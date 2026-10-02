import numpy as np
from omegaconf import OmegaConf

from rag.generate import answer_start, best_chunks, build_messages, recipe, split_thought
from rag.index import load_cfg


def context(n, text, url="http://example/1"):
    return {"n": n, "text": text, "date": "2020년1월1일", "committee_name": "위원회",
            "meeting_number": "제1회", "session_number": "제2차", "original": url}


def test_best_chunks_picks_top_chunk_per_doc_in_rank_order():
    scores = np.array([0.1, 0.9, 0.5, 0.8, 0.7])
    doc_ids = np.array(["a", "a", "b", "c", "b"])
    assert best_chunks(scores, doc_ids, 2, pool=10) == [1, 3]
    assert best_chunks(scores, doc_ids, 3, pool=2) == [1, 3, 4]  # pool이 모자라면 전체 정렬


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
    meta = {"name": "idx", "n_chunks": 3}
    base = recipe(cfg, meta, stream=False)
    assert {"git_commit", "git_dirty", "embedding_model", "index", "chunk_pool", "context_docs",
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
