import json
import subprocess
import sys
from pathlib import Path

import pytest
from commit_type_guard import bad_type, commit_subject

HOOK = Path(__file__).with_name("commit_type_guard.py")

# 이번 세션(S16·S17)에 실제로 쓴 형태
OK = [
    'git commit -q -m "refactor: 검색·생성 규칙을 한 곳에 두고"',
    'git add docs && git commit -q -m "docs: SLICE 17 결과\n\nCo-Authored-By: x"',
    'git commit -q --amend -m "refactor: BM25 검색기가 Kiwi 하나를 공유"',
    "git commit -m \"$(cat <<'EOF'\nfeat: 새 기능\n\n본문\nEOF\n)\"",
    "git commit -qm 'fix: 프롬프트 대조'",
]
BAD = [
    ("git commit -qm 'fix(judge): 프롬프트 대조'", "fix(judge):"),  # 범위 표기는 규약에 없다
    ('git commit -q -m "perf: BM25 검색기가 Kiwi 하나를 공유"', "perf"),
    ('git commit -m "Update readme"', "Update"),
    ("git commit -qm 'style: 정리'", "style"),
]
NOT_CHECKED = [
    "git commit --amend --no-edit",
    "git commit -F msg.txt",
    "git log --oneline -3",
    'grep -n "git commit" docs/x.md',
]


@pytest.mark.parametrize("command", OK)
def test_allowed_types_pass(command):
    assert bad_type(commit_subject(command)) is None


@pytest.mark.parametrize(("command", "found"), BAD)
def test_other_types_are_reported(command, found):
    assert bad_type(commit_subject(command)) == found


@pytest.mark.parametrize("command", NOT_CHECKED)
def test_commands_without_message_are_not_checked(command):
    assert commit_subject(command) is None


def run_hook(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    out = subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                         capture_output=True, check=True).stdout.decode("utf-8")
    return json.loads(out) if out else None


def test_hook_denies_only_bad_type():
    assert run_hook(OK[0]) is None
    out = run_hook('git commit -q -m "perf: 공유"')["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "perf" in out["permissionDecisionReason"]
