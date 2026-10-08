import json
import os
import subprocess
import sys
from pathlib import Path

# 하네스 테스트는 PR 병합 조건(uv run pytest -q)에 들지 않게 스크립트 옆에 둔다
# (pytest는 .으로 시작하는 .claude/를 모으지 않는다)
SCRIPT = Path(__file__).resolve().parent / "worker_queue.py"


def run(*args, cwd):
    # 자식 프로세스의 한글 출력이 cp949로 나오지 않게 한다
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_queue_flow(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "ids.txt").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    (out / "b.json").touch()
    common = ["--jobs", "j.jsonl", "--out", "out"]

    assert run("plan", *common, "--ids", "ids.txt", "--size", "2", cwd=tmp_path).returncode == 0
    assert [j["ids"] for j in read_jsonl(tmp_path / "j.jsonl")] == [["a", "c"], ["d", "e"]]

    r = run("start", *common, "--queue", "q.jsonl", "1", cwd=tmp_path)
    assert r.stdout.strip() == "1: a c"
    (out / "a.json").touch()
    r = run("done", *common, "--queue", "q.jsonl", "1", cwd=tmp_path)
    assert r.stdout.strip() == "1: missing c"
    (out / "c.json").touch()
    assert "남은 항목 없음" in run("start", *common, "--queue", "q.jsonl", "1", cwd=tmp_path).stdout

    assert [(r["jobs"], r["job"], r["status"]) for r in read_jsonl(tmp_path / "q.jsonl")] == [
        ("j.jsonl", 1, "running"), ("j.jsonl", 1, "partial"),
    ]


def test_guards(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "ids.txt").write_text("a\n", encoding="utf-8")
    common = ["--jobs", "j.jsonl", "--out", "out"]
    run("plan", *common, "--ids", "ids.txt", "--size", "1", cwd=tmp_path)

    assert run("plan", *common, "--ids", "ids.txt", "--size", "1", cwd=tmp_path).returncode != 0
    assert run("start", *common, "1", cwd=tmp_path).returncode != 0
    assert run("start", *common, "--queue", "q.jsonl", "1", "9", cwd=tmp_path).returncode != 0
    assert not (tmp_path / "q.jsonl").exists()
