"""기준·후보 순위 파일의 multi-doc 지표 차이를 묶음(pool_id) 단위 paired bootstrap 구간으로 낸다.

multi-doc은 판정에 쓰지 않으므로(docs/SPEC.md "보조 관찰") 채택·기각·보류를 내지 않는다.
예외는 메타데이터 가설이다: `--single <single-doc 비교 결과 JSON>`을 주면 SPEC "메타데이터 가설의
판정"을 적용한 `metadata_verdict`를 더한다(S18).
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from rag.eval.bootstrap import metadata_verdict, paired_bootstrap
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


def metadata_result(single: dict, rows: list[dict], min_gain: float) -> dict:
    """single-doc 비교 결과와 multi-doc 전체 행으로 메타데이터 가설을 판정한다(S18).

    single-doc 결과가 dev-full 판정(rag.eval.compare 출력)이 아니면 멈춘다.
    """
    if single.get("layer") != "dev-full" or "verdict" not in single:
        raise SystemExit("--single은 rag.eval.compare의 dev-full 결과 JSON이어야 한다")
    all_rows = {r["metric"]: r for r in rows if r["group"] == "all"}
    recall, complete = all_rows["recall@5"], all_rows["complete@5"]
    return {"single_verdict": single["verdict"],
            "recall@5": {"diff": recall["diff"], "ci": recall["ci"]},
            "complete@5": {"diff": complete["diff"], "ci": complete["ci"]},
            **metadata_verdict(single["verdict"], (recall["diff"], *recall["ci"]),
                               complete["ci"][1], min_gain)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--cand", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--single", type=Path, help="메타데이터 가설: rag.eval.compare 결과 JSON")
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
    if args.single:
        single = json.loads(args.single.read_text(encoding="utf-8"))
        result["metadata_verdict"] = metadata_result(single, result["diffs"],
                                                     cfg.eval.bootstrap.min_gain)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
