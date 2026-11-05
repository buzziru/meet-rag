import json
import subprocess
import sys

import pytest
import sessions_news as s


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                   check=True, capture_output=True)


def _commit(cwd, name, msg):
    (cwd / name).write_text("x\n", encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-m", msg)


@pytest.fixture
def repo(tmp_path):
    """메인 체크아웃 main과 worktree deploy."""
    main = tmp_path / "repo"
    main.mkdir()
    _git(main, "init", "-b", "main")
    (main / "_workspace").mkdir()
    _commit(main, "a.txt", "첫 커밋")
    deploy = tmp_path / "deploy"
    _git(main, "worktree", "add", "-b", "feat/x", str(deploy))
    return main, deploy


def test_names_sessions_by_worktree(repo):
    main, deploy = repo
    assert s.locate(str(main))[:2] == (main.resolve(), "main")
    assert s.locate(str(deploy))[:2] == (main.resolve(), "deploy")


def test_other_sessions_log_line_shows_once_and_own_never(repo):
    main, deploy = repo
    s.collect(str(main), "m")
    s.collect(str(deploy), "d")
    s.add(str(deploy), "Dataset 교체", "main: 재시작 필요")

    assert s.collect(str(deploy), "d") == ""  # 내가 적은 줄
    first = s.collect(str(main), "m")
    assert "| deploy | Dataset 교체 | main: 재시작 필요" in first
    assert s.collect(str(main), "m") == ""  # 두 번째는 없음


def test_other_branch_commit_shows_with_files_once(repo):
    main, deploy = repo
    s.collect(str(main), "m")
    _commit(deploy, "한글.txt", "feat: 배포")

    first = s.collect(str(main), "m")
    assert "deploy 커밋:" in first
    assert "feat: 배포" in first
    assert "한글.txt" in first  # core.quotepath로 이스케이프되지 않음
    assert s.collect(str(main), "m") == ""


def test_commit_already_in_my_branch_is_not_news(repo):
    main, deploy = repo
    s.collect(str(main), "m")
    _commit(main, "b.txt", "내 커밋")
    _git(deploy, "merge", "main")  # 상대가 main을 병합해 내 커밋이 상대 브랜치로 감

    assert s.collect(str(main), "m") == ""


def test_new_claude_session_replays_recent_log_only(repo):
    main, deploy = repo
    for i in range(s.REPLAY + 2):
        s.add(str(deploy), f"소식{i:02d}", "main")
    s.collect(str(main), "옛 세션")

    replay = s.collect(str(main), "새 세션")
    assert "소식01" not in replay
    assert "소식02" in replay
    assert f"소식{s.REPLAY + 1:02d}" in replay


def test_first_run_does_not_report_old_commits(repo):
    main, deploy = repo
    _commit(deploy, "c.txt", "옛 커밋")
    assert s.collect(str(main), "m") == ""


def test_many_commits_are_capped(repo):
    main, deploy = repo
    s.collect(str(main), "m")
    for i in range(s.MAX_COMMITS + 2):
        _commit(deploy, f"f{i}.txt", f"커밋{i}")
    news = s.collect(str(main), "m")
    assert "외 커밋 2개 (파일: f0.txt, f1.txt)" in news  # 오래된 커밋도 파일 이름은 남는다
    assert "커밋0" not in news


def test_hook_stays_silent_outside_git(tmp_path, monkeypatch, capsys):
    payload = json.dumps({"cwd": str(tmp_path), "session_id": "m"}).encode()
    monkeypatch.setattr(sys, "argv", ["sessions_news.py"])
    monkeypatch.setattr("sys.stdin", type("S", (), {"buffer": type("B", (), {
        "read": staticmethod(lambda: payload)})()})())
    s.main()
    assert capsys.readouterr().out == ""


def test_hook_prints_additional_context(repo, monkeypatch):
    main, deploy = repo
    s.collect(str(main), "m")
    s.add(str(deploy), "소식", "main")
    r = subprocess.run([sys.executable, s.__file__], input=json.dumps(
        {"cwd": str(main), "session_id": "m"}).encode(), capture_output=True, check=True)
    out = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    assert "소식" in out["additionalContext"]
