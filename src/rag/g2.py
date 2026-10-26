"""G2 기준 오답 질의 검토(PLAN G2, 사용자 결정 2026-10-15).

기준 설정(cfg.g2.exp)이 dev-full에서 정답을 상위 top개에 넣지 못한 질의 전부를 대상으로 한다.

    prepare: 작업자 입력을 쓴다. 1단계(in1)는 질의와 정답 문서만, 2단계(in2)는 검색 상위를 더한다
    review:  작업자 출력(out1·out2)과 코드가 계산한 순위 유형을 모아 사람이 확인할 검수 파일을 쓴다

순위 유형(결합 손실·근접·전 목록 실패)과 같은 회의 여부는 코드가 정하고, 특정 가능성과 다른 정답
여부는 작업자가 판단한다. 최종 분류는 final_class 규칙으로 정한다.
"""

import argparse
import json
from collections import Counter

from omegaconf import OmegaConf

from rag.conditions import build_extractor
from rag.eval.metrics import load_gold, read_run
from rag.index import ROOT, load_cfg
from rag.multidoc.check import wrap_lines
from rag.retrieve import ChunkStore, Retriever, best_chunks, chunks_by_doc
from rag.search import query_embeddings, query_files, query_list, read_texts

META = ["date", "committee_name", "meeting_name", "meeting_number", "session_number", "agenda"]


def rank_type(ranks: dict[str, int | None], top: int, near: int) -> str:
    """결합 전 목록별 정답 순위로 실패를 나눈다(24_01과 같은 기준: top·20)."""
    best = min((r for r in ranks.values() if r), default=None)
    if best is not None and best <= top:
        return "결합 손실"
    if best is not None and best <= near:
        return "근접"
    return "전 목록 실패"


def final_class(s1: dict, s2: dict) -> str:
    """질의만으로 특정할 수 없거나 상위에 다른 정답이 있으면 좁힐 수 없는 오류다."""
    if not s1["identifiable"] or s2["other_answer"]:
        return "좁힐 수 없음"
    return "개선 가능"


def meta_text(doc: dict, agenda_chars: int) -> str:
    """회의 정보 한 줄. 안건은 수만 자인 문서가 있어 앞 agenda_chars자만 쓴다."""
    vals = {k: str(doc[k]) for k in META if doc.get(k)}
    if len(vals.get("agenda", "")) > agenda_chars:
        vals["agenda"] = vals["agenda"][:agenda_chars] + "…"
    return " | ".join(f"{k}: {v}" for k, v in vals.items())


def prompt(name: str):
    return OmegaConf.load(ROOT / "configs" / "g2" / "prompt" / f"{name}.yaml")


def doc_block(doc: dict, chunk: str, g) -> str:
    return f"{meta_text(doc, g.agenda_chars)}\n\n{wrap_lines(chunk, g.max_line_chars)}"


def write_input(path, p, **fields) -> None:
    path.write_text(f"# 지시\n\n{p.system}\n\n# 입력\n\n{p.user.format(**fields)}\n",
                    encoding="utf-8")


