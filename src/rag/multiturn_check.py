"""지어낸 대화 표본을 로컬에서 차례로 돌려 후속 답변의 동작을 기록한다(S51).

앱과 같은 chat_events를 지나며, 턴마다 검색 질의, 판단 값, 다시 넣은 앞 근거, 근거, 생성 원문과
화면 글, 기계 검사(인용 누락, 거부 없는 되풀이, 앞 근거 라벨 일치)를 paths.multiturn_runs에 남긴다.
사용자가 읽을 질문·답변 문서(.md)를 함께 쓴다. 표본은 평가 질의가 아니고 판정에 쓰지 않는다.
로컬에는 GPU가 없어 retriever.rerank.enabled=false로 실행한다.
명세는 docs/slices/51-evidence-reuse.md.
"""

import json
import sys
from difflib import SequenceMatcher

from langsmith.run_trees import get_cached_client
from omegaconf import OmegaConf

from rag.app import CITATION, chat_events, follow_up
from rag.docs import Corpus
from rag.gen_eval.checks import citation_check, refusal_split
from rag.generate import Pipeline, recipe
from rag.index import ROOT, load_cfg, refuse_existing


def checks(cfg, raw: str, prev_raw: str | None, n_ctx: int) -> dict:
    """답변 하나의 기계 검사. 거부 문장을 뺀 나머지로 인용을 보고(judge와 같은 방식), 앞 답변이
    있으면 인용 번호를 지운 글끼리 유사도를 잰다."""
    g = cfg.gen_eval
    kind, _, rest = refusal_split(raw, cfg.prompt.refusal, list(g.filler_phrases),
                                  list(g.unlisted_refusal))
    cit = None if kind == "full" else citation_check(rest, n_ctx, list(g.filler_phrases))
    out = {"refusal": kind, "citations": cit,
           "uncited": bool(cit and (cit["uncited"] or cit["invalid"]))}
    if prev_raw is not None:
        sim = SequenceMatcher(None, CITATION.sub("", prev_raw), CITATION.sub("", raw)).ratio()
        out["repeat_ratio"] = round(sim, 3)
        out["repeat"] = sim >= cfg.app.multiturn.check.repeat_min and kind is None
    return out


def run_conversation(pipe, cfg, rec: dict, corpus, follow, conv: dict) -> list[dict]:
    """대화 하나를 페이지처럼 차례로 보낸다. 앞 대화에는 생성 원문과 인용한 청크 번호를 쌓는다."""
    history, out = [], []
    for i, turn in enumerate(conv["turns"]):
        log: dict = {}
        events = list(chat_events(pipe, cfg, rec, corpus, turn["q"], history, follow, log))
        final = events[-1]
        prev_raw = history[-1]["answer"] if history else None
        ctx = log.get("contexts", [])
        reused = [c["doc_id"] for c in ctx if c["stages"].get("reused")]
        # 앞 턴이 앞 대화에 들어가지 못했으면 앱은 이 턴을 첫 질문으로 처리한다
        row = {"cid": conv["cid"], "turn": i + 1, "follow": bool(history), "q": turn["q"],
               "label": turn,
               "search": log.get("search"), "meta": log.get("meta"), "prev_rows": log.get("prev"),
               "reused_docs": reused, "first_token_s": log.get("first_token_s"),
               "contexts": [{"n": c["n"], "doc_id": c["doc_id"], "date": c["date"],
                             "committee_name": c["committee_name"]} for c in ctx],
               "raw": final["raw"], "shown": final["text"],
               "checks": checks(cfg, final["raw"], prev_raw, len(ctx))}
        if history and "needs_prev" in turn:
            row["checks"]["reuse_match"] = bool(reused) == turn["needs_prev"]
        out.append(row)
        if final["raw"]:  # 페이지와 같이 답을 만들지 못한 턴은 앞 대화에 넣지 않는다
            history.append({"question": turn["q"], "answer": final["raw"], "rows": final["rows"]})
    return out


def reading_doc(rows: list[dict]) -> str:
    """사용자가 읽을 문서. 질문과 화면에 나가는 답변 글만 담는다(S51 결정 사항 7)."""
    lines, cid = [], None
    for r in rows:
        if r["cid"] != cid:
            cid = r["cid"]
            lines.append(f"## 대화 {cid}\n")
        lines += [f"**질문 {r['turn']}**: {r['q']}\n", f"**답변 {r['turn']}**:\n\n{r['shown']}\n"]
    return "\n".join(lines)


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.retriever.get("rerank") and cfg.retriever.rerank.enabled:
        raise SystemExit("로컬 실행은 retriever.rerank.enabled=false로 한다(GPU 없음)")
    split = cfg.app.multiturn.check.split
    if split not in ("dev", "check"):
        raise SystemExit(f"app.multiturn.check.split은 dev·check 중 하나다: {split}")
    out = ROOT / cfg.paths.multiturn_runs
    doc = out.with_suffix(".md")
    refuse_existing(out, cfg.search.overwrite)
    refuse_existing(doc, cfg.search.overwrite)
    with (ROOT / cfg.paths.multiturn_set).open(encoding="utf-8") as f:
        convs = [c for c in map(json.loads, f) if c["split"] == split]
    if not convs:  # 빈 기록을 남기면 같은 경로로 다시 돌릴 때 막힌다
        raise SystemExit(f"{cfg.paths.multiturn_set}에 split={split}인 대화가 없다")
    pipe = Pipeline(cfg)
    rec = {**recipe(cfg, pipe.index_meta, True),
           "multiturn": OmegaConf.to_container(cfg.app.multiturn), "multiturn_split": split}
    rows = []
    try:
        follow, corpus = follow_up(cfg), Corpus(cfg)
        for conv in convs:
            rows += run_conversation(pipe, cfg, rec, corpus, follow, conv)
            print(f"{conv['cid']} 끝", flush=True)
    finally:  # 중간에 멈춰도 받은 답변은 남긴다
        get_cached_client().flush()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        doc.write_text(reading_doc(rows), encoding="utf-8", newline="\n")
    follow_rows = [r for r in rows if r["follow"]]
    c = [r["checks"] for r in follow_rows]
    print(f"{out.relative_to(ROOT)}: 대화 {len(convs)}개, 후속 답변 {len(c)}개, "
          f"인용 누락 {sum(x['uncited'] for x in c)}, "
          f"거부 없는 되풀이 {sum(x['repeat'] for x in c)}, "
          f"앞 근거 라벨 일치 {sum(x.get('reuse_match', False) for x in c)}/{len(c)}")


if __name__ == "__main__":
    main()
