import numpy as np

from rag.search import first_docs, rank_docs, rank_with_pool


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
