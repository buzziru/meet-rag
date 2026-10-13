"""상위 후보를 다시 점수 매긴다(H2, EXP-005).

후보 쌍 파일(`rag.search search.mode=rerank-pairs`)을 읽어 점수 파일을 쓴다.
- backend jev: 질의 하나의 후보를 한 요청에 묶어 Jev(OpenRouter Decisions API)의 score 질문으로
  채점한다. 응답은 요청 본문 해시로 저장해 다시 실행할 때 쓴다. 질의당 지연·비용도 남긴다
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
from sentence_transformers import CrossEncoder

from rag.index import ROOT, load_cfg  # .env를 읽는다


def load_model(rr) -> CrossEncoder:
    if rr.threads:
        torch.set_num_threads(rr.threads)
    return CrossEncoder(rr.model, revision=rr.revision, max_length=rr.max_length,
                        device=rr.device, model_kwargs={"dtype": getattr(torch, rr.dtype)})


def read_pairs(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def score(cfg) -> None:
    rr = cfg.retriever.rerank
    pairs = read_pairs(ROOT / cfg.paths.rerank_pairs)
    model = load_model(rr)
    start = time.perf_counter()
    scores = model.predict([(p["query"], p["text"]) for p in pairs], batch_size=rr.batch_size)
    elapsed = time.perf_counter() - start
    out = ROOT / cfg.paths.rerank_scores
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for p, s in zip(pairs, scores, strict=True):
            f.write(json.dumps({"qid": p["qid"], "doc_id": p["doc_id"], "score": float(s)}) + "\n")
    print(f"{len(pairs):,} pairs -> {cfg.paths.rerank_scores} ({elapsed:.1f}s, "
          f"{len(pairs) / elapsed:.1f} pairs/s)")


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
    out = ROOT / cfg.paths.rerank_latency
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def jev_body(group: list[dict], jv) -> dict:
    """질의 하나와 후보들을 공유 state에 두고 후보마다 score 질문 하나를 붙인다."""
    candidates = {str(i): p["text"] for i, p in enumerate(group)}
    state = {"query": group[0]["query"], "candidates": candidates}
    questions = {f"c{i}": {"type": "score", "instructions": f"후보 {i}: {jv.instructions}",
                           "criteria": list(jv.levels)} for i in range(len(group))}
    return {"model": jv.model, "state": state, "questions": questions}


def jev_call(body: dict, jv, cache: Path) -> dict:
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True)
    path = cache / f"{hashlib.sha1(raw.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    headers = {"Authorization": f"Bearer {os.environ[jv.api_key_env]}",
               "Content-Type": "application/json"}
    req = urllib.request.Request(jv.url, data=raw.encode(), headers=headers)
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=jv.timeout) as r:
        resp = json.loads(r.read().decode())
    rec = {"latency": time.perf_counter() - start, "response": resp}
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def jev_score(cfg) -> None:
    jv = cfg.retriever.rerank.jev
    groups = [list(g) for _, g in groupby(read_pairs(ROOT / cfg.paths.rerank_pairs),
                                          key=lambda p: p["qid"])]
    cache = ROOT / cfg.paths.rerank_jev_cache
    cache.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(jv.workers) as ex:
        recs = list(ex.map(lambda g: jev_call(jev_body(g, jv), jv, cache), groups))
    out = ROOT / cfg.paths.rerank_scores
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for g, rec in zip(groups, recs, strict=True):
            answers = rec["response"]["answers"]
            for i, p in enumerate(g):
                row = {"qid": p["qid"], "doc_id": p["doc_id"], "score": answers[f"c{i}"]["score"]}
                f.write(json.dumps(row) + "\n")
    t = np.array([r["latency"] for r in recs])
    usage = [r["response"]["usage"] for r in recs]
    result = {"backend": "jev", "model": jv.model, "n_queries": len(recs),
              "input_tokens": sum(u["input_tokens"] for u in usage),
              "cost": sum(u.get("cost") or 0 for u in usage),
              "latency_mean": float(t.mean()), "latency_p50": float(np.percentile(t, 50)),
              "latency_p95": float(np.percentile(t, 95)), "latency_max": float(t.max())}
    out = ROOT / cfg.paths.rerank_latency
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{len(groups):,} queries -> {cfg.paths.rerank_scores}")
    print(json.dumps(result))


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    rr = cfg.retriever.rerank
    if rr.backend == "jev":
        jev_score(cfg)
    else:
        {"score": score, "latency": latency}[rr.mode](cfg)


if __name__ == "__main__":
    main()
