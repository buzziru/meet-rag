"""기준·후보 순위 파일의 multi-doc 지표 차이를 묶음(pool_id) 단위 paired bootstrap 구간으로 낸다.

multi-doc은 판정에 쓰지 않으므로(docs/SPEC.md "보조 관찰") 채택·기각·보류를 내지 않는다.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from rag.eval.bootstrap import paired_bootstrap
from rag.eval_multi.metrics import load_gold, per_query, ranked_docs, read_run, sha256
from rag.index import ROOT, load_cfg


def diff_table(base: pd.DataFrame, cand: pd.DataFrame, gold: pd.DataFrame, breakdowns,
               n_resamples: int, seed: int, alpha: float) -> list[dict]:
    """전체와 breakdowns 값마다, 지표마다 점 추정 차이와 구간."""
    parts = [("all", "all", gold.index)]
    for col in breakdowns:
        parts += [(col, value, idx) for value, idx in gold.groupby(col).groups.items()]
    rows = []
    for group, value, idx in parts:
        for metric in base.columns:
            diff = (cand.loc[idx, metric] - base.loc[idx, metric]).to_numpy()
            point, lo, hi = paired_bootstrap(
                diff, gold.loc[idx, "pool_id"].to_numpy(), n_resamples, seed, alpha
            )
            rows.append({"group": group, "value": value, "n": len(idx), "metric": metric,
                         "diff": point, "ci": [lo, hi]})
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--cand", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    cfg = load_cfg()
    ev, bs = cfg.multidoc.eval, cfg.eval.bootstrap
    frozen = ROOT / cfg.paths.multidoc_frozen
    gold = load_gold(frozen)
    runs = {"base": args.base, "cand": args.cand}
    scores = {
        name: per_query(ranked_docs(read_run(path), gold, max(ev.ks)), gold, ev.ks)
        for name, path in runs.items()
    }
    result = {
        "frozen_sha256": sha256(frozen),
        **{
            name: {"run": str(path), "run_sha256": sha256(path),
                   "metrics": scores[name].mean().to_dict()}
            for name, path in runs.items()
        },
        "diffs": diff_table(scores["base"], scores["cand"], gold, ev.breakdowns,
                            bs.n_resamples, bs.seed, bs.alpha),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
