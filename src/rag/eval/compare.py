"""기준·후보 순위 파일을 dev-full에서 회의 단위 paired bootstrap으로 비교해 판정한다.

dev-small은 판정에 쓰지 않으므로(docs/SPEC.md "평가 층") 층을 고를 수 없다.
"""

import argparse
import json
from pathlib import Path

from rag.eval.bootstrap import paired_bootstrap, verdict
from rag.eval.metrics import (
    gold_ranks,
    load_cfg,
    load_gold,
    min_docs,
    per_query,
    read_run,
    sha256,
)

LAYER = "dev-full"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--cand", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    cfg = load_cfg()
    ev = cfg.eval
    gold = load_gold(cfg, LAYER)
    n_min = min_docs(ev.recall_ks, ev.mrr_k)
    runs = {"base": args.base, "cand": args.cand}
    scores = {
        name: per_query(gold_ranks(read_run(path), gold, n_min), ev.recall_ks, ev.mrr_k)
        for name, path in runs.items()
    }
    diff = scores["cand"][ev.primary] - scores["base"][ev.primary]
    bs = ev.bootstrap
    point, lo, hi = paired_bootstrap(
        diff.to_numpy(), gold[bs.unit].to_numpy(), bs.n_resamples, bs.seed, bs.alpha
    )
    result = {
        "layer": LAYER,
        **{
            name: {"run": str(path), "run_sha256": sha256(path),
                   "metrics": scores[name].mean().to_dict()}
            for name, path in runs.items()
        },
        "primary": ev.primary,
        "diff": point,
        "ci": [lo, hi],
        "verdict": verdict(point, lo, hi, bs.min_gain),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
