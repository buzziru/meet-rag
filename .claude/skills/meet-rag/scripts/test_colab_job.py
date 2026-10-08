import importlib.util
import json
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
