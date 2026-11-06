"""judge 변형 시험(S53, docs/slices/53-judge-perturb.md).

기준 생성 기록(paths.gen_runs)의 표본 답변을 알려진 유형으로 망가뜨리고, 같은 judge 설정으로 다시
채점해 기준 judge 기록(paths.gen_judge)보다 기대한 쪽으로 나빠졌는지 센다. judge 코드와 설정은
그대로 쓴다.
알려진 오류 유형을 잡는지만 보여 주고 judge의 정확도 전체는 보여 주지 못한다.

- unsupported: 답변 끝에 근거에 없는 사실 문장을 붙인다 → 충실성이 떨어져야 한다
- speaker_swap: 답변에 나온 답변자 이름을 같은 근거의 질의자 이름으로 바꾼다
  → 발언자 불일치가 올라야 한다
- off_topic: 답변을 표본 안 다른 질의의 답변으로 바꾼다 → 답변 관련성이 떨어져야 한다

인자는 Hydra override(예: +exp=current). 판정용 층(dev-full)만 쓴다.
"""

import json
import random
import sys

import numpy as np
from langsmith.run_trees import get_cached_client

from rag.conditions import committee_base
from rag.gen_eval.common import load_refs, read_jsonl
from rag.gen_eval.judge import Judge, judge_recipe, judge_record, run_all, sha
from rag.gen_eval.report import per_query
from rag.index import ROOT, load_cfg, refuse_existing, write_guarded

# 변형마다 볼 지표와 나빠지는 방향(-1: 낮아짐, +1: 높아짐)
EXPECT = {"unsupported": ("faithfulness", -1), "speaker_swap": ("speaker_mismatch", 1),
          "off_topic": ("relevance", -1)}
VOLATILE_RECIPE = {"git_commit", "gen_commits"}


def unsupported(answer: str, sentence: str) -> str:
    return f"{answer.rstrip()}\n\n{sentence}"


def speaker_swap(gen: dict) -> str | None:
    """답변에 나온 답변자 이름 하나를 같은 근거의 다른 질의자 이름으로 모두 바꾼다.
    바꿀 짝이 없으면 None."""
    answer = gen["answer"]
    for c in gen["contexts"]:
        sp = c.get("speakers") or {}
        questioners = [p["name"] for p in sp.get("questioners", []) if p.get("name")]
        for a in (p["name"] for p in sp.get("answerers", []) if p.get("name")):
            if a not in answer:
                continue
            for q in questioners:
                if q != a and q not in answer:
                    return answer.replace(a, q)
    return None


def enough(pool: list[str], n: int, kind: str) -> list[str]:
    """표본을 조용히 줄이지 않는다. 대상이 n보다 적으면 멈춘다."""
    if len(pool) < n:
        raise SystemExit(f"{kind} 대상 질의가 {len(pool)}개라 "
                         f"gen_eval.perturb.n={n}개를 뽑을 수 없다")
    return pool


def build_cases(gens: dict, base: dict, p) -> list[tuple[str, str, str]]:
    """(변형, qid, 바꾼 답변). 표본은 충실성과 관련성이 계산된 기준 질의에서 변형마다
    seed로 뽑는다."""
    eligible = sorted(q for q, r in base.items()
                      if (r.get("faithfulness") or {}).get("score") is not None
                      and (r.get("relevance") or {}).get("score") is not None)
    if p.n < 2:  # off_topic은 표본 안에서 답변을 돌려 쓰므로 하나면 자기 답변이 들어간다
        raise SystemExit(f"gen_eval.perturb.n은 2 이상이다: {p.n}")
    cases = []
    for i, kind in enumerate(p.kinds):
        rng = random.Random(p.seed + i)
        if kind == "unsupported":
            for q in rng.sample(enough(eligible, p.n, kind), p.n):
                cases.append((kind, q, unsupported(gens[q]["answer"], p.unsupported_sentence)))
        elif kind == "speaker_swap":
            pool = [q for q in eligible if speaker_swap(gens[q]) is not None]
            for q in rng.sample(enough(pool, p.n, kind), p.n):
                cases.append((kind, q, speaker_swap(gens[q])))
        elif kind == "off_topic":
            picked = rng.sample(enough(eligible, p.n, kind), p.n)
            for q, other in zip(picked, picked[1:] + picked[:1], strict=True):
                cases.append((kind, q, gens[other]["answer"]))
        else:
            raise SystemExit(f"gen_eval.perturb.kinds의 알 수 없는 변형: {kind}({list(EXPECT)} 중)")
    return cases


