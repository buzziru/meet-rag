"""configs/exp/* 전부로 합성 인덱스에서 질의 하나를 끝까지 낸다(S16, 리뷰 B-13).

평가(rag.search의 finish)와 생성(explain)이 같은 최종 순위를 내는지도 함께 본다.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from test_search import _tmp_cfg, _write_text_index

from rag.generate import Pipeline
from rag.index import ROOT, load_cfg
from rag.retrieve import Retriever, dense_dirs

EXPS = sorted(p.stem for p in (ROOT / "configs" / "exp").glob("exp*.yaml"))

# 문서 a~f. b·c는 국방위원회 2020년 회의라 아래 조건 두 필드가 모두 맞고, d는 위원회만 맞는다
DOCS = [("a", "예산 심사", "2019년3월2일(화)", "기획재정위원회"),
        ("b", "국정감사 질의", "2020년10월5일(월)", "국방위원회"),
        ("c", "법안 처리", "2020년11월3일(화)", "국방위원회"),
        ("d", "회의 개회", "2018년5월1일(화)", "국방위원회"),
        ("e", "결산 보고", "2017년8월1일(화)", "교육위원회"),
        ("f", "업무 보고", "2016년2월1일(월)", "외교통일위원회")]
CONDS = {"committee_name": ["국방위원회"], "date": ["2020"]}
EMB = [[0.9, 0.1], [0.5, 0.5], [0.1, 0.9], [0.3, 0.7], [0.7, 0.3], [0.2, 0.2]]


def _world(tmp_path: Path, overrides: list[str]):
    corpus = tmp_path / "corpus.jsonl"
    with corpus.open("w", encoding="utf-8", newline="\n") as f:
        for doc, text, date, committee in DOCS:
            f.write(json.dumps({
                "doc_id": doc, "context": text, "date": date, "committee_name": committee,
                "meeting_name": "상임위원회", "generation_number": "21",
                "meeting_number": "제380회", "session_number": "제1차", "agenda": "",
                "questioners": [], "answerers": []},
                ensure_ascii=False) + "\n")
    cfg = _tmp_cfg(tmp_path, [f"paths.corpus='{corpus.as_posix()}'", *overrides])
    for d in dense_dirs(cfg):  # 기본 청크와 추가 청크 인덱스에 같은 문서를 둔다
        _write_text_index(d, [(doc, text) for doc, text, *_ in DOCS], EMB)
    return cfg


def _query(ret: Retriever):
    row = ret.chunk_emb @ np.array([0.6, 0.4], dtype=np.float32)
    tokens = ret.query_tokens(["국정감사 질의"])
    return row, tokens[0] if tokens else None


@pytest.mark.parametrize("exp", EXPS)
def test_exp_config_final_order_matches_explain(tmp_path, exp):
    cfg = _world(tmp_path, [f"+exp={exp}", "retriever.bm25.name=test"])
    ret = Retriever(cfg)
    row, tokens = _query(ret)
    conds = CONDS if ret.use_cond else None
    rerank = ({d: float(i) for i, (d, *_) in enumerate(DOCS)} if ret.use_rerank else None)
    fused, matched, _ = ret.candidates(row, tokens, conds)
    docs = ret.final(fused, matched, rerank)  # rag.search의 finish와 같은 호출
    assert len(docs) == cfg.retriever.top_k
    assert ret.explain(row, tokens, conds, rerank=rerank)[0] == docs


def _search_world(tmp_path, monkeypatch, overrides):
    """합성 인덱스 위에서 rag.search.search를 돌릴 수 있게 질의 하나의 입력을 바꿔 끼운다.
    순위·후보 쌍 파일은 search의 ROOT를 tmp_path로 바꿔 그 아래 config 경로에 쓴다."""
    from rag import search
    cfg = _world(tmp_path, [*overrides, "retriever.bm25.name=test"])
    rerank = {d: float(i) for i, (d, *_) in enumerate(DOCS)}
    monkeypatch.setattr(search, "ROOT", tmp_path)
    monkeypatch.setattr(search, "query_list", lambda cfg: (["q1"], tmp_path / "q.jsonl"))
    monkeypatch.setattr(search, "read_texts", lambda path, qids: ["국정감사 질의"])
    monkeypatch.setattr(search, "query_embeddings",
                        lambda cfg, qids, path: np.array([[0.6, 0.4]], dtype=np.float32))
    monkeypatch.setattr(search, "build_extractor",
                        lambda cfg: type("Ex", (), {"extract": lambda self, t: CONDS})())
    monkeypatch.setattr(search, "read_rerank_scores", lambda cfg: {"q1": rerank})
    return cfg, rerank


@pytest.mark.parametrize("exp", ["exp014", "exp017"])  # 재정렬 없음·있음(검색 기준)
def test_search_writes_explain_order(tmp_path, monkeypatch, exp):
    """rag.search.search가 쓴 순위 파일이 생성 경로(explain)와 같은 순서다(테스트 리뷰 T1-4)."""
    from rag.search import search
    cfg, rerank = _search_world(tmp_path, monkeypatch, [f"+exp={exp}"])
    search(cfg)
    run = pd.read_csv(next((tmp_path / cfg.paths.runs_dir).glob("*.csv")))
    ret = Retriever(cfg)
    row, tokens = _query(ret)
    want = ret.explain(row, tokens, CONDS if ret.use_cond else None,
                       rerank=rerank if ret.use_rerank else None)[0]
    assert run["doc_id"].tolist() == want


def test_search_rerank_pairs_are_fused_head(tmp_path, monkeypatch):
    from rag.search import search
    cfg, _ = _search_world(tmp_path, monkeypatch, ["+exp=exp017", "search.mode=rerank-pairs"])
    search(cfg)
    pairs = (tmp_path / cfg.paths.rerank_pairs).read_text(encoding="utf-8").splitlines()
    ret = Retriever(cfg)
    row, tokens = _query(ret)
    fused, _, _ = ret.candidates(row, tokens, CONDS)
    assert [json.loads(p)["doc_id"] for p in pairs] == fused[: cfg.retriever.rerank.depth]
    assert not (tmp_path / cfg.paths.runs_dir).exists()  # 쌍만 쓰고 순위 파일은 쓰지 않는다


def test_rrf_condition_list_and_best_filter(tmp_path):
    cfg = _world(tmp_path, ["+exp=exp004", "retriever.bm25.name=test",
                            "retriever.fusion.depth=6"])
    ret = Retriever(cfg)
    row, tokens = _query(ret)
    named, matched, _ = ret.lists(row, tokens, CONDS)
    assert list(named) == ["dense", "bm25", "conditions"]
    # min_fields 2: 위원회만 맞은 d는 조건 목록에 들지 않는다. b·c는 dense 문서 점수 순
    assert named["conditions"] == ["b", "c"]
    assert matched == {"b", "c"}
    assert ret.final(ret.fuse(named), matched) == ["b", "c"]


def test_generate_refuses_rewrite():
    with pytest.raises(SystemExit, match="rewrite"):
        Pipeline(load_cfg(["index.scope=full", "+exp=exp013"]))


def test_prompts_hold_their_refusal_phrase():
    for p in sorted((ROOT / "configs" / "prompt").glob("*.yaml")):
        prompt = load_cfg([f"prompt={p.stem}"]).prompt
        assert prompt.refusal and prompt.refusal in prompt.system, p.name


def test_current_alias_composes_as_its_baseline_exp():
    """지금 기준의 별칭(configs/exp/current.yaml)이 가리키는 EXP가 있고, 같은 설정으로 조립되며,
    DECISIONS 머리 줄과 같은 EXP를 적는지 본다. 기준은 이 두 곳에만 둔다(ADR-0076). 값은 config에서
    읽어 기준이 바뀌어도 이 테스트는 고치지 않는다(PR #181 리뷰)."""
    from omegaconf import OmegaConf

    from rag.generate import recipe

    alias = OmegaConf.load(ROOT / "configs" / "exp" / "current.yaml")
    target = next(d for d in alias.defaults if d != "_self_")
    assert (ROOT / "configs" / "exp" / f"{target}.yaml").exists()
    header = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8").splitlines()[2]
    assert f"EXP-{target.removeprefix('exp')}" in header

    cfg = load_cfg(["index.scope=full", "+exp=current"])
    base = load_cfg(["index.scope=full", f"+exp={target}"])
    # 쓰지 않는 보간(rewriter 등)은 풀지 않고 비교한다
    assert OmegaConf.to_container(cfg) == OmegaConf.to_container(base)
    rec = recipe(cfg, {"names": ["idx"], "n_chunks": 1}, stream=False)
    assert rec["prompt_version"] == cfg.prompt.version
    assert (ROOT / "configs" / "prompt" / f"{cfg.prompt.version}.yaml").exists()
    assert f"-{cfg.prompt.version}-" in cfg.paths.gen_runs
    assert f"-{cfg.prompt.version}-" in cfg.paths.gen_judge
