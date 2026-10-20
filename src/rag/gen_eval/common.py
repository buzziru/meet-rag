"""생성 평가(S14) 공용: 질의 표본, 참조(정답 문서·answer.comment), 생성 기록 이어 쓰기.

질의는 평가 층(gen_eval.queries)의 dev 질의만 쓴다. test 층은 받지 않는다.
"""

import json
from pathlib import Path

import numpy as np

from rag.eval.metrics import load_gold
from rag.index import ROOT

LAYERS = ("dev-small", "dev-full")
VOLATILE = ("git_commit", "git_dirty")  # 같은 설정의 이어 쓰기에서 달라도 되는 레시피 값


def sample_qids(qids: list[str], seed: int, n: int) -> list[str]:
    """qid를 정렬해 seed로 섞은 순서의 앞 n개. n을 늘려도 앞 표본이 유지된다."""
    qids = sorted(qids)
    return [qids[i] for i in np.random.default_rng(seed).permutation(len(qids))[:n]]


def eval_qids(cfg) -> list[str]:
    """gen_eval.queries 층의 표본 qid."""
    layer = cfg.gen_eval.queries
    if layer not in LAYERS:
        raise SystemExit(f"gen_eval.queries는 {LAYERS} 중 하나다: {layer}")
    return sample_qids(list(load_gold(cfg, layer).index), cfg.gen_eval.seed, cfg.gen_eval.n)


def load_refs(cfg, qids: list[str]) -> dict[str, dict]:
    """qid별 정답 문서와 answer.comment(응답 발언 원문). 주어진 dev qid만 남긴다."""
    keep, refs = set(qids), {}
    with (ROOT / cfg.paths.queries).open(encoding="utf-8") as f:
        for q in map(json.loads, f):
            if q["qid"] in keep:
                refs[q["qid"]] = {"doc_id": q["doc_id"], "answer_comment": q["answer_comment"]}
    return refs


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stable(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in VOLATILE}


def done_qids(path: Path, rec: dict) -> set[str]:
    """이미 쓴 qid. 기존 기록의 레시피가 지금 설정과 다르면 멈춘다(덮어쓰기·섞어 쓰기 방지)."""
    if not path.exists():
        return set()
    rows = read_jsonl(path)
    for r in rows:
        if stable(r["recipe"]) != stable(rec):
            raise SystemExit(f"{path.relative_to(ROOT)}의 기록이 지금 설정과 다른 레시피로 "
                             f"만들어졌다(qid {r['qid']}). 경로나 설정을 확인한다")
    return {r["qid"] for r in rows}
