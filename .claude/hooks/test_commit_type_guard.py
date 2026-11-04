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
    "git commit -m @'\nchore: PowerShell here-string\n\n본문\n'@",
    'git commit -m @"\r\ndocs: CRLF here-string\r\n"@',
    'git add x; if ($?) { git commit -q -m "chore: PowerShell 블록" }',
    'git commit -m "chore: 뒤에 다른 명령" && uv run python -m rag.x',
]
BAD = [
    ("git commit -m @'\nperf: PowerShell here-string\n'@", "perf"),
    ("git commit -qm 'fix(judge): 프롬프트 대조'", "fix(judge):"),  # 범위 표기는 규약에 없다
    ('git commit -q -m "perf: BM25 검색기가 Kiwi 하나를 공유"', "perf"),
    ('git commit -m "Update readme"', "Update"),
    ('git add x; git commit -m "perf: 구분자 뒤"', "perf"),
    ('GIT_AUTHOR_NAME=x git commit -m "perf: 환경 변수 뒤"', "perf"),
    ('git commit -q \\\n  -m "perf: 줄 잇기"', "perf"),
    ('git status && git commit -m "perf: && 뒤"', "perf"),
]
NOT_CHECKED = [
    "git commit --amend --no-edit",
    "git commit -F msg.txt",
    "git log --oneline -3",
    'grep -n "git commit" docs/x.md',
]
# 실제로 막혔던 형태(ADR-0088): 뒤 명령의 -m, heredoc 본문의 글자, 다른 명령의 인자에 든 글자
FALSE_POSITIVES = [
    "git commit -F - <<'EOF'\nchore: 요약\nEOF\nuv run python -m rag.x",
    "git commit -F msg.txt && uv run python -m rag.x",
    "git commit -F - <<'EOF'\nchore: 요약\n\n본문에 python -m 글자\nEOF",
    'echo "git commit -F - 와 python -m rag 오탐" >> note.md',
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


@pytest.mark.parametrize("command", FALSE_POSITIVES)
def test_hook_does_not_read_other_text_as_message(command):
    assert run_hook(command) is None


def test_hook_denies_only_bad_type():
    assert run_hook(OK[0]) is None
    out = run_hook('git commit -q -m "perf: 공유"')["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "perf" in out["permissionDecisionReason"]
