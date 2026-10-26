import json

import numpy as np
import pytest

from rag.index import index_basis, load_cfg
from rag.retrieve import (
    Retriever,
    chunks_by_doc,
    condition_docs,
    conditions_first,
    dense_chunkings,
    dense_dirs,
    final_order,
    first_docs,
    load_dense,
    rank_docs,
    rank_with_pool,
    read_doc_ids,
    rerank_top,
    rrf,
    top_docs,
    weighted_doc_scores,
)
from rag.search import query_files, query_list, write_run


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


def test_pool_grows_before_full_sort():
    # 첫 묶음(30)에 문서 100개가 없다. 묶음을 키워 전체 정렬과 같은 결과를 낸다(S17)
    rng = np.random.default_rng(2)
    doc_ids = rng.integers(0, 400, 20000).astype(str)
    for _ in range(20):
        scores = rng.standard_normal(20000).astype(np.float32)
        full = first_docs(np.argsort(-scores, kind="stable"), doc_ids, 100)
        assert rank_with_pool(scores, doc_ids, 100, pool=30) == (full, False)


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


def test_test_queries_need_explicit_allow():
    for over in (["index.scope=full"], ["index.scope=dev-small", "search.allow_test=true"],
                 ["index.scope=full", "search.allow_test=true", "search.mode=export-queries"]):
        cfg = load_cfg(["search.queries=test", *over])
        with pytest.raises(SystemExit):
            query_files(cfg)
        with pytest.raises(SystemExit):
            query_list(cfg)


def test_test_queries_use_own_paths():
    cfg = load_cfg(["search.queries=test", "index.scope=full", "search.allow_test=true",
                    "+exp=exp017"])
    files = query_files(cfg)
    assert files["name"] == "test" and files["emb"].name == "queries-test.npz"
    assert files["emb"] != query_files(load_cfg(["index.scope=full", "+exp=exp017"]))["emb"]
    assert "test-full" in cfg.paths.rerank_pairs and "test-full" in cfg.paths.rerank_scores


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


def test_final_order_reranks_before_condition_filter():
    # 재정렬로 c가 1위가 되지만 최다 일치 문서 d가 앞으로 온다(EXP-017 순서)
    got = final_order(["a", "b", "c", "d"], {"d"}, {"a": 0.1, "b": 0.2, "c": 0.9}, 3)
    assert got == ["d", "c", "b", "a"]
    assert final_order(["a", "b", "c"], {"b"}) == ["b", "a", "c"]


def test_chunks_by_doc():
    got = chunks_by_doc(np.array(["x", "y", "x", "z", "y"]))
    assert {k: v.tolist() for k, v in got.items()} == {"x": [0, 2], "y": [1, 4], "z": [3]}


def test_weighted_doc_scores_by_chunk_rank():
    scores = np.array([0.9, 0.2, 0.5, 0.8, 0.7])
    chunk_doc = np.array([0, 0, 0, 1, 2])
    # 문서 0: 0.9 + 0.5 (합) / 0.9 + 0.1·0.5, 문서 1·2는 청크가 하나라 그 점수만
    np.testing.assert_allclose(weighted_doc_scores(scores, chunk_doc, 3, [1.0, 1.0]),
                               [1.4, 0.8, 0.7])
    np.testing.assert_allclose(weighted_doc_scores(scores, chunk_doc, 3, [1.0, 0.1]),
                               [0.95, 0.8, 0.7])


def test_weight_1_matches_max_ranking():
    rng = np.random.default_rng(0)
    chunk_doc = np.sort(rng.integers(0, 200, 3000))
    names = np.unique(chunk_doc).astype(str)
    _, inv = np.unique(chunk_doc, return_inverse=True)
    for _ in range(20):
        scores = rng.standard_normal(3000).astype(np.float32)
        got = top_docs(weighted_doc_scores(scores, inv, len(names), [1.0]), names, 10)
        assert got == rank_docs(scores, names[inv], 10)


def test_rrf_weights_favor_weighted_list():
    # 가중치 1이면 동점(앞 목록 우선), dense에 2를 주면 dense 1위가 확실히 앞선다
    assert rrf([["a", "b"], ["b", "a"]], 60, None, [1.0, 1.0]) == ["a", "b"]
    assert rrf([["b", "a"], ["a", "b"]], 60, None, [2.0, 1.0]) == ["b", "a"]
    assert rrf([["x"], ["y"], ["y"]], 60, None, [2.0, 1.0, 1.0]) == ["x", "y"]  # 2/61 = 1/61 + 1/61


