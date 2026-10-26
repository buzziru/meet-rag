"""judge 결과(paths.gen_judge)를 집계해 표로 낸다(S14).

기준별 평균과 계산한 질의 수, 뺀 질의 수(전체 거부 포함 이유별), 충실성 판정의 발언자 구분 불가
진술 수(S22), 전체·부분 거부(S14b), 거부 교차 집계,
인용·메타데이터 오류, 토큰·비용, 첫 토큰 시간을 낸다. 항목 평가 결과가 있으면 정보 상태 × 처리 표,
거부 정확도, 틀린 처리 유형을 낸다(S14c). gen_eval.item_cases를 주면 판정 확인 사례의 judge 결과를
정답과 대조한다. 종합 지표와 기준 비교·판정은
만들지 않는다(초안 결정 사항 2·3 이후).
인자는 Hydra override(예: +exp=exp017 gen_eval.n=20).
"""

import sys
from collections import Counter
from hashlib import sha256

import numpy as np

from rag.gen_eval.checks import HANDLINGS, STATES, item_outcome
from rag.gen_eval.common import read_jsonl
from rag.index import ROOT, load_cfg


def mean(xs: list[float]) -> str:
    return f"{np.mean(xs):.3f}" if xs else "-"


def rate(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n:.1%})" if n else "0/0"


def criterion(rows: list[dict], key: str) -> tuple[list[float], Counter, int]:
    """(점수 목록, 뺀 이유별 수, judge 형식 오류 수). 전체 거부 답변은 기준을 채점하지 않아
    full_refusal로 센다(기준 문서 K8)."""
    scores, excluded, errors = [], Counter(), 0
    for r in rows:
        c = r.get(key)
        if c is None:
            if r["refusal"] == "full":
                excluded["full_refusal"] += 1
            continue
        if c.get("score") is not None:
            scores.append(c["score"])
        elif c.get("excluded"):
            excluded[c["excluded"]] += 1
        else:
            errors += 1
    return scores, excluded, errors


def refusal_table(rows: list[dict]) -> list[tuple[str, int, int]]:
    """(근거 상태, 질의 수, 거부 수). 정답 문서의 근거 청크에 핵심 답이 있는데 거부했으면 잘못된
    거부다. 정답 문서가 없을 때의 거부는 참고값이다(S14 결정 5). 판단 불가는 참조 사용 불가(핵심
    진술 없음)와 judge 형식 오류로 나눈다(기준 문서 C2)."""
    def unusable(r):
        return r["gold_n"] and r["answer_in_chunk"] is None and r["key_statements"]["keys"] == []

    groups = {"정답 문서 있음, 청크에 핵심 답 있음": lambda r: r["gold_n"] and r["answer_in_chunk"],
              "정답 문서 있음, 청크에 핵심 답 없음":
                  lambda r: r["gold_n"] and r["answer_in_chunk"] is False,
              "정답 문서 있음, 판단 불가(참조 사용 불가)": unusable,
              "정답 문서 있음, 판단 불가(judge 형식 오류)":
                  lambda r: r["gold_n"] and r["answer_in_chunk"] is None and not unusable(r),
              "정답 문서 없음": lambda r: not r["gold_n"]}
    return [(name, sum(1 for r in rows if f(r)), sum(1 for r in rows if f(r) and r["refusal"]))
            for name, f in groups.items()]


def chunk_ratio_table(rows: list[dict]) -> list[tuple[float, int, int]]:
    """(정답 청크에 든 핵심 진술 비율, 질의 수, 거부 수). 경계 gen_eval.chunk_key_min은 근거가
    부족한 잠정값이라, 비율 분포를 남겨 나중에 경계를 정하는 근거로 쓴다(사용자 결정 2026-10-20)."""
    ratios = Counter()
    refusals = Counter()
    for r in rows:
        score = (r.get("chunk_keys") or {}).get("score")
        if score is not None:
            ratios[round(score, 2)] += 1
            refusals[round(score, 2)] += bool(r["refusal"])
    return [(k, ratios[k], refusals[k]) for k in sorted(ratios)]


# 틀린 처리 유형이 아닌 판정. 상황 미전달은 거부 정확도 밖이라 따로 센다
NOT_WRONG = ("맞음", "상황 전달", "상황 미전달")


