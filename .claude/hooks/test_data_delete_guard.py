import json
import subprocess
import sys
from pathlib import Path

import pytest
from data_delete_guard import decide, to_path

HOOK = Path(__file__).with_name("data_delete_guard.py")
windows = pytest.mark.skipif(sys.platform != "win32", reason="junction은 Windows에서 만든다")


@pytest.fixture
def repo(tmp_path):
    """root/data(원본), root/wt(링크 없는 worktree), root/wt2(data junction이 든 worktree)."""
    root = tmp_path / "root"
    (root / "data" / "gen_eval").mkdir(parents=True)
    (root / "data" / "gen_eval" / "x.json").write_text("{}", encoding="utf-8")
    (root / "wt").mkdir()
    (root / "wt" / "a.txt").write_text("a", encoding="utf-8")
    (root / "wt2").mkdir()
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "wt2" / "data"),
                        str(root / "data")], check=True, capture_output=True)
    return root


def run(command, root):
    return decide(command, root, root)


@windows
@pytest.mark.parametrize("command", [
    "git worktree remove --force {r}/wt2",  # 2026-10-22 사고의 명령
    "rm -rf {r}/wt2",
    "Remove-Item -Recurse -Force {r}/wt2",
    "cmd /c rmdir /s /q {r}/wt2",
    "rm -rf {r}/wt2/data",  # 링크 자체에 재귀 삭제
])
def test_recursive_delete_through_link_is_denied(repo, command):
    out = run(command.format(r=repo.as_posix()), repo)
    assert out and out[0] == "deny"


@windows
@pytest.mark.parametrize("command", [
    "cmd /c rmdir {r}/wt2/data",  # 링크만 지운다
    "(Get-Item {r}/wt2/data).Delete()",
    "mklink /J {r}/wt/data {r}/data",  # 링크를 만드는 것은 막지 않는다
])
def test_link_only_operations_pass(repo, command):
    assert run(command.format(r=repo.as_posix()), repo) is None


@pytest.fixture
def session(repo, tmp_path):
    """원본 repo의 worktree에서 도는 하위 세션의 루트(.git이 gitdir 파일)."""
    (repo / ".git" / "worktrees" / "w").mkdir(parents=True)
    wt = tmp_path / "wt_session"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {(repo / '.git' / 'worktrees' / 'w').as_posix()}\n",
                             encoding="utf-8")
    return wt


DATA_DELETES = [
    "rm {r}/data/gen_eval/x.json",
    "rm -rf data/gen_eval",  # cwd 기준 상대 경로
    "Remove-Item {r}/data/gen_eval/x.json",
    "rm data/gen_eval/없는파일.json",  # 아직 없어도 data/ 아래면 확인
    "git clean -fdx",
    "python -c \"import os; os.remove('data/gen_eval/x.json')\"",
]


@pytest.mark.parametrize("command", DATA_DELETES)
def test_worktree_session_deleting_original_data_asks(repo, session, command):
    # 하위 세션은 <원본>/.claude/worktrees/<이름>에서 돈다. .git 파일로 원본 data/를 찾는다
    out = decide(command.format(r=repo.as_posix()), repo, session)
    assert out and out[0] == "ask"


@pytest.mark.parametrize("command", [
    'bash -c "rm -rf {r}/data/gen_eval"',  # 다른 셸에 넘긴 삭제도 명령이다
    "powershell -NoProfile -Command \"Remove-Item -Recurse -Force '{r}/data/gen_eval'\"",
])
def test_wrapped_shell_deletion_asks(repo, session, command):
    out = decide(command.format(r=repo.as_posix()), repo, session)
    assert out and out[0] == "ask"


@windows
def test_wrapped_shell_through_link_is_denied(repo):
    out = run(f'bash -c "rm -rf {repo.as_posix()}/wt2"', repo)
    assert out and out[0] == "deny"


@pytest.mark.parametrize("command", DATA_DELETES)
def test_main_checkout_data_deletion_is_not_asked(repo, command):
    # 막으려는 것은 분리된 세션의 임의 삭제다. 메인 체크아웃의 data/ 삭제는 그대로 둔다
    assert run(command.format(r=repo.as_posix()), repo) is None


@pytest.mark.parametrize("command", [
    "rm -rf {r}/wt",  # 링크 없는 디렉터리
    "git worktree remove {r}/wt",  # 병합 뒤 일반적인 worktree 정리는 그대로 된다
    "git worktree remove --force {r}/wt",
    "cd {r} && rm -rf {r}/wt",  # cd 대상(저장소 루트)은 삭제 대상이 아니다
    "Remove-Item -Force {r}/wt/a.txt",
    "git status && uv run ruff check --format=full .",
    "git clean -fd",  # 추적하지 않는 파일만, 무시 파일(data/)은 남긴다
    "grep -n 'rm -rf' docs/x.md",
    # 커밋 메시지·heredoc 본문에 적힌 삭제 명령은 명령이 아니다
    'git commit -q -m "fix: rm -rf {r}/wt2/* 에서 data/ 링크를 보지 못함"',
    "cat > x.md <<'EOF'\nrm -rf {r}/wt2\ngit worktree remove --force {r}/wt2\nEOF",
])
def test_other_commands_pass(repo, session, command):
    assert run(command.format(r=repo.as_posix()), repo) is None
    assert decide(command.format(r=repo.as_posix()), repo, session) is None


@windows
def test_wildcard_reaches_link_inside(repo):
    # 셸이 wt2/*를 펼치면 wt2/data(junction)가 재귀 삭제 대상이 된다
    out = run(f"rm -rf {repo.as_posix()}/wt2/*", repo)
    assert out and out[0] == "deny"


def test_git_bash_drive_path():
    assert to_path("/c/workspace/x", Path("C:/")) == Path("C:/workspace/x")


@windows
def test_hook_outputs_permission_decision(repo):
    payload = {"tool_input": {"command": f"git worktree remove --force {repo.as_posix()}/wt2"},
               "cwd": str(repo)}
    # 훅은 자기 위치로 저장소 루트를 정한다. 여기서는 deny 판정이 링크 검사에서 나와 루트와 무관하다
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, check=True)
    out = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "링크" in out["permissionDecisionReason"]
    quiet = subprocess.run([sys.executable, str(HOOK)], capture_output=True, check=True,
                           input=json.dumps({"tool_input": {"command": "git status"}}).encode())
    assert quiet.stdout == b""
