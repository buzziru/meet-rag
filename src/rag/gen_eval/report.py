"""judge 결과(paths.gen_judge)를 집계해 표로 낸다(S14).

기준별 평균과 계산한 질의 수, 뺀 질의 수(이유별), 전체·부분 거부(S14b), 거부 교차 집계,
인용·메타데이터 오류, 토큰·비용, 첫 토큰 시간을 낸다. 종합 지표와 기준 비교·판정은
만들지 않는다(초안 결정 사항 2·3 이후).
인자는 Hydra override(예: +exp=exp017 gen_eval.n=20).
"""

import sys
from collections import Counter

import numpy as np

from rag.gen_eval.common import read_jsonl
from rag.index import ROOT, load_cfg


def mean(xs: list[float]) -> str:
    return f"{np.mean(xs):.3f}" if xs else "-"


def rate(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n:.1%})" if n else "0/0"


def criterion(rows: list[dict], key: str) -> tuple[list[float], Counter, int]:
    """(점수 목록, 뺀 이유별 수, judge 형식 오류 수). 거부 답변은 기준이 없어 세지 않는다."""
    scores, excluded, errors = [], Counter(), 0
    for r in rows:
        c = r.get(key)
        if c is None:
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
    거부다. 정답 문서가 없을 때의 거부는 참고값이다(S14 결정 5). 판단 불가는 핵심 진술이 없거나
    judge 형식 오류인 경우다."""
    groups = {"정답 문서 있음, 청크에 핵심 답 있음": lambda r: r["gold_n"] and r["answer_in_chunk"],
              "정답 문서 있음, 청크에 핵심 답 없음":
                  lambda r: r["gold_n"] and r["answer_in_chunk"] is False,
              "정답 문서 있음, 판단 불가": lambda r: r["gold_n"] and r["answer_in_chunk"] is None,
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


def usage_sum(usages, key: str) -> int:
    return sum((u or {}).get(key) or 0 for u in usages)


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    rows = read_jsonl(ROOT / cfg.paths.gen_judge)
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

    print("\n| 근거 상태 | 질의 | 거부(전체·부분) |\n| --- | ---: | ---: |")
    for name, k, ref in refusal_table(rows):
        print(f"| {name} | {k} | {rate(ref, k)} |")

    # 경계는 judge가 채점에 쓴 값이다. S15 전 기록에는 없다
    key_min = rows[0]["judge_recipe"].get("chunk_key_min", "기록 없음")
    print(f"\n정답 청크에 든 핵심 진술 비율(잠정 경계 {key_min} 이상을 "
          "'있음'으로 본다)\n\n| 비율 | 질의 | 거부 |\n| ---: | ---: | ---: |")
    for ratio, k, ref in chunk_ratio_table(rows):
        print(f"| {ratio:.2f} | {k} | {rate(ref, k)} |")

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
    keys = ("faithfulness", "relevance", "inclusion", "key_statements", "chunk_keys")
    judge_usage = [u for r in rows for key in keys for u in ((r.get(key) or {}).get("usage") or [])]
    first = [r["first_token_s"] for r in rows if r["first_token_s"] is not None]
    total = [r["total_s"] for r in rows]
    providers = Counter(r["provider"] for r in rows)
    print("\n| 생성·judge | 값 |\n| --- | ---: |")
    print(f"| 생성 입력·출력 토큰 | {tin:,} · {tout:,} (사고 과정 {reasoning:,}) |")
    print(f"| 생성 비용 추정 | ${(tin * price.input + tout * price.output) / 1e6:.4f} |")
    print(f"| judge 입력·출력 토큰 | {usage_sum(judge_usage, 'prompt_tokens'):,} · "
          f"{usage_sum(judge_usage, 'completion_tokens'):,} |")
    print(f"| 답변 첫 토큰 시간 중앙값·최대 | {np.median(first):.2f}초 · {max(first):.2f}초 |"
          if first else "| 답변 첫 토큰 시간 | - |")
    print(f"| 생성 전체 시간 중앙값 | {np.median(total):.2f}초 |")
    print(f"| 제공자 | {', '.join(f'{k} {v}' for k, v in providers.items())} |")


if __name__ == "__main__":
    main()