def require_s22(rows: list[dict]) -> None:
    """S22 이전 judge 기록(항목 평가의 counts, 충실성 판정의 speaker_unclear가 없음)이면 멈춘다.
    읽으면 거부 정확도가 0/0으로 나오거나 원인을 알 수 없는 KeyError가 난다."""
    for r in rows:
        e, f = r.get("item_eval") or {}, r.get("faithfulness") or {}
        if ("items" in e and "counts" not in e) or any(
                "speaker_unclear" not in v for v in f.get("verdicts", [])):
            raise SystemExit("S22 이전 judge 기록이다(counts·speaker_unclear 없음). "
                             "그 기록을 만든 커밋의 report로 읽는다")


def item_summary(rows: list[dict]) -> dict:
    """질의 항목 단위 거부 평가의 집계(S14c). 거부 정확도는 모호·회피 항목을 뺀 항목 중 맞는
    처리의 비율로, 질의 단위 값(counts, 기준 문서 I13)을 합쳐 계산한다. 모호·회피는 상황
    전달·미전달로 따로 세고(D-41 결정 3, S14c 결정 사항 4) 전체 항목 중 비율을 낸다(I10).
    판단 불가는 judge 형식 오류로 항목이 없는 질의다."""
    evals = [r["item_eval"] for r in rows if r.get("item_eval")]
    items = [i for e in evals for i in e.get("items") or []]
    outcomes = Counter(i["outcome"] for i in items)
    counts = [e["counts"] for e in evals if "counts" in e]
    judged = sum(c["judged"] for c in counts)
    return {"table": Counter((i["state"], i["handling"]) for i in items),
            "outcomes": outcomes, "accuracy": (sum(c["correct"] for c in counts), judged),
            "situation": (outcomes["상황 전달"], len(items) - judged),
            "ambiguous": (len(items) - judged, len(items)),
            "speaker_unclear": sum(i["speaker_unclear"] for i in items),
            "queries": len(evals), "errors": sum(1 for e in evals if "error" in e),
            "wrong_queries": sum(1 for e in evals if any(
                i["outcome"] not in NOT_WRONG for i in e.get("items") or []))}


def case_agreement(cases: list[dict], results: list[dict]) -> tuple[Counter, list[str]]:
    """판정 확인 사례(S14c)의 judge 결과와 정답의 일치. (항목별 일치 수, 어긋난 곳 설명).
    judge가 질의를 정답과 다른 수의 항목으로 나눴으면 그 사례는 항목별로 비교하지 않는다."""
    by_case = {r["case"]: r for r in results}
    agree, notes = Counter(), []
    for c in cases:
        got = by_case[c["case"]]
        if "error" in got:
            notes.append(f"{c['case']}: {got['error']}")
            agree["판단 불가 사례"] += 1
            continue
        if len(got["items"]) != len(c["expected"]):
            notes.append(f"{c['case']}: 항목 수 정답 {len(c['expected'])}, "
                         f"judge {len(got['items'])}")
            agree["항목 수 다른 사례"] += 1
            continue
        for k, (e, g) in enumerate(zip(c["expected"], got["items"], strict=True), 1):
            e = {**e, "outcome": item_outcome(e["state"], e["handling"])}
            agree["항목"] += 1
            for key in ("state", "handling", "outcome"):
                same = e[key] == g[key]
                agree[key] += same
                if not same:
                    notes.append(f"{c['case']} 항목 {k} {key}: 정답 {e[key]}, judge {g[key]}")
    return agree, notes


def print_items(rows: list[dict]) -> None:
    s = item_summary(rows)
    print(f"\n질의 항목 단위 거부 평가(S14c): 질의 {s['queries']}개, 판단 불가(judge 형식 오류) "
          f"{s['errors']}개, 틀린 처리가 있는 질의 {rate(s['wrong_queries'], s['queries'])}\n")
    print("| 정보 상태 \\ 처리 | " + " | ".join(HANDLINGS) + " |\n| --- |"
          + " ---: |" * len(HANDLINGS))
    for st in STATES:
        print(f"| {st} | " + " | ".join(str(s["table"][st, h]) for h in HANDLINGS) + " |")
    print(f"\n거부 정확도(블라인드 확인 전 참고값, 모호·회피 뺀 항목 중 맞는 처리) "
          f"{rate(*s['accuracy'])}, 모호·회피 항목 {rate(*s['ambiguous'])}, "
          f"모호·회피 항목 중 상황 전달 {rate(*s['situation'])}, "
          f"발언자 구분 불가 항목 {s['speaker_unclear']}\n")
    print("| 틀린 처리 유형 | 항목 |\n| --- | ---: |")
    for name, k in s["outcomes"].most_common():
        if name not in NOT_WRONG:
            print(f"| {name} | {k} |")


