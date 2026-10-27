"""기준·후보 judge 결과를 gen-full에서 회의 단위 paired bootstrap으로 비교해 판정한다(S27).

규칙은 docs/SPEC.md "생성 단계 평가 > 판정"(D-53), 기준값은 configs/eval/gen_v1.yaml이다.
판정용 세트(gen_eval 기본값의 dev-full 330질의)만 받는다. gen-small은 작동 확인용이다.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rag.eval.bootstrap import paired_bootstrap
from rag.eval.metrics import load_gold, sha256
from rag.eval.score import OVERWRITE_HINT
from rag.gen_eval.common import eval_qids, read_jsonl
from rag.gen_eval.judge import sha
from rag.gen_eval.report import require_s22
from rag.index import load_cfg, write_guarded

# judge_recipe 중 채점 방식을 정하는 값. 다르면 차이가 생성이 아니라 채점에서 나온다
JUDGE_KEYS = ("name", "model", "base_url", "params", "extra_body", "step_params",
              "prompt_version", "prompt_sha256", "filler_phrases", "check_patterns",
              "chunk_key_min", "item_eval")
# 거부 문구는 생성 프롬프트에서 오므로 프롬프트 실험에서 바뀔 수 있다. 멈추지 않고 차이만 낸다
CHECK_KEYS = ("refusal",)
METRICS = ("faithfulness", "relevance", "composite", "inclusion", "over_refusal")


def per_query(rows: list[dict]) -> pd.DataFrame:
    """질의 단위 값. 계산하지 않은 기준(전체 거부, 제외 조건, 형식 오류)은 NaN이다.
    종합 지표는 충실성·관련성 평균이고 둘 중 하나라도 없으면 NaN이다(D-53)."""
    out = {}
    for r in rows:
        counts = (r.get("item_eval") or {}).get("counts") or {}
        out[r["qid"]] = {
            key: (r.get(key) or {}).get("score", np.nan)
            for key in ("faithfulness", "relevance", "inclusion")
        } | {"over_refusal": counts["over_refusal"] / counts["judged"]
             if counts.get("judged") else np.nan}
    df = pd.DataFrame.from_dict(out, orient="index").astype(float)
    df["composite"] = df[["faithfulness", "relevance"]].mean(axis=1, skipna=False)
    return df


def gen_verdict(ci: dict[str, tuple[float, float, float]], spec) -> tuple[str, list[str]]:
    """(판정, 걸린 조건). ci는 기준별 (점 추정, 하한, 상한)이다.

    기각(종합 지표 상한 < 0)과 채택(하한 > 0)은 함께 성립하지 않고 안전 조건은 채택에만 들어
    있어, 안전 조건은 채택과 보류만 가른다. 기각에서도 걸린 안전 조건은 함께 낸다."""
    point, lo, hi = ci["composite"]
    safety = [f"{name} 하락(하한 < {spec.floors[key]})"
              for key, name in [("faithfulness", "충실성"), ("relevance", "답변 관련성")]
              if ci[key][1] < spec.floors[key]]
    if ci["over_refusal"][2] > spec.over_refusal_max:
        safety.append(f"과잉 거부 증가(상한 > {spec.over_refusal_max})")
    if hi < 0:
        return "기각", safety
    failed = (["종합 지표 구간 하한 ≤ 0"] if lo <= 0 else []) + (
        [f"종합 지표 점 추정 < {spec.min_gain}"] if point < spec.min_gain else [])
    return ("보류" if failed + safety else "채택"), failed + safety


def check_inputs(runs: dict[str, Path], rows: dict[str, list[dict]], qids: list[str]) -> dict:
    """두 judge 결과가 비교할 수 있는지 보고 어긋나면 멈춘다. 코드 판정 설정의 차이를 돌려준다."""
    if runs["base"].resolve() == runs["cand"].resolve():
        raise SystemExit("--base와 --cand가 같은 파일이다")
    want = set(qids)
    for name, rs in rows.items():
        require_s22(rs)
        got = [r["qid"] for r in rs]
        if len(got) != len(set(got)) or set(got) != want:
            raise SystemExit(f"{runs[name]}의 질의가 gen-full {len(want)}질의와 다르다 "
                             f"({len(set(got))}질의, 겹침 {len(want & set(got))}). "
                             "판정은 gen-full 결과로 한다")
    recipes = {}
    for name, rs in rows.items():
        # 커밋·생성 레시피는 섞여도 된다(근거가 같은 질의에 기준 결과를 쓰는 S26 방식)
        found = {sha({k: r["judge_recipe"].get(k) for k in JUDGE_KEYS + CHECK_KEYS}) for r in rs}
        if len(found) != 1:
            raise SystemExit(f"{runs[name]}에 judge 설정이 {len(found)}가지 섞여 있다")
        recipes[name] = rs[0]["judge_recipe"]
    diff = [k for k in JUDGE_KEYS if recipes["base"].get(k) != recipes["cand"].get(k)]
    if diff:
        raise SystemExit(f"judge 설정이 다르다: {', '.join(diff)}. "
                         "같은 judge로 채점한 결과만 비교한다")
    return {k: {"base": recipes["base"].get(k), "cand": recipes["cand"].get(k)}
            for k in CHECK_KEYS if recipes["base"].get(k) != recipes["cand"].get(k)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--cand", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    cfg = load_cfg(["index.scope=full"])
    runs = {"base": args.base, "cand": args.cand}
    rows = {name: read_jsonl(path) for name, path in runs.items()}
    qids = eval_qids(cfg)
    check_diff = check_inputs(runs, rows, qids)

    bs = cfg.eval.bootstrap
    groups = load_gold(cfg, cfg.gen_eval.queries)[bs.unit]
    scores = {name: per_query(rs).loc[qids] for name, rs in rows.items()}
    result, ci = {}, {}
    for key in METRICS:
        a, b = scores["base"][key], scores["cand"][key]
        both = a.notna() & b.notna()  # 짝지은 제외(D-47 결정 6)
        diff = (b - a)[both]
        ci[key] = paired_bootstrap(diff.to_numpy(), groups[diff.index].to_numpy(),
                                   bs.n_resamples, bs.seed, bs.alpha)
        result[key] = {"base": float(a[both].mean()), "cand": float(b[both].mean()),
                       "diff": ci[key][0], "ci": [ci[key][1], ci[key][2]], "n": int(both.sum())}
    verdict, failed = gen_verdict(ci, cfg.eval_gen)
    out = {
        "layer": "gen-full", "n_queries": len(qids), "qids_sha256": sha(sorted(qids)),
        **{name: {"run": str(path), "run_sha256": sha256(path)} for name, path in runs.items()},
        "metrics": result, "verdict": verdict, "failed": failed,
        "check_settings_diff": check_diff,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        print(f"-> {args.out} ({write_guarded(args.out, text, args.overwrite, OVERWRITE_HINT)})")


if __name__ == "__main__":
    main()
