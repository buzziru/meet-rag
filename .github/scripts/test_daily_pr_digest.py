"""daily_pr_digest 수집 로직 동작 테스트.

`uv run --no-project --with anthropic==1.15.0 --with pytest pytest -q .github/scripts`
"""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def digest(monkeypatch):
    for k, v in {
        "GITHUB_REPOSITORY": "o/r",
        "OWNER": "o",
        "SINCE": "2026-10-20T00:00:00Z",
        "DAY": "2026-10-20",
    }.items():
        monkeypatch.setenv(k, v)
    import daily_pr_digest

    return importlib.reload(daily_pr_digest)


def fake_gh(view: dict, line_comments: list[dict]):
    def gh(*args):
        return json.dumps(view if args[0] == "pr" else [line_comments])

    return gh


PR = {
    "number": 1, "title": "t", "url": "u", "body": "본문",
    "comments": [
        {"author": {"login": "o"}, "body": "소유자"},
        {"author": {"login": "x"}, "body": "외부"},
    ],
    "reviews": [{"author": {"login": "x"}, "state": "COMMENTED", "body": "외부 리뷰"}],
    "files": [{"path": "a.py", "additions": 3, "deletions": 1}],
}
LINES = [
    {"user": {"login": "o"}, "path": "a.py", "line": 2, "body": "줄 소유자"},
    {"user": {"login": "x"}, "path": "a.py", "line": 3, "body": "줄 외부"},
]


def test_merged_in_period_keeps_only_owner_comments(digest, monkeypatch):
    view = PR | {"state": "MERGED", "mergedAt": "2026-10-20T05:00:00Z"}
    monkeypatch.setattr(digest, "gh", fake_gh(view, LINES))
    pr = digest.collect_pr("1")
    assert pr["comments"] == [{"body": "소유자"}]
    assert pr["reviews"] == []
    assert [c["body"] for c in pr["line_comments"]] == ["줄 소유자"]
    assert pr["files"] == [{"path": "a.py", "additions": 3, "deletions": 1}]


@pytest.mark.parametrize("state,merged_at", [("OPEN", None), ("MERGED", "2026-10-19T23:00:00Z")])
def test_open_or_merged_before_period_has_head_only(digest, monkeypatch, state, merged_at):
    monkeypatch.setattr(digest, "gh", fake_gh(PR | {"state": state, "mergedAt": merged_at}, LINES))
    assert digest.collect_pr("1") == {"number": 1, "title": "t", "url": "u", "state": state}


class FakeAPIError(Exception):
    pass


class FakeClient:
    """모델 이름별로 정한 결과(응답 stop_reason 또는 예외)를 돌려준다."""

    def __init__(self, outcomes: dict):
        self.outcomes, self.calls = outcomes, []
        self.messages = self

    def create(self, model, **_):
        self.calls.append(model)
        outcome = self.outcomes[model]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(stop_reason=outcome, model=model, usage=None)


@pytest.mark.parametrize(
    "opus,calls,failure",
    [
        ("end_turn", ["opus"], None),
        ("refusal", ["opus", "sonnet"], "거절"),
        (FakeAPIError(), ["opus", "sonnet"], "API 오류(FakeAPIError)"),
    ],
)
def test_fallback_on_refusal_or_api_error(digest, monkeypatch, opus, calls, failure):
    monkeypatch.setenv("MODEL", "opus")
    monkeypatch.setenv("FALLBACK_MODEL", "sonnet")
    monkeypatch.setattr(digest.anthropic, "APIError", FakeAPIError)
    monkeypatch.setattr(digest.PROMPT.__class__, "read_text", lambda *a, **k: "지시")
    client = FakeClient({"opus": opus, "sonnet": "end_turn"})
    response, got = digest.ask_with_fallback(client, "{}")
    assert client.calls == calls
    assert got == failure
    assert response.model == calls[-1]