def prepare(cfg) -> None:
    g = cfg.g2
    rcfg = load_cfg([f"+exp={g.exp}", "index.scope=full"])
    ret = Retriever(rcfg)
    gold = load_gold(rcfg, "dev-full")
    # 기준 순위 파일(rag.search와 같은 이름 규칙)
    name = f"{ret.index_dir.parent.name}-{rcfg.retriever.run_name}-{query_files(rcfg)['name']}"
    run = read_run(ROOT / rcfg.paths.runs_dir / f"{name}.csv")
    top = run.sort_values(["qid", "rank"]).groupby("qid")["doc_id"].apply(list)
    miss = sorted(q for q in gold.index if gold.loc[q, "doc_id"] not in top[q][: g.top])

    qids, path = query_list(rcfg)
    texts = dict(zip(qids, read_texts(path, qids), strict=True))
    emb = dict(zip(qids, query_embeddings(rcfg, qids, query_files(rcfg)["emb"]),
                   strict=True))
    tokens = dict(zip(miss, ret.query_tokens([texts[q] for q in miss]), strict=True))
    ex = build_extractor(rcfg)
    by_doc = chunks_by_doc(ret.dense_ids)

    labels = {}
    with (ROOT / rcfg.paths.queries).open(encoding="utf-8") as f:
        for q in map(json.loads, f):
            if q["qid"] in set(miss):
                labels[q["qid"]] = q["question_comment"]
    docs = {}
    need = {gold.loc[q, "doc_id"] for q in miss} | {d for q in miss for d in top[q][: g.top]}
    with (ROOT / rcfg.paths.corpus).open(encoding="utf-8") as f:
        for d in map(json.loads, f):
            if d["doc_id"] in need:
                docs[d["doc_id"]] = d

    rows, picks = {}, {}
    for q in miss:
        row = ret.chunk_emb @ emb[q]
        named, _, _ = ret.lists(row, tokens[q], ex.extract(texts[q]))
        fused = ret.fuse(named)
        g_doc = gold.loc[q, "doc_id"]
        ranks = {n: lst.index(g_doc) + 1 if g_doc in lst else None for n, lst in named.items()}
        final = top[q].index(g_doc) + 1 if g_doc in top[q] else None
        shown = [*top[q][: g.top], g_doc]
        picks[q] = dict(zip(shown, best_chunks(row, by_doc, shown), strict=True))
        rows[q] = {"qid": q, "gold": g_doc, "final_rank": final, "list_ranks": ranks,
                   "fused_rank": fused.index(g_doc) + 1 if g_doc in fused else None,
                   "rank_type": rank_type(ranks, g.top, g.near),
                   "same_meeting_top1": docs[top[q][0]]["conference_number"]
                   == docs[g_doc]["conference_number"],
                   "top": top[q][: g.top]}
    chunks = ChunkStore(ret.dirs).texts({i for p in picks.values() for i in p.values()})

    out = ROOT / cfg.paths.g2_dir
    for sub in ["in1", "in2", "out1", "out2"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    p1, p2 = prompt(g.stage1), prompt(g.stage2)
    for q in miss:
        r, gd = rows[q], docs[rows[q]["gold"]]
        write_input(out / "in1" / f"{q}.md", p1, qid=q, query=texts[q],
                    question_comment=wrap_lines(labels[q], g.max_line_chars),
                    document=f"{meta_text(gd, g.agenda_chars)}\n\n"
                             f"{wrap_lines(gd['context'], g.max_line_chars)}")
        top_text = "\n\n".join(
            f"### {i}위\n{doc_block(docs[d], chunks[picks[q][d]], g)}"
            for i, d in enumerate(r["top"], 1))
        write_input(out / "in2" / f"{q}.md", p2, qid=q, query=texts[q],
                    gold=doc_block(gd, chunks[picks[q][r["gold"]]], g),
                    gold_rank=r["final_rank"] or f"{rcfg.retriever.top_k}위 밖", top=top_text)
    (out / "ids.txt").write_text("\n".join(miss) + "\n", encoding="utf-8")
    with (out / "rows.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for q in miss:
            f.write(json.dumps(rows[q], ensure_ascii=False) + "\n")
    print(f"실패 {len(miss)} / {len(gold)} -> {cfg.paths.g2_dir}")
    print(Counter(r["rank_type"] for r in rows.values()))


def review(cfg) -> None:
    out = ROOT / cfg.paths.g2_dir
    rows = [json.loads(x) for x in (out / "rows.jsonl").open(encoding="utf-8")]
    missing = [r["qid"] for r in rows for s in ["out1", "out2"]
               if not (out / s / f"{r['qid']}.json").exists()]
    if missing:
        missing = sorted(set(missing))
        raise SystemExit(f"작업자 출력이 없는 질의 {len(missing)}개: {missing[:5]}")
    rcfg = load_cfg([f"+exp={cfg.g2.exp}", "index.scope=full"])
    qids, path = query_list(rcfg)
    texts = dict(zip(qids, read_texts(path, qids), strict=True))
    blocks, tally, cross = [], Counter(), Counter()
    for r in rows:
        q = r["qid"]
        s1 = json.loads((out / "out1" / f"{q}.json").read_text(encoding="utf-8"))
        s2 = json.loads((out / "out2" / f"{q}.json").read_text(encoding="utf-8"))
        cls = final_class(s1, s2)
        detail = r["rank_type"] if cls == "개선 가능" else s1["reason"] or "다른 정답"
        tally[(cls, detail)] += 1
        cross[(s1["identifiable"], s2["other_answer"])] += 1
        blocks.append(((cls, detail, q), [
            f"## {q}", "", f"- 질의: {texts[q]}",
            f"- 입력: `{cfg.paths.g2_dir}/in1/{q}.md`(정답 문서 전체), `in2/{q}.md`(상위 5개)",
            f"- 순위: 최종 {r['final_rank']}, 목록별 {r['list_ranks']}, "
            f"유형 {r['rank_type']}, 1위가 같은 회의 {r['same_meeting_top1']}",
            f"- 1단계(특정 가능성): {s1['identifiable']}, {s1['reason']} / {s1['evidence']}",
            f"- 2단계(다른 정답 {s2['other_answer']} {s2['other_ranks']}, "
            f"원인 {s2['cause']}): {s2['evidence']}",
            f"- 에이전트 분류: **{cls}** ({detail})",
            "- 사람: [ ] 동의  [ ] 수정 →", "- 메모:", ""]))
    # 분류·세부 순으로 묶어 개선 가능 항목을 먼저 본다
    lines = [x for _, block in sorted(blocks, key=lambda b: b[0]) for x in block]
    head = ["# G2 기준 오답 질의 검토", "",
            f"입력 `{cfg.paths.g2_dir}/in1·in2`, 지시 {cfg.g2.stage1}·{cfg.g2.stage2}. "
            "분류 규칙: 1단계 특정 불가이거나 2단계 다른 정답 있음이면 좁힐 수 없음. "
            "2단계 입력의 정답 문서는 질의와 dense 점수가 가장 가까운 청크 하나라, 답이 문서의 "
            "다른 곳에 있으면 정답을 약하게 볼 수 있다.", "",
            "| 분류 | 세부 | 수 |", "| --- | --- | ---: |",
            *[f"| {c} | {k} | {n} |" for (c, k), n in sorted(tally.items())], "",
            "| 1단계 특정 가능 | 2단계 다른 정답 | 수 |", "| --- | --- | ---: |",
            *[f"| {i} | {o} | {n} |" for (i, o), n in sorted(cross.items())], "",
            "항목은 분류·세부 순서다(개선 가능이 먼저).", ""]
    path = out.parent / "g2_failures.md"
    path.write_text("\n".join(head + lines), encoding="utf-8")
    print(f"{len(rows)}개 -> {path.relative_to(ROOT)}")
    for (c, k), n in sorted(tally.items()):
        print(c, k, n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "review"])
    args = ap.parse_args()
    cfg = load_cfg()
    {"prepare": prepare, "review": review}[args.cmd](cfg)


if __name__ == "__main__":
    main()