def print_cases(cfg) -> None:
    """judge 결과를 만든 사례 파일이 지금 파일과 다르면 멈춘다(사례 정답을 고친 뒤의 옛 결과)."""
    src = ROOT / cfg.gen_eval.item_cases
    results = read_jsonl(src.with_suffix(".judge.jsonl"))
    if results[0]["judge_recipe"].get("item_cases_sha256") != sha256(src.read_bytes()).hexdigest():
        raise SystemExit(f"{src.name}이 judge 결과를 만들 때의 사례 파일과 다르다. "
                         "사례를 다시 채점한다")
    agree, notes = case_agreement(read_jsonl(src), results)
    n = agree["항목"]
    print(f"# 판정 확인 사례 {src.name}\n\n항목 {n}개(항목 수 다른 사례 "
          f"{agree['항목 수 다른 사례']}, 판단 불가 사례 {agree['판단 불가 사례']})\n\n"
          "| 대상 | 정답과 같음 |\n| --- | ---: |")
    for key, name in [("state", "정보 상태"), ("handling", "처리"), ("outcome", "맞는 처리 여부")]:
        print(f"| {name} | {rate(agree[key], n)} |")
    print("\n" + "\n".join(f"- {x}" for x in notes) if notes else "\n어긋난 곳 없음")


