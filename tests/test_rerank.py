import json
import sys

import pytest
from omegaconf import OmegaConf

from rag.index import load_cfg
from rag.rerank import jev_body, write_scores
from rag.rerank import main as rerank_main
from rag.retrieve import read_rerank_scores, rerank_basis_path


def test_jev_body_one_question_per_candidate():
    jv = OmegaConf.create({"model": "m", "instructions": "답하는가?", "levels": ["a", "b"]})
    group = [{"query": "q", "text": f"t{i}", "doc_id": f"d{i}"} for i in range(2)]
    body = jev_body(group, jv)
    assert body["state"] == {"query": "q", "candidates": {"0": "t0", "1": "t1"}}
    assert body["questions"]["c1"] == {"type": "score", "instructions": "후보 1: 답하는가?",
                                       "criteria": ["a", "b"]}


def _rerank_args(tmp_path):
    pairs = tmp_path / "p.pairs.jsonl"
    pairs.write_text(json.dumps({"qid": "q1", "doc_id": "d1", "query": "q", "text": "t"}) + "\n",
                     encoding="utf-8")
    return ["+exp=exp017", "index.scope=dev-small", f"paths.rerank_pairs='{pairs.as_posix()}'",
            f"paths.rerank_scores='{(tmp_path / 's.scores.jsonl').as_posix()}'"]


def test_rerank_scores_are_read_only_with_matching_basis(tmp_path):
    args = _rerank_args(tmp_path)
    cfg = load_cfg(args)
    write_scores(cfg, [{"qid": "q1", "doc_id": "d1", "score": 0.5}])
    assert read_rerank_scores(cfg) == {"q1": {"d1": 0.5}}
    # Colab cuda·float16으로 만든 점수를 로컬 기본값(cpu·float32)으로 읽는다
    assert read_rerank_scores(load_cfg([*args, "retriever.rerank.dtype=float16"]))
    with pytest.raises(SystemExit, match="model"):
        read_rerank_scores(load_cfg([*args, "retriever.rerank.model=other"]))
    (tmp_path / "p.pairs.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="pairs_sha256"):  # 후보 쌍을 다시 만든 경우
        read_rerank_scores(cfg)


def test_rerank_scores_are_not_overwritten(tmp_path):
    cfg = load_cfg(_rerank_args(tmp_path))
    write_scores(cfg, [{"qid": "q1", "doc_id": "d1", "score": 0.5}])
    with pytest.raises(SystemExit, match="내용이 다른"):  # 로컬 cpu로 다시 채점한 경우
        write_scores(cfg, [{"qid": "q1", "doc_id": "d1", "score": 0.4}])


def test_adopt_writes_basis_without_scoring(tmp_path, monkeypatch):
    args = _rerank_args(tmp_path)
    (tmp_path / "s.scores.jsonl").write_text(
        json.dumps({"qid": "q1", "doc_id": "d1", "score": 0.5}) + "\n", encoding="utf-8")
    cfg = load_cfg(args)
    with pytest.raises(SystemExit, match="adopt_basis"):
        read_rerank_scores(cfg)
    monkeypatch.setattr(sys, "argv", ["rag.rerank", *args, "adopt_basis=true",
                                      "retriever.rerank.device=cuda",
                                      "retriever.rerank.dtype=float16"])
    rerank_main()
    basis = json.loads(rerank_basis_path(cfg).read_text(encoding="utf-8"))
    assert basis["dtype"] == "float16" and read_rerank_scores(cfg) == {"q1": {"d1": 0.5}}
