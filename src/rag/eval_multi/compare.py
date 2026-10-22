"""기준·후보 순위 파일의 multi-doc 지표 차이를 묶음(pool_id) 단위 paired bootstrap 구간으로 낸다.

multi-doc은 판정에 쓰지 않으므로(docs/SPEC.md "보조 관찰") 채택·기각·보류를 내지 않는다.
예외는 메타데이터 가설이다: `--single <single-doc 비교 결과 JSON>`을 주면 SPEC "메타데이터 가설의
판정"을 적용한 `metadata_verdict`를 더한다(S18).
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from rag.eval.bootstrap import metadata_verdict, paired_bootstrap, verdict
from rag.eval.score import OVERWRITE_HINT
from rag.eval_multi.metrics import load_gold, per_query, ranked_docs, read_run, sha256
from rag.index import ROOT, load_cfg, write_guarded


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


def check_single(single, base: Path, cand: Path) -> None:
    """--single 입력이 rag.eval.compare의 dev-full 결과이고 같은 실험의 비교인지 본다(S18).

    형식을 먼저 본다. 다른 JSON을 넣으면 뒤의 이름 대조가 없는 칸을 읽어 KeyError가 나거나,
    층이 다른 결과가 "같은 실험이 아니다"로 멈춰 원인을 가리키지 못한다(PR #129 리뷰).
    이름 대조: rag.search는 순위 파일을 `<인덱스>-<설정 이름>-<평가 층>.csv`로 쓴다. single-doc
    결과의 base·cand 이름에서 `-dev-full.csv`를 뗀 것과 multi-doc 이름에서 `-multidoc.csv`를 뗀
    것이 같아야 한다. 다른 실험의 결과를 넣으면 판정이 그 실험의 single-doc 단계로 정해진다.
    """
    if not (isinstance(single, dict) and single.get("layer") == "dev-full"
            and all(k in single for k in ("verdict", "diff", "ci"))
            and all(isinstance(single.get(r), dict) and "run" in single[r]
                    for r in ("base", "cand"))):
        raise SystemExit("--single은 rag.eval.compare의 dev-full 결과 JSON이어야 한다")
    for role, multi in [("base", base), ("cand", cand)]:
        dev = Path(single[role]["run"]).name
        if (not dev.endswith("-dev-full.csv") or not multi.name.endswith("-multidoc.csv")
                or dev.removesuffix("-dev-full.csv") != multi.name.removesuffix("-multidoc.csv")):
            raise SystemExit(f"--single의 {role} 순위 {dev}가 --{role} {multi.name}와 같은 "
                             "실험이 아니다(이름에서 -dev-full.csv·-multidoc.csv를 뗀 부분이 다름)")


def metadata_result(single: dict, rows: list[dict], min_gain: float) -> dict:
    """single-doc 비교 결과와 multi-doc 전체 행으로 메타데이터 가설을 판정한다(S18).

    입력 형식은 check_single이 먼저 본다. single-doc 결과에는 min_gain이 기록되지 않으므로,
    기록된 차이·구간을 지금 min_gain으로 다시 판정해 기록된 판정과 다르면 멈춘다
    (판정 기준이 바뀐 뒤 옛 결과를 넣은 경우).
    """
    if verdict(single["diff"], *single["ci"], min_gain) != single["verdict"]:
        raise SystemExit(f"--single의 판정 {single['verdict']}이 지금 min_gain {min_gain}으로 "
                         "다시 판정한 값과 다르다. 지금 config로 rag.eval.compare를 다시 돌린다")
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
    p.add_argument("--overwrite", action="store_true")
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
        check_single(single, args.base, args.cand)
        result["metadata_verdict"] = {
            # 어느 single-doc 결과로 판정했는지 남긴다. 순위 파일처럼 경로와 sha256을 적는다
            "single": {"path": str(args.single), "sha256": sha256(args.single)},
            **metadata_result(single, result["diffs"], cfg.eval.bootstrap.min_gain)}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        print(f"-> {args.out} ({write_guarded(args.out, text, args.overwrite, OVERWRITE_HINT)})")


if __name__ == "__main__":
    main()
