import json

import numpy as np

from rag.bm25 import BM25Retriever
from rag.index import load_cfg
from rag.search import rank_docs, rrf


def test_rrf_sums_reciprocal_ranks():
    # b: 1/(1+2) + 1/(1+1) > a: 1/(1+1) > c: 1/(1+2)
    assert rrf([["a", "b"], ["b", "c"]], k=1, top_k=3) == ["b", "a", "c"]


def test_rrf_ties_follow_first_ranking():
    assert rrf([["a", "b"], ["b", "a"]], k=60, top_k=2) == ["a", "b"]
    assert rrf([["a"], ["c"]], k=60, top_k=2) == ["a", "c"]


def test_bm25_finds_lexical_match(tmp_path):
    chunks = [
        {"doc_id": "d1", "text": "국방위원회에서 병역법 개정안을 심사했습니다."},
        {"doc_id": "d2", "text": "보건복지위원회는 국민연금 제도를 논의했습니다."},
        {"doc_id": "d2", "text": "연금 개혁에 대한 질의가 이어졌습니다."},
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
    cfg = load_cfg(["+exp=exp001"])
    bm25 = BM25Retriever(cfg, tmp_path)
    assert (tmp_path / f"bm25-{cfg.retriever.bm25.name}").is_dir()

    doc_ids = np.array([c["doc_id"] for c in chunks])
    ids = bm25.query_ids(["국민연금 개혁은?", "병역법", "그리고"])
    assert rank_docs(bm25.scores(ids[0]), doc_ids, 1) == ["d2"]
    assert rank_docs(bm25.scores(ids[1]), doc_ids, 1) == ["d1"]
    assert ids[2] == [] and not bm25.scores(ids[2]).any()
    # 캐시를 다시 읽어도 같은 점수
    again = BM25Retriever(cfg, tmp_path)
    assert np.allclose(again.scores(ids[0]), bm25.scores(ids[0]))
