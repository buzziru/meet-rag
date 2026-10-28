import json

import merged_branch_push_guard as g
import pytest


@pytest.mark.parametrize(("command", "target"), [
    ("git push -q", (None, None)),  # 현재 브랜치
    ("cd /c/x && git push -q -u origin feat/s28-x 2>&1 | tail -1", ("feat/s28-x", None)),
    ("git push origin HEAD", (None, None)),
    ("git push origin HEAD:refs/heads/exp/exp018", ("exp/exp018", None)),
    ("git -C /c/w push origin main", ("main", "/c/w")),
    ('git -C "C:/a b" push', (None, "C:/a b")),
])
def test_push_target(command, target):
    assert g.push_target(command) == target


@pytest.mark.parametrize("command", [
    "git push origin --delete docs/x",
    "git push -q origin :docs/x",
    "git pull --ff-only",
])
def test_not_checked(command):
    assert g.push_target(command) is None


def _run(monkeypatch, capsys, command, current, merged):
    monkeypatch.setattr(g, "current_branch", lambda cwd: current)
    monkeypatch.setattr(g, "merged_pr", lambda b, cwd: merged.get(b))
    monkeypatch.setattr("sys.stdin", type("S", (), {"buffer": type("B", (), {
        "read": staticmethod(lambda: json.dumps({"tool_input": {"command": command},
                                                  "cwd": "."}).encode())})()})())
    g.main()
    return capsys.readouterr().out


def test_blocks_push_to_merged_branch(monkeypatch, capsys):
    out = _run(monkeypatch, capsys, "git push -q", "exp/exp018-refusal-format",
               {"exp/exp018-refusal-format": 180})
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "#180" in out


def test_allows_open_branch_and_main(monkeypatch, capsys):
    assert _run(monkeypatch, capsys, "git push -q", "chore/x", {}) == ""
    assert _run(monkeypatch, capsys, "git push origin main", "main", {"main": 1}) == ""
