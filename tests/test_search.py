import numpy as np

from rag.search import rank_docs


def test_rank_docs_dedupes_by_first_chunk_rank():
    scores = np.array([0.9, 0.8, 0.95, 0.1, 0.5])
    doc_ids = np.array(["a", "b", "a", "c", "b"])
    assert rank_docs(scores, doc_ids, 2) == ["a", "b"]
    assert rank_docs(scores, doc_ids, 5) == ["a", "b", "c"]


def test_rank_docs_breaks_ties_by_chunk_order():
    assert rank_docs(np.array([1.0, 1.0]), np.array(["x", "y"]), 2) == ["x", "y"]