def usage_sum(usages, key: str) -> int:
    return sum((u or {}).get(key) or 0 for u in usages)


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.gen_eval.item_cases:
        print_cases(cfg)
        return
    rows = read_jsonl(ROOT / cfg.paths.gen_judge)
    require_s22(rows)
    n = len(rows)
    answered = [r for r in rows if r["refusal"] != "full"]
    partial = [r for r in rows if r["refusal"] == "partial"]
    print(f"# {cfg.paths.gen_judge}\n\n질의 {n}개, 전체 거부 {rate(n - len(answered), n)}, "
          f"부분 거부 {rate(len(partial), n)}\n")

    print("| 기준 | 평균 | 계산한 질의 | 그중 부분 거부 | 뺀 질의 | judge 형식 오류 |\n"
          "| --- | ---: | ---: | ---: | --- | ---: |")
    for key, name in [("faithfulness", "충실성"), ("relevance", "답변 관련성"),
                      ("inclusion", "핵심 답변 포함도")]:
        scores, excluded, errors = criterion(rows, key)
        part = len(criterion(partial, key)[0])
        ex = ", ".join(f"{k} {v}" for k, v in excluded.items()) or "-"
        print(f"| {name} | {mean(scores)} | {len(scores)} | {part} | {ex} | {errors} |")
    # 뒷받침(1)으로 판정하고 발언자 구분 불가로 표시한 진술만 센다(기준 문서 F7)
    unclear = [sum(v["speaker_unclear"] and v["verdict"] == 1
                   for v in (r.get("faithfulness") or {}).get("verdicts", [])) for r in rows]
    print(f"\n충실성 판정에서 발언자를 구분할 수 없는 진술 {sum(unclear)}개, 그런 진술이 든 질의 "
          f"{sum(1 for k in unclear if k)}개(기준 문서 F7)")

    print("\n| 근거 상태 | 질의 | 거부(전체·부분) |\n| --- | ---: | ---: |")
    for name, k, ref in refusal_table(rows):
        print(f"| {name} | {k} | {rate(ref, k)} |")

    # 경계는 judge가 채점에 쓴 값이다. S15 전 기록에는 없다
    key_min = rows[0]["judge_recipe"].get("chunk_key_min", "기록 없음")
    print(f"\n정답 청크에 든 핵심 진술 비율(잠정 경계 {key_min} 이상을 "
          "'있음'으로 본다)\n\n| 비율 | 질의 | 거부 |\n| ---: | ---: | ---: |")
    for ratio, k, ref in chunk_ratio_table(rows):
        print(f"| {ratio:.2f} | {k} | {rate(ref, k)} |")
    if any(r.get("item_eval") for r in rows):
        print_items(rows)

    cites = [r["citations"] for r in answered]
    n_sent = sum(c["n_sentences"] for c in cites)
    meta = [r["metadata"] for r in answered]
    print("\n| 코드 판정 | 값 |\n| --- | ---: |")
    bad = sum(1 for c in cites if c["invalid"])
    print(f"| 근거 번호 밖 인용이 있는 답변 | {rate(bad, len(cites))} |")
    print(f"| 인용 없는 문장 | {rate(sum(c['uncited'] for c in cites), n_sent)} |")
    print(f"| 내용 없는 문장(인사말·도입 문장, 문장 수에서 뺌) | "
          f"{sum(c.get('filler', 0) for c in cites)} |")
    print(f"| 회의 일자·위원회 불일치가 있는 답변 | {rate(sum(1 for m in meta if m), len(meta))} |")

    gen_usage = [r["usage"] for r in rows]
    price = cfg.generator.price_per_mtok
    tin, tout = usage_sum(gen_usage, "prompt_tokens"), usage_sum(gen_usage, "completion_tokens")
    reasoning = sum(((u or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                    for u in gen_usage)
    keys = ("faithfulness", "relevance", "inclusion", "key_statements", "chunk_keys", "item_eval")
    judge_usage = [u for r in rows for key in keys for u in ((r.get(key) or {}).get("usage") or [])]
    first = [r["first_token_s"] for r in rows if r["first_token_s"] is not None]
    total = [r["total_s"] for r in rows]
    providers = Counter(r["provider"] for r in rows)
    print("\n| 생성·judge | 값 |\n| --- | ---: |")
    print(f"| 생성 입력·출력 토큰 | {tin:,} · {tout:,} (사고 과정 {reasoning:,}) |")
    print(f"| 생성 비용 추정 | ${(tin * price.input + tout * price.output) / 1e6:.4f} |")
    print(f"| judge 입력·출력 토큰 | {usage_sum(judge_usage, 'prompt_tokens'):,} · "
          f"{usage_sum(judge_usage, 'completion_tokens'):,} |")
    retrieve = [r["retrieve_s"] for r in rows if r.get("retrieve_s") is not None]
    print(f"| 답변 첫 토큰 시간 중앙값·p95·최대 | {spread(first)} · {max(first):.2f}초 |"
          if first else "| 답변 첫 토큰 시간 | - |")
    print(f"| 생성 전체 시간 중앙값·p95 | {spread(total)} |")
    print(f"| 검색 시간 중앙값·p95 | {spread(retrieve)} |")
    print(f"| 생성 동시 수 | {dict(Counter(r.get('concurrency') for r in rows))} |")
    print(f"| 제공자 | {', '.join(f'{k} {v}' for k, v in providers.items())} |")
    print_judge_calls(judge_usage)


def spread(xs: list[float]) -> str:
    return f"{np.median(xs):.2f}초 · {np.percentile(xs, 95):.2f}초" if xs else "-"


def print_judge_calls(usages: list[dict]) -> None:
    """judge 단계별 호출 수, 새로 부른 호출의 지연·토큰, 끝나지 않은 응답 수(S24). 지연은 저장
    응답을 쓴 호출을 빼고 센다. S24 전 기록에는 단계 이름이 없어 표를 내지 않는다."""
    if not any(u and "step" in u for u in usages):
        return
    print("\n| judge 단계 | 호출 | 새로 부름 | 지연 중앙값·p95 | 새 호출 입력·출력 토큰 "
          "| 끝나지 않음 |\n| --- | ---: | ---: | ---: | ---: | ---: |")
    for step in dict.fromkeys(u["step"] for u in usages if u and "step" in u):
        us = [u for u in usages if u and u.get("step") == step]
        new = [u for u in us if not u["cached"]]
        lat = [u["latency_s"] for u in new if u.get("latency_s") is not None]
        unfinished = sum(1 for u in new if u.get("finish_reason") != "stop")
        print(f"| {step} | {len(us)} | {len(new)} | {spread(lat)} | "
              f"{usage_sum(new, 'prompt_tokens'):,} · {usage_sum(new, 'completion_tokens'):,} | "
              f"{unfinished} |")


if __name__ == "__main__":
    main()
