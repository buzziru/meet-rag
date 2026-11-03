import json

import numpy as np
import pytest
from omegaconf import OmegaConf

from rag.generate import build_messages, recipe
from rag.index import load_cfg
from rag.llm import answer_start, split_thought
from rag.retrieve import ChunkStore, best_chunks
from rag.speakers import render


def context(n, text, url="http://example/1"):
    return {"n": n, "text": text, "date": "2020년1월1일", "committee_name": "위원회",
            "meeting_number": "제1회", "session_number": "제2차", "original": url}


def test_best_chunks_picks_top_chunk_per_doc_in_given_order():
    scores = np.array([0.1, 0.9, 0.5, 0.8, 0.7])
    doc_chunks = {"a": np.array([0, 1]), "b": np.array([2, 4]), "c": np.array([3])}
    assert best_chunks(scores, doc_chunks, ["c", "b", "a"]) == [3, 4, 1]


def test_chunk_store_reads_rows_across_indexes(tmp_path):
    dirs = []
    for name, rows in [("idx-512", ["a0", "a1"]), ("idx-256", ["b0", "b1", "b2"])]:
        d = tmp_path / name / "full"
        d.mkdir(parents=True)
        lines = [json.dumps({"chunk_id": i, "doc_id": "d", "text": s}, ensure_ascii=False)
                 for i, s in enumerate(rows)]
        (d / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        dirs.append(d)
    store = ChunkStore(dirs)
    assert [store.get(i)["text"] for i in range(5)] == ["a0", "a1", "b0", "b1", "b2"]
    assert store.get(3)["index"] == "idx-256" and store.get(3)["chunk_id"] == 1
    # 여러 번호를 한 번에 읽는다(후보 쌍, G2). 번호는 load_dense와 같다
    assert store.texts({1, 2, 4}) == {1: "a1", 2: "b0", 4: "b2"}


def test_messages_number_contexts_without_urls():
    cfg = load_cfg(["index.scope=full"])
    msgs = build_messages(cfg.prompt, [context(1, "첫 근거"), context(2, "둘째 근거")], "질문?")
    assert [m["role"] for m in msgs] == ["system", "user"]
    user = msgs[1]["content"]
    assert "[1] 2020년1월1일 위원회 제1회 제2차\n첫 근거" in user
    assert "[2]" in user and user.rstrip().endswith("질문?")
    assert "http" not in user


def test_messages_render_speakers_only_when_field_present():
    """S29: speakers가 없으면 메시지가 S25와 같은 문자열이고, 있으면 text 자리에 렌더링한다."""
    cfg = load_cfg(["index.scope=full"])
    plain = context(1, "질문입니다. 답변입니다.")
    want = ("[근거]\n[1] 2020년1월1일 위원회 제1회 제2차\n질문입니다. 답변입니다.\n\n"
            "[질문]\n질문?")
    assert build_messages(cfg.prompt, [plain], "질문?")[1]["content"] == want
    spk = {"questioners": [{"name": "홍길동", "position": "위원", "affiliation": ""}],
           "answerers": [{"name": "김철수", "position": "장관", "affiliation": "국토교통부"}],
           "spans": [{"role": "answer", "start": 7, "end": 13, "name": "김철수",
                      "position": "장관", "affiliation": "국토교통부"}]}
    user = build_messages(cfg.prompt, [{**plain, "speakers": spk}], "질문?")[1]["content"]
    assert ("[1] 2020년1월1일 위원회 제1회 제2차\n"
            "질의자: 홍길동 위원 / 답변자: 김철수 국토교통부 장관\n"
            "질문입니다. 〈답변 김철수 장관〉답변입니다.〈/답변〉") in user


def test_recipe_records_speakers_mode_only_when_on():
    meta = {"names": ["idx"], "n_chunks": 3}
    assert "speakers" not in recipe(load_cfg(["index.scope=full"]), meta, stream=False)
    on = recipe(load_cfg(["index.scope=full", "speakers.mode=marks"]), meta, stream=False)
    assert on["speakers"] == {"mode": "marks", "repeat_min_chars": 21}


def test_prompt_version_file_loads():
    assert load_cfg(["prompt=v1"]).prompt.version == "v1"


def test_recipe_tracks_prompt_content():
    cfg = load_cfg(["index.scope=full"])
    meta = {"names": ["idx"], "n_chunks": 3}
    base = recipe(cfg, meta, stream=False)
    assert {"git_commit", "git_dirty", "embedding_model", "index", "retriever", "context_docs",
            "prompt_version", "prompt_sha256", "model", "params", "stream"} <= set(base)
    assert base["params"]["temperature"] == 0.0

    changed = OmegaConf.merge(cfg, {"prompt": {"system": "다른 지시"}})
    assert recipe(changed, meta, stream=False)["prompt_sha256"] != base["prompt_sha256"]
    assert recipe(cfg, meta, stream=True)["stream"] is True


def test_split_thought():
    assert split_thought("<thought>생각</thought>\n답변 [1]") == ("생각", "답변 [1]")
    assert split_thought("바로 답변") == ("", "바로 답변")
    assert split_thought("<thought>끝나지 않음") == ("끝나지 않음", "")
    assert answer_start("<tho") is None
    assert answer_start("<thought>생각</thought>답") == len("<thought>생각</thought>")
    assert answer_start("바로") == 0


def test_recipe_tracks_condition_settings_and_rerank_scores():
    cfg = load_cfg(["index.scope=full", "+exp=exp017"])
    meta = {"names": ["idx"], "n_chunks": 3, "rerank_scores_sha256": "a"}
    base = recipe(cfg, meta, stream=False)
    exclude = load_cfg(["index.scope=full", "+exp=exp017", "conditions.name_exclude=['정부']"])
    assert recipe(exclude, meta, stream=False)["conditions"] != base["conditions"]
    titles = OmegaConf.merge(cfg, {"ingest": {"name_titles": ["위원"]}})
    assert recipe(titles, meta, stream=False)["name_titles"] == ["위원"]
    assert recipe(cfg, {**meta, "rerank_scores_sha256": "b"}, stream=False) != base


def test_recipe_records_query_embedding_basis():
    rec = recipe(load_cfg(["index.scope=full", "+exp=exp017"]),
                 {"names": ["idx"], "n_chunks": 3}, stream=False)
    assert rec["embedding_revision"] == "55ec6e9358a56d56af759bc8372e970caf8c305f"
    assert rec["query_prompt"] == "query: "


def test_pipeline_client_uses_generator_timeout_and_retries(monkeypatch):
    from types import SimpleNamespace

    import rag.generate as g
    made = {}
    monkeypatch.setattr(g, "Retriever", lambda cfg: SimpleNamespace(
        dense_ids=[], dirs=[], use_cond=False, use_rerank=False))
    monkeypatch.setattr(g, "chunks_by_doc", lambda ids: {})
    monkeypatch.setattr(g, "ChunkStore", lambda dirs: SimpleNamespace(names=[], bounds=[0]))
    monkeypatch.setattr(g, "corpus_meta", lambda cfg: [])
    monkeypatch.setattr(g, "require_env", lambda name: "key")
    monkeypatch.setattr(g, "OpenAI", lambda **kw: made.update(kw) or "client")
    monkeypatch.setattr(g, "wrap_openai", lambda c: c)
    g.Pipeline(load_cfg(["index.scope=full"]))
    # SDK 기본값(600초, 2회) 대신 generator 설정 값(D-57 결정 1)
    assert made["timeout"] == 120 and made["max_retries"] == 1


def test_generate_records_finish_reason():
    from types import SimpleNamespace

    from rag.generate import Pipeline

    def chunk(content=None, finish=None, usage=None):
        choices = [] if usage else [SimpleNamespace(delta=SimpleNamespace(content=content),
                                                    finish_reason=finish)]
        return SimpleNamespace(choices=choices, usage=usage, provider="p")

    usage = SimpleNamespace(model_dump=lambda: {"completion_tokens": 2})
    stream = [chunk("답변"), chunk("이다", "length"), chunk(usage=usage)]
    pipe = object.__new__(Pipeline)
    pipe.cfg = load_cfg(["index.scope=full"])
    pipe.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: iter(stream))))
    out = Pipeline.generate.__wrapped__(pipe, [], True, False)
    assert out["finish_reason"] == "length" and out["answer"] == "답변이다"


