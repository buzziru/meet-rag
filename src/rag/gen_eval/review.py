"""judge 설정 둘의 채점 결과를 나란히 놓은 사람 검수 파일을 쓴다(S14, PR #106 코멘트).

gen_eval.review.judges의 두 judge 결과(paths.gen_judge)와 생성 기록·참조 발언을 읽어
- {out}.md: 질의마다 질문·답변·근거·참조 발언과 두 설정의 판정·이유(읽는 파일)
- {out}.csv: 질의 × 기준마다 두 설정의 점수, Claude 의견, 빈 검수 칸(채우는 파일, Excel용 utf-8-sig)
를 쓴다. {out}_opinion.json이 있으면 질의·기준별 의견을 넣는다.
질의 원문을 담으므로 data/ 아래에만 둔다.
인자는 Hydra override(예: +exp=exp017 gen_eval.n=20 prompt=v1).
"""

import json
import sys

import pandas as pd

from rag.gen_eval.common import load_refs, read_jsonl
from rag.index import ROOT, load_cfg

CRITERIA = {"faithfulness": "충실성", "relevance": "답변 관련성", "inclusion": "핵심 답변 포함도",
            "answer_in_chunk": "청크에 핵심 답 있음"}
REVIEW_COLUMNS = ["user_choice", "user_score", "user_note"]


def score(row: dict, key: str):
    if key == "answer_in_chunk":
        return row.get(key)
    c = row.get(key) or {}
    return c.get("score") if c.get("score") is not None else c.get("excluded") or c.get("error")


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    return "-" if v is None else str(v)


def detail(row: dict, key: str) -> list[str]:
    """기준 하나의 판정 이유 줄들."""
    c = row.get(key) or {}
    if key == "faithfulness":
        return [f"- [{v['verdict']}] {v['statement']} / {v['reason']}"
                for v in c.get("verdicts", [])]
    if key == "relevance":
        return [f"- {c.get('label', '-')}: {c.get('reason', '-')}"] if c else []
    if key == "inclusion":
        return [f"- [{x['present']}] {x['statement']} / {x['reason']}" for x in c.get("checks", [])]
    chunk = row.get("chunk_keys") or {}
    return [f"- [{x['present']}] {x['statement']} / {x['reason']}" for x in chunk.get("checks", [])]


def main() -> None:
    overrides = sys.argv[1:]
    cfg = load_cfg(["index.scope=full", *overrides])
    names = list(cfg.gen_eval.review.judges)
    out = ROOT / cfg.gen_eval.review.out
    if out.with_suffix(".csv").exists() and not cfg.search.overwrite:  # 사람이 채운 검수 칸(S15)
        raise SystemExit(f"{out.with_suffix('.csv')}가 있다. "
                         "덮어쓰려면 search.overwrite=true")
    judged = {n: {r["qid"]: r for r in read_jsonl(ROOT / load_cfg(
        ["index.scope=full", *overrides, f"judge={n}"]).paths.gen_judge)} for n in names}
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    qids = [q for q in gens if all(q in judged[n] for n in names)]
    refs = load_refs(cfg, qids)
    op_path = out.with_name(out.name + "_opinion.json")
    opinions = json.loads(op_path.read_text(encoding="utf-8")) if op_path.exists() else {}

    md, rows = [f"# judge 설정 비교 검수: {' vs '.join(names)}\n",
                f"생성 기록 `{cfg.paths.gen_runs}`. 채우는 파일은 `{out.name}.csv`다.\n"], []
    for i, q in enumerate(qids, 1):
        g, a, b = gens[q], judged[names[0]][q], judged[names[1]][q]
        md += [f"## {i}. {q}\n", f"**질문**: {g['query']}\n", f"**생성 답변**\n\n{g['answer']}\n",
               f"**참조 발언(answer.comment)**\n\n{refs[q]['answer_comment']}\n",
               f"정답 문서 위치: {a['gold_n'] or '근거에 없음'}\n",
               "<details><summary>근거 5개</summary>\n"]
        md += [f"[{c['n']}] {c['date']} {c['committee_name']}\n\n{c['text']}\n"
               for c in g["contexts"]]
        md += ["</details>\n"]
        for key, label in CRITERIA.items():
            sa, sb = score(a, key), score(b, key)
            md += [f"### {label}: {names[0]} {fmt(sa)} / {names[1]} {fmt(sb)}"
                   f"{' (다름)' if sa != sb else ''}\n", f"{names[0]}:\n", *detail(a, key), "",
                   f"{names[1]}:\n", *detail(b, key), ""]
            op = opinions.get(q, {}).get(key, "")
            if op:
                md += [f"> Claude 의견: {op}\n"]
            rows.append({"no": i, "qid": q, "criterion": label,
                         names[0]: fmt(sa), names[1]: fmt(sb), "differs": sa != sb,
                         "claude_opinion": op, **dict.fromkeys(REVIEW_COLUMNS, "")})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"{len(qids)}개 질의, 의견 {len(opinions)}개 질의 -> {out}.md, {out}.csv")


if __name__ == "__main__":
    main()
