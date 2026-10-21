import json

import numpy as np
from omegaconf import OmegaConf

from rag.generate import (
    ChunkStore,
    answer_start,
    best_chunks,
    build_messages,
    recipe,
    split_thought,
)
from rag.index import load_cfg


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


def test_messages_number_contexts_without_urls():
    cfg = load_cfg(["index.scope=full"])
    msgs = build_messages(cfg.prompt, [context(1, "첫 근거"), context(2, "둘째 근거")], "질문?")
    assert [m["role"] for m in msgs] == ["system", "user"]
    user = msgs[1]["content"]
    assert "[1] 2020년1월1일 위원회 제1회 제2차\n첫 근거" in user
    assert "[2]" in user and user.rstrip().endswith("질문?")
    assert "http" not in user


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
