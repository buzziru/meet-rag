import json

import numpy as np
import pytest
from omegaconf import OmegaConf
from test_search import _tmp_cfg, _write_text_index

from rag import rewrite
from rag.index import load_cfg
from rag.retrieve import Retriever, rank_docs, rrf

GATE = OmegaConf.create({"overlap_k": 2, "max_overlap": 0, "spread_ranks": [1, 3],
                         "max_spread": 0.1})


def test_signals_overlap_and_spread():
    named = {"dense": ["a", "b", "c"], "bm25": ["b", "d", "a"]}
    row = np.array([0.9, 0.95, 0.5, 0.7], dtype=np.float32)  # 청크 → 문서 0, 0, 1, 2
    sig = rewrite.signals(named, row, np.array([0, 0, 1, 2]), 3, GATE)
    assert sig["overlap"] == 1  # 상위 2개 {a, b} ∩ {b, d}
    assert sig["spread"] == pytest.approx(0.95 - 0.5)  # 문서 점수는 청크 최댓값, 1위 - 3위


@pytest.mark.parametrize("sig, expected", [
    ({"overlap": 0, "spread": 0.5}, True),
    ({"overlap": 1, "spread": 0.1}, True),
    ({"overlap": 1, "spread": 0.2}, False),
])
def test_needs_rewrite_when_any_signal_low(sig, expected):
    assert rewrite.needs_rewrite(sig, GATE) is expected


@pytest.mark.parametrize("raw, expected", [
    ("<thought>생각</thought>\n예산 감액 사유", "예산 감액 사유"),
    ("\n  예산 감액 사유  \n설명 줄", "예산 감액 사유"),
    ("<thought>끝나지 않은 생각", None),
    ("", None),
    ("가" * 11, None),
])
def test_parse_keeps_first_line_within_limit(raw, expected):
    assert rewrite.parse(raw, max_chars=10) == expected


def _cfg(tmp_path):
    return load_cfg(["+exp=exp013", f"paths.rewrites={(tmp_path / 'rw.json').as_posix()}"])


def test_rewrite_queries_calls_only_missing(tmp_path, monkeypatch):
    calls = []

    class Fake:
        def __init__(self, cfg):
            pass

        def call(self, query):
            calls.append(query)
            return {"raw": f"{query} 재작성", "seconds": 0.0, "usage": None}

    monkeypatch.setattr(rewrite, "Rewriter", Fake)
    cfg = _cfg(tmp_path)
    assert rewrite.rewrite_queries(cfg, {"q1": "가"}) == {"q1": "가 재작성"}
    assert rewrite.rewrite_queries(cfg, {"q1": "가", "q2": "나"}) == {"q1": "가 재작성",
                                                                      "q2": "나 재작성"}
    assert calls == ["가", "나"]


def test_load_rewrites_stops_on_different_basis(tmp_path):
    cfg = _cfg(tmp_path)
    saved = {"basis": {**rewrite.basis(cfg), "model": "other"}, "items": {}}
    (tmp_path / "rw.json").write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(SystemExit):
        rewrite.load_rewrites(cfg)


def test_retriever_adds_rewrite_lists_after_original(tmp_path):
    cfg = _tmp_cfg(tmp_path, ["+exp=exp001", "retriever.fusion.depth=3",
                              "retriever.bm25.name=test",
                              "+retriever.rewrite={enabled: true, lists: [dense, bm25]}"])
    _write_text_index(tmp_path / "kure-v1-512" / "dev-small",
                      [("a", "예산 심사"), ("b", "국정감사 질의"), ("c", "법안 처리")],
                      [[0.9, 0.0], [0.5, 0.0], [0.1, 1.0]])
    ret = Retriever(cfg)
    row = ret.chunk_emb @ np.array([1.0, 0.0], dtype=np.float32)
    rw_row = ret.chunk_emb @ np.array([0.0, 1.0], dtype=np.float32)
    tokens, rw_tokens = ret.query_tokens(["국정감사 질의", "법안 처리"])
    named, _, _ = ret.lists(row, tokens, rewrite=(rw_row, rw_tokens))
    assert list(named) == ["dense", "bm25", "dense_rw", "bm25_rw"]
    assert named["dense_rw"][0] == "c"
    assert named["bm25_rw"] == rank_docs(ret.bm25.scores(rw_tokens), ret.bm25_ids, 3)
    fused, _, _ = ret.candidates(row, tokens, rewrite=(rw_row, rw_tokens))
    assert fused == rrf(list(named.values()), cfg.retriever.fusion.rrf_k, None)
    assert ret.lists(row, tokens)[0].keys() == {"dense", "bm25"}  # 재작성 없으면 그대로
