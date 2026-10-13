import numpy as np
import pytest

from rag.index import load_cfg
from rag.search import (
    chunks_by_doc,
    condition_docs,
    conditions_first,
    first_docs,
    query_files,
    rank_docs,
    rank_with_pool,
    rerank_top,
    rrf,
    top_docs,
    top_sum_scores,
)


def test_rank_docs_dedupes_by_first_chunk_rank():
    scores = np.array([0.9, 0.8, 0.95, 0.1, 0.5])
    doc_ids = np.array(["a", "b", "a", "c", "b"])
    assert rank_docs(scores, doc_ids, 2) == ["a", "b"]
    assert rank_docs(scores, doc_ids, 5) == ["a", "b", "c"]


def test_rank_docs_breaks_ties_by_chunk_order():
    assert rank_docs(np.array([1.0, 1.0]), np.array(["x", "y"]), 2) == ["x", "y"]


def test_pool_matches_full_sort():
    rng = np.random.default_rng(0)
    doc_ids = rng.integers(0, 300, 5000).astype(str)
    for _ in range(50):
        scores = rng.standard_normal(5000).astype(np.float32)
        full = first_docs(np.argsort(-scores, kind="stable"), doc_ids, 10)
        assert rank_docs(scores, doc_ids, 10, pool=30) == full


def test_pool_falls_back_when_too_few_docs():
    # 상위 청크가 모두 한 문서라 pool 안에서 문서 3개를 채우지 못한다
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
    doc_ids = np.array(["a", "a", "a", "a", "b", "c"])
    docs, fell_back = rank_with_pool(scores, doc_ids, 3, pool=3)
    assert (docs, fell_back) == (["a", "b", "c"], True)
    assert rank_with_pool(scores, doc_ids, 1, pool=3) == (["a"], False)


def test_query_batch_does_not_change_ranks():
    rng = np.random.default_rng(1)
    chunks = rng.standard_normal((2000, 32)).astype(np.float32)
    queries = rng.standard_normal((40, 32)).astype(np.float32)
    doc_ids = rng.integers(0, 200, 2000).astype(str)

    def run(batch):
        out = []
        for s in range(0, len(queries), batch):
            scores = queries[s : s + batch] @ chunks.T
            out += [rank_docs(row, doc_ids, 10, pool=50) for row in scores]
        return out

    assert run(7) == run(40)


def test_multidoc_queries_need_full_scope():
    cfg = load_cfg(["search.queries=multidoc", "index.scope=dev-small"])
    with pytest.raises(SystemExit):
        query_files(cfg)
    full = query_files(load_cfg(["search.queries=multidoc", "index.scope=full"]))
    assert full["name"] == "multidoc" and full["emb"].name == "queries-multidoc.npz"


def test_summary_q_files_unchanged():
    files = query_files(load_cfg(["index.scope=full"]))
    assert files["name"] == "dev-full" and files["emb"].name == "queries-full.npz"


def test_condition_docs_orders_by_count_then_dense():
    names = np.array(["a", "b", "c", "d"])
    scores = np.array([0.1, 0.9, 0.5, 0.7])
    assert condition_docs({0: 2, 1: 1, 2: 1, 3: 2}, scores, names, 10, 1) == ["d", "a", "b", "c"]
    assert condition_docs({0: 2, 1: 1, 2: 1, 3: 2}, scores, names, 2, 1) == ["d", "a"]


def test_condition_docs_min_fields():
    names = np.array(["a", "b", "c"])
    scores = np.array([0.1, 0.9, 0.5])
    assert condition_docs({0: 2, 1: 1, 2: 3}, scores, names, 10, min_fields=2) == ["c", "a"]
    assert condition_docs({1: 1}, scores, names, 10, min_fields=2) == []


def test_conditions_first_keeps_order_within_groups():
    assert conditions_first(["a", "b", "c", "d"], {"c", "a"}) == ["a", "c", "b", "d"]
    assert conditions_first(["a", "b"], set()) == ["a", "b"]


def test_rrf_without_top_k_returns_all():
    assert rrf([["a", "b"], ["c"]], 60, None) == ["a", "c", "b"]
    assert rrf([["a", "b"], ["c"]], 60, 2) == ["a", "c"]


def test_rerank_top_reorders_head_only():
    docs = ["a", "b", "c", "d"]
    assert rerank_top(docs, {"a": 0.1, "b": 0.9, "c": 0.5}, 3) == ["b", "c", "a", "d"]


def test_chunks_by_doc():
    got = chunks_by_doc(np.array(["x", "y", "x", "z", "y"]))
    assert {k: v.tolist() for k, v in got.items()} == {"x": [0, 2], "y": [1, 4], "z": [3]}


def test_top_sum_scores_adds_top_n_per_doc():
    scores = np.array([0.9, 0.2, 0.5, 0.8, 0.7])
    chunk_doc = np.array([0, 0, 0, 1, 2])
    # 문서 0: 0.9 + 0.5, 문서 1·2는 청크가 하나라 그 점수만
    np.testing.assert_allclose(top_sum_scores(scores, chunk_doc, 3, 2), [1.4, 0.8, 0.7])


def test_top_sum_with_n1_matches_max_ranking():
    rng = np.random.default_rng(0)
    chunk_doc = np.sort(rng.integers(0, 200, 3000))
    names = np.unique(chunk_doc).astype(str)
    _, inv = np.unique(chunk_doc, return_inverse=True)
    for _ in range(20):
        scores = rng.standard_normal(3000).astype(np.float32)
        got = top_docs(top_sum_scores(scores, inv, len(names), 1), names, 10)
        assert got == rank_docs(scores, names[inv], 10)
