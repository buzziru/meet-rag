import json

import bm25s
import numpy as np
from kiwipiepy import Kiwi

from rag.bm25 import BM25Retriever, build, doc_meta, forms
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


def test_meta_prefix_makes_metadata_searchable(tmp_path):
    corpus = [
        {"doc_id": "d1", "date": "2019년3월5일(화)", "committee_name": "국방위원회"},
        {"doc_id": "d2", "date": "2020년7월1일(수)", "committee_name": ""},
    ]
    with (tmp_path / "corpus.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in corpus)
    meta = doc_meta(tmp_path / "corpus.jsonl", ["date", "committee_name"])
    assert meta == {"d1": "2019년3월5일(화) 국방위원회", "d2": "2020년7월1일(수)"}

    chunks = [{"doc_id": "d1", "text": "예산을 논의했습니다."},
              {"doc_id": "d2", "text": "예산을 논의했습니다."}]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
    b = load_cfg(["+exp=exp002"]).retriever.bm25
    build(tmp_path / "chunks.jsonl", tmp_path / "idx", b, Kiwi(), meta)
    model = bm25s.BM25.load(tmp_path / "idx", load_vocab=True)
    q = model.get_tokens_ids(next(forms(Kiwi(), ["국방위원회 예산"], set(b.tags))))
    scores = model.get_scores_from_ids(q)
    assert scores[0] > scores[1]


def test_run_name_overrides_file_suffix():
    cfg = load_cfg(["+exp=exp002"])
    assert cfg.retriever.run_name == "hybrid-meta" and cfg.retriever.bm25.name == "kiwi-meta-v1"
    assert load_cfg(["+exp=exp001"]).retriever.get("run_name") is None
