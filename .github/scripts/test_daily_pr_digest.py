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


DIFF = (
    "diff --git a/src/a.py b/src/a.py\n@@ -1 +1 @@\n-x\n+y\n"
    "diff --git a/docs/d.md b/docs/d.md\n@@ -1 +1 @@\n-p\n+q\n"
    "diff --git a/tests/test_a.py b/tests/test_a.py\n@@ -1 +1 @@\n-m\n+n\n"
)
MERGED = {"number": 7, "title": "t", "files": [{"path": "src/a.py"}]}
OPEN_PR = {"number": 8, "title": "열림", "state": "OPEN"}


@pytest.fixture
def code_tree(tmp_path, monkeypatch):
    """main 체크아웃처럼 src/a.py만 있는 작업 디렉터리. tests/test_a.py는 지워진 파일이다."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)


def test_review_input_keeps_code_diffs_and_numbered_files_of_merged_prs(
    digest, monkeypatch, code_tree
):
    called = []
    monkeypatch.setattr(digest, "gh", lambda *a: called.append(a[2]) or DIFF)
    data, omitted = digest.review_input([MERGED, OPEN_PR])
    assert called == ["7"]  # 열린 PR의 diff는 받지 않는다
    assert [d["path"] for d in data["diffs"]] == ["src/a.py", "tests/test_a.py"]
    assert data["files"] == [{"path": "src/a.py", "text": "1\tx = 1\n2\ty = 2"}]
    assert data["prs"] == [{"number": 7, "title": "t"}]
    assert omitted == []


def test_review_input_over_limit_omits_files_before_diffs(digest, monkeypatch, code_tree):
    monkeypatch.setattr(digest, "gh", lambda *a: DIFF)
    monkeypatch.setattr(digest, "REVIEW_MAX_CHARS", 60)  # 짧은 diff 하나만 들어가는 크기
    data, omitted = digest.review_input([MERGED])
    assert len(data["diffs"]) == 1 and data["files"] == []
    assert data["omitted"] == omitted
    assert omitted == ["diff tests/test_a.py", "파일 src/a.py"]


def test_review_input_without_code_change_is_none(digest, monkeypatch, code_tree):
    monkeypatch.setattr(digest, "gh", lambda *a: "diff --git a/docs/d.md b/docs/d.md\n")
    assert digest.review_input([MERGED]) == (None, [])


def review_response(text, stop_reason="end_turn"):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason=stop_reason, model="opus", usage=None, content=[block])


@pytest.fixture
def review_env(digest, monkeypatch, code_tree):
    monkeypatch.setenv("MODEL", "opus")
    monkeypatch.setenv("FALLBACK_MODEL", "sonnet")
    monkeypatch.setattr(digest, "gh", lambda *a: DIFF)


def test_section_has_findings_and_model(digest, monkeypatch, review_env):
    monkeypatch.setattr(digest, "ask_review", lambda *a: review_response("- [ ] 지적"))
    section = digest.code_review_section(None, [MERGED])
    assert section.startswith("## 코드 리뷰\n\n- [ ] 지적")
    assert "`opus`" in section


def test_section_is_none_without_findings(digest, monkeypatch, review_env):
    monkeypatch.setattr(digest, "ask_review", lambda *a: review_response("NO_FINDINGS"))
    assert digest.code_review_section(None, [MERGED]) is None


def test_section_without_findings_reports_omitted_items(digest, monkeypatch, review_env):
    monkeypatch.setattr(digest, "ask_review", lambda *a: review_response("NO_FINDINGS"))
    monkeypatch.setattr(digest, "REVIEW_MAX_CHARS", 60)
    section = digest.code_review_section(None, [MERGED])
    assert "지적 없음" in section and "파일 src/a.py" in section


def test_section_reports_error_during_stream(digest, monkeypatch, review_env):
    def fail(*a):
        raise RuntimeError("끊김")  # SDK가 APIError로 바꾸지 않는 스트림 도중 오류

    monkeypatch.setattr(digest, "ask_review", fail)
    assert "RuntimeError" in digest.code_review_section(None, [MERGED])


def test_section_reports_unfinished_response(digest, monkeypatch, review_env):
    monkeypatch.setattr(
        digest, "ask_review", lambda *a: review_response("잘린 글", "max_tokens")
    )
    section = digest.code_review_section(None, [MERGED])
    assert "max_tokens" in section and "잘린 글" not in section


def test_section_reports_failure_of_both_models(digest, monkeypatch, review_env):
    def fail(*a):
        raise FakeAPIError

    monkeypatch.setattr(digest.anthropic, "APIError", FakeAPIError)
    monkeypatch.setattr(digest, "ask_review", fail)
    assert "FakeAPIError" in digest.code_review_section(None, [MERGED])


def run_main(digest, monkeypatch, digest_text, section):
    """main을 그대로 지나 이슈 본문을 돌려준다. 이슈를 만들지 않았으면 None."""
    captured = {}

    def fake_gh(*args):
        if args[:2] == ("pr", "view"):
            return json.dumps(PR | {"state": "OPEN", "mergedAt": None})
        if args[:2] == ("issue", "create"):
            captured["body"] = Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8")
        if args[:2] == ("issue", "list"):
            return "[]"
        return ""

    monkeypatch.setenv("PR_NUMBERS", "1")
    monkeypatch.setenv("MODEL", "opus")
    monkeypatch.setenv("FALLBACK_MODEL", "sonnet")
    monkeypatch.setattr(digest, "gh", fake_gh)
    monkeypatch.setattr(digest.anthropic, "Anthropic", lambda: None)
    result = (review_response(digest_text), None)
    monkeypatch.setattr(digest, "ask_with_fallback", lambda c, t: result)
    monkeypatch.setattr(digest, "code_review_section", lambda c, p: section)
    digest.main()
    return captured.get("body")


@pytest.mark.parametrize(
    "digest_text,section,kept,dropped",
    [
        ("종합", "## 코드 리뷰\n\n지적", ["종합", "## 코드 리뷰", "`opus`"], []),
        ("종합", None, ["종합"], ["## 코드 리뷰"]),
        ("NO_ITEMS", "## 코드 리뷰\n\n지적", ["## 코드 리뷰"], ["NO_ITEMS"]),
    ],
)
def test_main_issue_body(digest, monkeypatch, digest_text, section, kept, dropped):
    body = run_main(digest, monkeypatch, digest_text, section)
    assert all(k in body for k in kept)
    assert not any(d in body for d in dropped)


def test_main_no_issue_without_items_and_findings(digest, monkeypatch):
    assert run_main(digest, monkeypatch, "NO_ITEMS", None) is None