def _write_index(d, doc_ids, emb):
    (d / "emb").mkdir(parents=True)
    lines = [json.dumps({"chunk_id": i, "doc_id": x}) for i, x in enumerate(doc_ids)]
    (d / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    np.save(d / "emb" / "part-00000.npy", emb)


def test_dense_dirs_follow_index_template():
    cfg = load_cfg(["+exp=exp011", "index.scope=dev-small"])
    dirs = dense_dirs(cfg)
    names = ["snowflake-ko-fixed-512-64", "snowflake-ko-fixed-256-32"]
    assert [d.parent.name for d in dirs] == names
    assert all(d.name == "dev-small" for d in dirs)
    assert len(dense_dirs(load_cfg(["+exp=exp009"]))) == 1


def test_dense_dirs_require_full_chunking_spec():
    for bad in ["[[256,32]]", "[{chunk_tokens: 256, overlap_tokens: 32}]"]:
        cfg = load_cfg(["+exp=exp011", f"retriever.extra_chunks={bad}"])
        with pytest.raises(ValueError):
            dense_dirs(cfg)


def test_load_dense_appends_in_order(tmp_path):
    base, extra = tmp_path / "a", tmp_path / "b"
    _write_index(base, ["a", "b"], np.ones((2, 3), dtype=np.float32))
    _write_index(extra, ["a", "a", "b"], np.zeros((3, 3), dtype=np.float32))
    ids, emb = load_dense([base, extra])
    assert ids.tolist() == ["a", "b", "a", "a", "b"]
    assert emb.shape == (5, 3) and emb[:2].sum() == 6 and emb[2:].sum() == 0


def test_write_run_refuses_different_content(tmp_path):
    path = tmp_path / "run.csv"
    rows = [{"qid": "q1", "rank": 1, "doc_id": "d1"}]
    assert write_run(path, rows, overwrite=False) == "씀"
    assert write_run(path, rows, overwrite=False) == "같은 내용, 그대로 둠"
    other = [{"qid": "q1", "rank": 1, "doc_id": "d2"}]
    with pytest.raises(SystemExit):
        write_run(path, other, overwrite=False)
    assert write_run(path, other, overwrite=True) == "씀"
    assert "d2" in path.read_text(encoding="utf-8")


def _write_text_index(d, rows, emb):
    (d / "emb").mkdir(parents=True)
    lines = [json.dumps({"chunk_id": i, "doc_id": doc, "text": text}, ensure_ascii=False)
             for i, (doc, text) in enumerate(rows)]
    (d / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    np.save(d / "emb" / "part-00000.npy", np.asarray(emb, dtype=np.float32))


def _tmp_cfg(tmp_path, overrides):
    slug_size = "${embedding.slug}-${chunking.chunk_tokens}"
    template = (tmp_path / slug_size / "${index.scope}").as_posix()
    cfg = load_cfg([f"paths.index_dir='{template}'", "index.scope=dev-small",
                    "retriever.top_k=2", "retriever.chunk_pool=null", *overrides])
    for d, c in zip(dense_dirs(cfg), dense_chunkings(cfg), strict=True):  # 인덱스 지문(S15)
        d.mkdir(parents=True, exist_ok=True)
        (d / "basis.json").write_text(json.dumps(index_basis(cfg, c)), encoding="utf-8")
    return cfg


def test_retriever_dense_ranks_by_max_chunk_across_indexes(tmp_path):
    cfg = _tmp_cfg(tmp_path, ["+retriever.extra_chunks=[{name: fixed, chunk_tokens: 256, "
                              "overlap_tokens: 32}]"])
    _write_text_index(tmp_path / "kure-v1-512" / "dev-small",
                      [("a", "x"), ("b", "y")], [[0.9, 0.0], [0.5, 0.0]])
    _write_text_index(tmp_path / "kure-v1-256" / "dev-small",
                      [("b", "y1"), ("c", "z")], [[1.0, 0.0], [0.1, 0.0]])
    ret = Retriever(cfg)
    row = ret.chunk_emb @ np.array([1.0, 0.0], dtype=np.float32)
    assert ret.rank(row) == ["b", "a"]  # b의 256 청크(1.0)가 a의 512 청크(0.9)보다 높다


def test_retriever_hybrid_fuses_dense_and_bm25(tmp_path):
    cfg = _tmp_cfg(tmp_path, ["+exp=exp001", "retriever.fusion.depth=3",
                              "retriever.bm25.name=test"])
    _write_text_index(tmp_path / "kure-v1-512" / "dev-small",
                      [("a", "예산 심사"), ("b", "국정감사 질의"), ("c", "법안 처리")],
                      [[0.9, 0.0], [0.5, 0.0], [0.1, 0.0]])
    ret = Retriever(cfg)
    row = ret.chunk_emb @ np.array([1.0, 0.0], dtype=np.float32)
    tokens = ret.query_tokens(["국정감사 질의"])[0]
    fused, matched, _ = ret.candidates(row, tokens)
    lexical = rank_docs(ret.bm25.scores(tokens), ret.bm25_ids, 3)
    assert fused == rrf([["a", "b", "c"], lexical], cfg.retriever.fusion.rrf_k, None)
    assert matched == set() and ret.rank(row, tokens) == fused[:2]


def test_retriever_explain_records_stage_ranks(tmp_path):
    cfg = _tmp_cfg(tmp_path, ["+exp=exp001", "retriever.fusion.depth=3",
                              "retriever.bm25.name=test"])
    _write_text_index(tmp_path / "kure-v1-512" / "dev-small",
                      [("a", "예산 심사"), ("b", "국정감사 질의"), ("c", "법안 처리")],
                      [[0.9, 0.0], [0.5, 0.0], [0.1, 0.0]])
    ret = Retriever(cfg)
    row = ret.chunk_emb @ np.array([1.0, 0.0], dtype=np.float32)
    tokens = ret.query_tokens(["국정감사 질의"])[0]
    docs, stages = ret.explain(row, tokens)
    assert docs == ret.candidates(row, tokens)[0][:2]
    assert [s["dense_rank"] for s in stages] == [{"a": 1, "b": 2, "c": 3}[d] for d in docs]
    assert stages[0]["rrf_score"] >= stages[1]["rrf_score"] and "bm25_rank" in stages[0]


def test_read_doc_ids_matches_full_parse(tmp_path):
    # 본문에 따옴표·역슬래시·doc_id 문자열이 들어도 줄 앞부분만 읽은 값이 json.loads와 같다(S20)
    rows = [{"chunk_id": 0, "doc_id": "d1", "start": 0, "text": '그는 "doc_id": "x" 라고 \\ 썼다'},
            {"chunk_id": 1, "doc_id": 'd"2\\', "start": 5, "text": "끝"}]
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    (tmp_path / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert read_doc_ids(tmp_path).tolist() == [r["doc_id"] for r in rows]


def test_read_doc_ids_stops_when_format_differs(tmp_path):
    for row in [{"doc_id": "d1", "chunk_id": 0}, {"chunk_id": 3, "doc_id": "d1"}]:
        (tmp_path / "chunks.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit, match=":1: 줄이"):
            read_doc_ids(tmp_path)


def test_load_dense_stops_when_rows_differ(tmp_path):
    base = tmp_path / "a"
    _write_index(base, ["a", "b"], np.ones((1, 3), dtype=np.float32))
    with pytest.raises(SystemExit, match="임베딩 1행"):
        load_dense([base])


def test_retriever_checks_index_basis(tmp_path):
    cfg = _tmp_cfg(tmp_path, [])
    d = tmp_path / "kure-v1-512" / "dev-small"
    _write_text_index(d, [("a", "x")], [[1.0, 0.0]])
    basis = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    (d / "basis.json").write_text(json.dumps({**basis, "revision": "old"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="revision"):  # 다른 모델 revision으로 만든 인덱스
        Retriever(cfg)
    (d / "basis.json").unlink()
    with pytest.raises(SystemExit, match="adopt_basis"):
        Retriever(cfg)


def test_query_cache_basis_is_checked_on_read(tmp_path):
    from omegaconf import OmegaConf

    from rag.retrieve import (
        adopt_query_basis,
        query_basis_path,
        read_query_emb,
        save_query_emb,
    )
    cfg = load_cfg(["+exp=exp017"])
    path = tmp_path / "queries-full.npz"
    save_query_emb(cfg, path, ["q1", "q2"], np.eye(2, dtype=np.float32))
    qids, emb = read_query_emb(cfg, path)  # 만든 설정과 같으면 읽는다
    assert qids == ["q1", "q2"] and emb.shape == (2, 2)
    for key, value in [("revision", "other"), ("query_prompt", "passage: ")]:
        with pytest.raises(SystemExit, match=key):
            read_query_emb(OmegaConf.merge(cfg, {"embedding": {key: value}}), path)

    query_basis_path(path).unlink()  # 지문 없는 기존 캐시
    with pytest.raises(SystemExit, match="adopt_basis"):
        read_query_emb(cfg, path)
    assert adopt_query_basis(cfg, path) == "씀"
    assert adopt_query_basis(cfg, path) == "이미 있음, 같음"
    with pytest.raises(SystemExit, match="query_prompt"):  # 다른 설정으로 받아들이지 않는다
        adopt_query_basis(load_cfg([]), path)
    with pytest.raises(SystemExit, match="없다"):
        adopt_query_basis(cfg, tmp_path / "none.npz")


def test_query_embeddings_never_embeds_locally(tmp_path, monkeypatch):
    import rag.search as search
    from rag.retrieve import save_query_emb
    cfg = load_cfg([])
    path = tmp_path / "queries-dev-small.npz"
    save_query_emb(cfg, path, ["q1"], np.ones((1, 2), dtype=np.float32))
    monkeypatch.setattr(search, "embed_queries", lambda *_: pytest.fail("로컬 임베딩"))
    assert search.query_embeddings(cfg, ["q1"], path).sum() == 2  # 캐시
    with pytest.raises(SystemExit, match="덮어쓰지 않는다"):
        search.query_embeddings(cfg, ["q1", "q2"], path)
    assert np.load(path)["emb"].sum() == 2  # 캐시는 그대로
    new = tmp_path / "queries-full.npz"
    with pytest.raises(SystemExit, match="캐시가 없다"):
        search.query_embeddings(cfg, ["q1"], new)
    assert not new.exists()
