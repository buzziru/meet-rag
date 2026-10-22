"""상위 후보를 다시 점수 매긴다(H2, EXP-005).

후보 쌍 파일(`rag.search search.mode=rerank-pairs`)을 읽어 점수 파일을 쓴다.
- backend jev: 질의 하나의 후보를 한 요청에 묶어 Jev(OpenRouter Decisions API)의 score 질문으로
  채점한다. 응답은 요청 본문 해시로 저장해 다시 실행할 때 쓴다. 질의당 지연·비용도 남긴다.
  캐시에 없어 실제로 보낸 요청은 LangSmith로 추적한다(요청 본문, 응답, 지연, 오류)
- backend cross-encoder: 쌍마다 점수(score), 질의당 재정렬 시간(latency). KURE-Reranker-nano
  CPU 지연 측정에 썼다(EXP-005 실행 기록)
인자는 Hydra override.
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
from pathlib import Path

import numpy as np
import torch
from langsmith import traceable
from langsmith.run_trees import get_cached_client
from sentence_transformers import CrossEncoder

from rag.index import ROOT, load_cfg, pinned, refuse_existing, write_guarded  # .env를 읽는다
from rag.retrieve import rerank_basis, rerank_basis_path


def load_model(rr) -> CrossEncoder:
    if rr.threads:
        torch.set_num_threads(rr.threads)
    return CrossEncoder(rr.model, revision=pinned(rr), max_length=rr.max_length,
                        device=rr.device, model_kwargs={"dtype": getattr(torch, rr.dtype)})


def read_pairs(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def write_basis(cfg, overwrite: bool) -> str:
    """점수 파일 옆에 만든 설정(지문)을 쓴다. 읽는 쪽(rag.retrieve)은 device·dtype을 보지 않는다."""
    rr = cfg.retriever.rerank
    basis = rerank_basis(cfg)
    if rr.backend != "jev":
        basis |= {"device": rr.device, "dtype": rr.dtype}
    text = json.dumps(basis, ensure_ascii=False, indent=2) + "\n"
    return write_guarded(rerank_basis_path(cfg), text, overwrite)


def write_scores(cfg, rows: list[dict]) -> None:
    text = "".join(json.dumps(r) + "\n" for r in rows)
    state = write_guarded(ROOT / cfg.paths.rerank_scores, text, cfg.search.overwrite)
    print(f"{len(rows):,} scores -> {cfg.paths.rerank_scores} ({state}), "
          f"basis {write_basis(cfg, cfg.search.overwrite)}")


def score(cfg) -> None:
    rr = cfg.retriever.rerank
    pairs = read_pairs(ROOT / cfg.paths.rerank_pairs)
    model = load_model(rr)
    start = time.perf_counter()
    scores = model.predict([(p["query"], p["text"]) for p in pairs], batch_size=rr.batch_size)
    elapsed = time.perf_counter() - start
    write_scores(cfg, [{"qid": p["qid"], "doc_id": p["doc_id"], "score": float(s)}
                       for p, s in zip(pairs, scores, strict=True)])
    print(f"{elapsed:.1f}s, {len(pairs) / elapsed:.1f} pairs/s")


def latency(cfg) -> None:
    """질의 n개를 하나씩 재정렬해 질의당 시간(초)을 잰다. 첫 질의는 준비 실행으로 뺀다."""
    rr = cfg.retriever.rerank
    pairs = read_pairs(ROOT / cfg.paths.rerank_pairs)
    by_qid = [list(g) for _, g in groupby(pairs, key=lambda p: p["qid"])]
    rng = np.random.default_rng(rr.latency.seed)
    picked = [by_qid[i] for i in rng.choice(len(by_qid), rr.latency.n_queries + 1, replace=False)]
    model = load_model(rr)
    times = []
    for group in picked:
        start = time.perf_counter()
        model.predict([(p["query"], p["text"]) for p in group], batch_size=rr.batch_size)
        times.append(time.perf_counter() - start)
    t = np.array(times[1:])
    result = {"device": rr.device, "threads": torch.get_num_threads(), "dtype": rr.dtype,
              "n_queries": len(t), "pairs_per_query": len(picked[1]),
              "mean": float(t.mean()), "p50": float(np.percentile(t, 50)),
              "p95": float(np.percentile(t, 95)), "max": float(t.max())}
    state = write_guarded(ROOT / cfg.paths.rerank_latency, json.dumps(result, indent=2) + "\n",
                          cfg.search.overwrite)
    print(json.dumps(result, ensure_ascii=False), f"({state})")


def jev_body(group: list[dict], jv) -> dict:
    """질의 하나와 후보들을 공유 state에 두고 후보마다 score 질문 하나를 붙인다."""
    candidates = {str(i): p["text"] for i, p in enumerate(group)}
    state = {"query": group[0]["query"], "candidates": candidates}
    questions = {f"c{i}": {"type": "score", "instructions": f"후보 {i}: {jv.instructions}",
                           "criteria": list(jv.levels)} for i in range(len(group))}
    return {"model": jv.model, "state": state, "questions": questions}


@traceable(run_type="llm", name="jev_rerank", process_inputs=lambda i: {"body": i["body"]})
def jev_post(body: dict, raw: str, jv) -> dict:
    """요청 본문 raw(body를 직렬화한 것)를 보내 응답을 받는다. 추적 입력에는 body만 남긴다."""
    headers = {"Authorization": f"Bearer {os.environ[jv.api_key_env]}",
               "Content-Type": "application/json"}
    req = urllib.request.Request(jv.url, data=raw.encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=jv.timeout) as r:
        return json.loads(r.read().decode())


def jev_call(body: dict, jv, cache: Path, qid: str) -> dict:
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True)
    path = cache / f"{hashlib.sha1(raw.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    start = time.perf_counter()
    resp = jev_post(body, raw, jv, langsmith_extra={"metadata": {"qid": qid, "model": jv.model}})
    rec = {"latency": time.perf_counter() - start, "response": resp}
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def jev_score(cfg) -> None:
    jv = cfg.retriever.rerank.jev
    groups = [list(g) for _, g in groupby(read_pairs(ROOT / cfg.paths.rerank_pairs),
                                          key=lambda p: p["qid"])]
    cache = ROOT / cfg.paths.rerank_jev_cache
    cache.mkdir(parents=True, exist_ok=True)
    try:
        with ThreadPoolExecutor(jv.workers) as ex:
            recs = list(ex.map(lambda g: jev_call(jev_body(g, jv), jv, cache, g[0]["qid"]),
                               groups))
    finally:  # 호출이 중간에 실패해도 보낸 요청의 추적은 남긴다
        get_cached_client().flush()
    write_scores(cfg, [{"qid": p["qid"], "doc_id": p["doc_id"],
                        "score": rec["response"]["answers"][f"c{i}"]["score"]}
                       for g, rec in zip(groups, recs, strict=True) for i, p in enumerate(g)])
    t = np.array([r["latency"] for r in recs])
    usage = [r["response"]["usage"] for r in recs]
    result = {"backend": "jev", "model": jv.model, "n_queries": len(recs),
              "input_tokens": sum(u["input_tokens"] for u in usage),
              "cost": sum(u.get("cost") or 0 for u in usage),
              "latency_mean": float(t.mean()), "latency_p50": float(np.percentile(t, 50)),
              "latency_p95": float(np.percentile(t, 95)), "latency_max": float(t.max())}
    state = write_guarded(ROOT / cfg.paths.rerank_latency, json.dumps(result, indent=2) + "\n",
                          cfg.search.overwrite)
    print(json.dumps(result), f"({state})")


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    rr = cfg.retriever.rerank
    if cfg.adopt_basis:  # 지문 없는 기존 점수 파일에 지문만 쓴다. 채점하지 않는다(S15)
        if not (ROOT / cfg.paths.rerank_scores).exists():
            raise SystemExit(f"{cfg.paths.rerank_scores}가 없다")
        print(f"{rerank_basis_path(cfg)} ({write_basis(cfg, False)})")
    else:  # 채점·측정 전에 출력이 있는지 본다(다시 하면 값이 조금씩 달라 끝에서 멈춘다)
        outs = (["rerank_scores", "rerank_latency"] if rr.backend == "jev"
                else ["rerank_scores" if rr.mode == "score" else "rerank_latency"])
        for key in outs:
            refuse_existing(ROOT / cfg.paths[key], cfg.search.overwrite)
        if rr.backend == "jev":
            jev_score(cfg)
        else:
            {"score": score, "latency": latency}[rr.mode](cfg)


if __name__ == "__main__":
    main()
