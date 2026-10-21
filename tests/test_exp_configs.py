"""configs/exp/* 전부로 합성 인덱스에서 질의 하나를 끝까지 낸다(S16, 리뷰 B-13).

평가(rag.search의 finish)와 생성(explain)이 같은 최종 순위를 내는지도 함께 본다.
"""

import json
from pathlib import Path

import numpy as np
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
