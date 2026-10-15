import numpy as np
import pytest
from test_search import _tmp_cfg, _write_text_index

from rag.retrieve import Retriever, convex, minmax


def test_minmax_maps_first_to_one_last_to_zero():
    assert minmax(["a", "b", "c"], [0.9, 0.6, 0.3]) == pytest.approx({"a": 1.0, "b": 0.5, "c": 0.0})


def test_minmax_equal_scores_are_zero():
    assert minmax(["a", "b"], [2.0, 2.0]) == {"a": 0.0, "b": 0.0}


def test_convex_weights_and_missing_docs():
    dense = {"a": 1.0, "b": 0.5}
    bm25 = {"c": 1.0, "b": 0.8}
    # b: 0.5·0.5 + 0.5·0.8 = 0.65, a: 0.5, c: 0.5 (동점은 dense 목록 먼저)
    assert convex(dense, bm25, 0.5) == ["b", "a", "c"]
    assert convex(dense, bm25, 1.0) == ["a", "b", "c"]


def test_retriever_score_fusion_replaces_dense_and_bm25(tmp_path):
    cfg = _tmp_cfg(tmp_path, ["+exp=exp001", "retriever.fusion.depth=3",
                              "retriever.bm25.name=test", "+retriever.fusion.method=score",
                              "+retriever.fusion.alpha=0.5"])
    _write_text_index(tmp_path / "kure-v1-512" / "dev-small",
                      [("a", "예산 심사"), ("b", "국정감사 질의"), ("c", "법안 처리")],
                      [[0.9, 0.0], [0.5, 0.0], [0.1, 0.0]])
    ret = Retriever(cfg)
    row = ret.chunk_emb @ np.array([1.0, 0.0], dtype=np.float32)
    tokens = ret.query_tokens(["국정감사 질의"])[0]
    named, _, _ = ret.lists(row, tokens)
    assert list(named) == ["cc"]
    # dense: a 1, b 0.5, c 0. BM25는 b만 점수가 있어 b 1, 나머지 0 → b 0.75, a 0.5, c 0
    assert named["cc"] == ["b", "a", "c"]
    assert ret.candidates(row, tokens)[0] == ["b", "a", "c"]
