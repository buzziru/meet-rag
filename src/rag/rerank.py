"""상위 후보를 cross-encoder로 다시 점수 매긴다(H2, EXP-005).

후보 쌍 파일(`rag.search search.mode=rerank-pairs`)을 읽어
- score: 쌍마다 점수를 매겨 점수 파일을 쓴다(Colab GPU)
- latency: 질의 몇 개로 질의당 재정렬 시간을 잰다(로컬 CPU, VM GPU)
인자는 Hydra override. 모드는 retriever.rerank.mode.
"""

import json
import sys
import time
from itertools import groupby
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import CrossEncoder

from rag.index import ROOT, load_cfg


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


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    {"score": score, "latency": latency}[cfg.retriever.rerank.mode](cfg)


if __name__ == "__main__":
    main()
