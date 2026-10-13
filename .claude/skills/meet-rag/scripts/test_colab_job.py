import importlib.util
import json
import subprocess
from pathlib import Path

# 하네스 테스트는 PR 병합 조건(uv run pytest -q)에 들지 않게 스크립트 옆에 둔다
SCRIPT = Path(__file__).resolve().parent / "colab_job.py"
spec = importlib.util.spec_from_file_location("colab_job", SCRIPT)
colab_job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(colab_job)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_root(tmp_path, frozen=True):
    splits = tmp_path / "data/splits/queries.csv"
    splits.parent.mkdir(parents=True)
    splits.write_text("qid,split\nd1,dev\nt1,test\n", encoding="utf-8")
    if frozen:
        write_jsonl(tmp_path / "data/multidoc/queries_g3.jsonl",
                    [{"qid": "md-conf-0001", "query": "q"}])
    return tmp_path


def test_non_dev_qids_accepts_dev_and_frozen_multidoc(tmp_path, monkeypatch):
    monkeypatch.setattr(colab_job, "ROOT", make_root(tmp_path))
    up = tmp_path / "up.jsonl"
    write_jsonl(up, [{"qid": "d1"}, {"qid": "md-conf-0001"}, {"doc_id": "x"}])
    assert colab_job.non_dev_qids(up) == 0


def test_non_dev_qids_counts_test_and_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(colab_job, "ROOT", make_root(tmp_path))
    up = tmp_path / "up.jsonl"
    write_jsonl(up, [{"qid": "t1"}, {"qid": "md-conf-9999"}, {"qid": "d1"}])
    assert colab_job.non_dev_qids(up) == 2


def test_non_dev_qids_without_frozen_set(tmp_path, monkeypatch):
    monkeypatch.setattr(colab_job, "ROOT", make_root(tmp_path, frozen=False))
    up = tmp_path / "up.jsonl"
    write_jsonl(up, [{"qid": "md-conf-0001"}])
    assert colab_job.non_dev_qids(up) == 1


class FakeRun:
    """subprocess.run 대역. 결과 목록을 차례로 돌려주고 호출 수를 센다."""

    def __init__(self, results):
        self.results, self.calls = list(results), 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        r = self.results.pop(0)
        if r == "timeout":
            raise subprocess.TimeoutExpired("colab", kwargs["timeout"])
        return subprocess.CompletedProcess(args, r[0], r[1], "")


def test_colab_retries_timeout_and_lost_connection(monkeypatch):
    fake = FakeRun(["timeout", (1, "RuntimeError: Connection was lost."), (0, "ok")])
    monkeypatch.setattr(colab_job.subprocess, "run", fake)
    assert colab_job.colab("exec", "-s", "x") == "ok"
    assert fake.calls == 3


def test_colab_does_not_retry_other_errors(monkeypatch):
    fake = FakeRun([(1, "session not found")])
    monkeypatch.setattr(colab_job.subprocess, "run", fake)
    assert colab_job.colab("exec", "-s", "x", check=False) == "session not found"
    assert fake.calls == 1


def test_start_bg_is_not_retried(monkeypatch):
    # nohup 실행을 두 번 띄우면 같은 산출물을 동시에 쓴다
    fake = FakeRun([(1, "RuntimeError: Connection was lost."), (0, "EXIT 0")])
    monkeypatch.setattr(colab_job.subprocess, "run", fake)
    try:
        colab_job.start_bg("x", "echo hi")
    except SystemExit:
        pass
    assert fake.calls == 1