def _store(tmp_path, rows):
    d = tmp_path / "snowflake-fixed-256" / "full"
    d.mkdir(parents=True)
    with (d / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for i, (doc, start, text) in enumerate(rows):
            f.write(json.dumps({"chunk_id": i, "doc_id": doc, "start": start,
                                "end": start + len(text), "text": text}) + "\n")
    return ChunkStore([d])


def test_chunk_store_window_merges_overlap_and_stops_at_document_edge(tmp_path):
    store = _store(tmp_path, [("a", 0, "abcd"), ("b", 0, "0123"), ("b", 2, "2345"),
                              ("b", 4, "4567"), ("c", 0, "xy")])
    assert store.window(2, 0)["text"] == "2345"
    w = store.window(2, 1)
    assert (w["text"], w["start"], w["end"], w["chunk_id"]) == ("01234567", 0, 8, 2)
    assert store.window(1, 1)["text"] == "012345"  # 앞은 다른 문서라 붙이지 않는다
    assert store.window(3, 5)["text"] == "01234567"  # 뒤 문서와 파일 끝을 넘지 않는다
    assert store.window(4, 1)["text"] == "xy"


@pytest.mark.parametrize("expand,first", [({"top": 0, "chunks": 0}, "2345"),
                                          ({"top": 1, "chunks": 1}, "01234567")])
def test_retrieve_expands_only_top_contexts_and_marks_follow_window(tmp_path, expand, first):
    import rag.generate as g
    store = _store(tmp_path, [("b", 0, "0123"), ("b", 2, "2345"), ("b", 4, "4567"),
                              ("c", 0, "wxyz"), ("c", 2, "yz01")])
    pipe = object.__new__(g.Pipeline)
    pipe.store, pipe.speakers = store, "marks"
    pipe.expand = OmegaConf.create(expand)
    pipe.doc_chunks = {"b": np.array([0, 1, 2]), "c": np.array([3, 4])}
    meta = {k: "" for k in g.CONTEXT_META}
    pipe.doc_meta = {"b": meta, "c": meta}
    pipe.doc_speakers = {d: {"questioners": [], "answerers": []} for d in "bc"}
    span = {"role": "answer", "name": "김", "affiliation": "", "position": "장관"}
    pipe.spans = {"b": [{**span, "start": 0, "end": 3}], "c": [{**span, "start": 0, "end": 3}]}
    scores = np.array([0, 1, 0, 1, 0], dtype=float)
    pipe.rank = lambda query, q_emb, qid=None: (scores, ["b", "c"], [{}, {}])
    b, c = pipe.retrieve("q", None, 2)
    assert (b["text"], c["text"]) == (first, "wxyz")  # 2위 근거는 청크 하나 그대로다
    # 표지 위치는 넓어진 본문 기준이다. 확장 전에는 청크 시작(2) 앞이 잘려 청크의 첫 글자만 남는다
    want = (0, 3) if expand["top"] else (0, 1)
    got = b["speakers"]["spans"][0]
    assert (got["start"], got["end"]) == want
    body = render(b).split("\n", 1)[1]
    assert body.replace("〈답변 김 장관〉", "").replace("〈/답변〉", "") == first


def test_pipeline_rejects_half_set_context_expand(monkeypatch):
    from types import SimpleNamespace

    import rag.generate as g
    monkeypatch.setattr(g, "Retriever", lambda cfg: SimpleNamespace(
        dense_ids=[], dirs=[], use_cond=False, use_rerank=False))
    monkeypatch.setattr(g, "chunks_by_doc", lambda ids: {})
    monkeypatch.setattr(g, "ChunkStore", lambda dirs: SimpleNamespace(names=[], bounds=[0]))
    monkeypatch.setattr(g, "corpus_meta", lambda cfg: [])
    with pytest.raises(SystemExit, match="context_expand"):
        g.Pipeline(load_cfg(["index.scope=full", "generator.context_expand.top=1"]))