def summarize(cases: list[tuple[str, str, str]], rows: list[dict], base: dict) -> dict:
    """변형마다 기준과 변형의 평균, 기대한 쪽으로 나빠진 질의 비율. 지표를 잴 수 없는 질의는
    measured에서 빠진다."""
    pert = per_query([{**r, "qid": f"{k}|{q}"} for (k, q, _), r in zip(cases, rows, strict=True)])
    ref = per_query(list(base.values()))
    out = {}
    for kind, (metric, sign) in EXPECT.items():
        qids = [q for k, q, _ in cases if k == kind]
        if not qids:
            continue
        b = ref.loc[qids, metric].to_numpy()
        a = pert.loc[[f"{kind}|{q}" for q in qids], metric].to_numpy()
        ok = ~(np.isnan(a) | np.isnan(b))
        delta = sign * (a[ok] - b[ok])
        out[kind] = {"metric": metric, "n": len(qids), "measured": int(ok.sum()),
                     "base_mean": float(b[ok].mean()) if ok.any() else None,
                     "perturbed_mean": float(a[ok].mean()) if ok.any() else None,
                     "worse": int((delta > 0).sum()), "same": int((delta == 0).sum()),
                     "better": int((delta < 0).sum()),
                     "worse_rate": float((delta > 0).mean()) if ok.any() else None}
    return out


def load_committees(cfg) -> set[str]:
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        return {committee_base(json.loads(line)["committee_name"]) for line in f} - {""}


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.gen_eval.queries != "dev-full":  # test 층으로 돌지 않게 한다(D-90)
        raise SystemExit(f"변형 시험은 gen_eval.queries=dev-full로만 한다: {cfg.gen_eval.queries}")
    p = cfg.gen_eval.perturb
    out = ROOT / cfg.paths.gen_perturb
    for path in (out, out.with_suffix(".summary.json")):  # judge 호출 전에 본다
        refuse_existing(path, cfg.search.overwrite)
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    base = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_judge)}
    rec = judge_recipe(cfg, [gens[q]["recipe"] for q in base])
    old = next(iter(base.values()))["judge_recipe"]
    if {k: v for k, v in old.items() if k not in VOLATILE_RECIPE} != \
            {k: v for k, v in rec.items() if k not in VOLATILE_RECIPE}:
        raise SystemExit("기준 judge 기록의 judge 설정이 지금 설정과 다르다. "
                         "같은 judge로 비교해야 한다")
    cases = build_cases(gens, base, p)
    refs = load_refs(cfg, sorted({q for _, q, _ in cases}))
    committees = load_committees(cfg)
    judge = Judge(cfg, session=f"meet-rag-perturb-{sha(rec)[:16]}")

    def one(case):
        kind, qid, answer = case
        return judge_record(judge, {**gens[qid], "answer": answer}, refs[qid], cfg, committees)

    try:
        rows = run_all(one, cases, cfg.judge.concurrency, lambda c: f"{c[0]}:{c[1]}",
                       cfg.judge.retry_passes, cfg.judge.stop_after_failures)
    finally:
        print(judge.http.summary(judge.calls))
    get_cached_client().flush()
    summary = summarize(cases, rows, base)
    pairs = zip(cases, rows, strict=True)
    text = "".join(json.dumps({"kind": k, "qid": q, "answer": a, **r, "judge_recipe": rec},
                              ensure_ascii=False) + "\n" for (k, q, a), r in pairs)
    write_guarded(out, text, cfg.search.overwrite)
    write_guarded(out.with_suffix(".summary.json"),
                  json.dumps(summary, ensure_ascii=False, indent=2) + "\n", cfg.search.overwrite)
    print(f"변형 {len(cases)}개 채점, API 호출 {judge.calls}회, 저장된 응답 {judge.hits}회 -> "
          f"{cfg.paths.gen_perturb}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
