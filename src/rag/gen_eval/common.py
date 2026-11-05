"""생성 평가(S14) 공용: 질의 표본, 참조(정답 문서·answer.comment), 생성 기록 이어 쓰기.

질의는 평가 층(gen_eval.queries)의 dev 질의를 쓴다. test 층은 생성 단계 종료 1회에만 명시적
허용으로 쓴다(D-87, slices/46-gen-test.md).
"""

import json
import os
from pathlib import Path

import numpy as np
from langsmith.utils import tracing_is_enabled
from omegaconf import OmegaConf

from rag.eval.metrics import load_gold
from rag.index import ROOT, file_sha256, load_cfg

LAYERS = ("dev-small", "dev-full")
VOLATILE = ("git_commit", "git_dirty")  # 같은 설정의 이어 쓰기에서 달라도 되는 레시피 값


def sample_qids(qids: list[str], seed: int, n: int,
                exclude: frozenset[str] = frozenset()) -> list[str]:
    """qid를 정렬해 seed로 섞은 순서에서 exclude를 뺀 앞 n개. n을 늘려도 앞 표본이 유지된다."""
    qids = sorted(qids)
    order = (qids[i] for i in np.random.default_rng(seed).permutation(len(qids)))
    return [q for q in order if q not in exclude][:n]


def dev_queries(cfg) -> frozenset[str]:
    """judge 지시 개발에 쓴 질의(paths.gen_dev_queries의 모든 목록)."""
    lists = OmegaConf.to_container(OmegaConf.load(ROOT / cfg.paths.gen_dev_queries))
    return frozenset(q for qs in lists.values() for q in qs)


def check_test_layer(cfg) -> None:
    """test 층을 쓸 설정인지 라벨을 읽기 전에 본다. 재정렬 점수 경로는 search.queries로 정해져,
    어긋나면 dev 점수 파일을 읽는다."""
    g = cfg.gen_eval
    if not g.allow_test:
        raise SystemExit("gen_eval.queries=test는 gen_eval.allow_test=true가 있어야 쓴다 "
                         "(생성 단계 종료 시 1회, D-87)")
    if cfg.search.queries != "test" or not cfg.search.allow_test:
        raise SystemExit("gen_eval.queries=test는 search.queries=test "
                         "search.allow_test=true와 함께 쓴다")
    if g.n != g.test_n:
        raise SystemExit(f"test 층의 gen_eval.n은 {g.test_n}이다(D-87 결정 1): {g.n}")


def check_test_input(cfg, key: str) -> None:
    """S13 산출물이 실행 기록의 해시와 같은지 본다. 해시만 재고 내용은 쓰지 않는다(D-87 결정 6)."""
    want = cfg.gen_eval.test_inputs[key]
    digest = file_sha256(ROOT / want.path)
    if not digest.startswith(want.sha256):
        raise SystemExit(f"{want.path}의 SHA-256 {digest[:8]}이 S13 기록 {want.sha256}과 다르다. "
                         "멈추고 보고한다(D-87 결정 6)")


def check_test_baseline(cfg) -> None:
    """test 1회는 지금 기준 설정 하나로 돈다(D-87 결정 2). 결과를 바꾸는 설정이 별칭 current와
    다르거나 seed가 다르면 멈춘다. 기록 경로에 seed가 없어 다른 표본이 같은 파일에 이어 쓰인다."""
    want = load_cfg(["index.scope=full", "+exp=current"])
    keys = ("embedding", "retriever", "conditions", "prompt", "generator", "speakers", "judge")
    diff = [k for k in keys if OmegaConf.to_container(cfg[k], resolve=True)
            != OmegaConf.to_container(want[k], resolve=True)]
    if cfg.gen_eval.seed != want.gen_eval.seed:
        diff.append("gen_eval.seed")
    if diff:
        raise SystemExit(f"test 1회는 +exp=current 설정만 쓴다. 다른 설정: {', '.join(diff)}")


def check_test_run(cfg) -> None:
    """test 층이면 API를 부르기 전에 1회 실행의 제약을 본다. dev 층에서는 test 산출물을 읽지 않게
    search.queries만 본다."""
    g = cfg.gen_eval
    if g.queries != "test":
        if cfg.search.queries == "test":
            raise SystemExit("search.queries=test는 gen_eval.queries=test와 함께 쓴다")
        return
    check_test_layer(cfg)
    # 라이브러리는 *_TRACING_V2를 먼저 읽어, 변수 하나만 보면 다른 이름으로 켜진 추적을 놓친다
    if os.environ.get("LANGSMITH_TRACING") != "false" or tracing_is_enabled():
        raise SystemExit("test 1회는 LANGSMITH_TRACING=false로 실행한다. 추적을 켜는 다른 환경 "
                         "변수(*_TRACING_V2)도 없어야 한다(D-72, D-87 결정 7)")
    if g.gen_rep or cfg.judge.rep or g.contexts != "retrieved":
        raise SystemExit("test 1회는 반복 번호 0, gen_eval.contexts=retrieved로만 실행한다"
                         "(D-87 결정 2)")
    for key in ("query_emb_test", "rerank_pairs", "rerank_scores"):
        if g.test_inputs[key].path != cfg.paths[key]:
            raise SystemExit(f"paths.{key}({cfg.paths[key]})가 S13 산출물이 아니다. "
                             "+exp=current로 실행한다")
        check_test_input(cfg, key)
    check_test_input(cfg, "run")  # 유료 호출 뒤에 알면 늦다
    check_test_baseline(cfg)


def eval_qids(cfg) -> list[str]:
    """gen_eval.queries 층의 표본 qid. 판정용 층(dev-full)에서는 judge 지시 개발에 쓴 질의를 뺀다
    (D-47 결정 5, S22 결정 사항 1). dev-small은 개발 층이라 빼지 않는다. test 층은 허용을 본 뒤
    seed 순서의 앞 gen_eval.n개다(D-87 결정 1)."""
    layer = cfg.gen_eval.queries
    if layer == "test":
        check_test_layer(cfg)
        return sample_qids(list(load_gold(cfg, "test", allow_test=True).index),
                           cfg.gen_eval.seed, cfg.gen_eval.n)
    if layer not in LAYERS:
        raise SystemExit(f"gen_eval.queries는 {LAYERS} 또는 test다: {layer}")
    exclude = dev_queries(cfg) if layer == "dev-full" else frozenset()
    return sample_qids(list(load_gold(cfg, layer).index), cfg.gen_eval.seed, cfg.gen_eval.n,
                       exclude)


def load_refs(cfg, qids: list[str]) -> dict[str, dict]:
    """qid별 정답 문서와 answer.comment(응답 발언 원문). 주어진 qid만 남긴다."""
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
