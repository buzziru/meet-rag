"""생성 평가 표본의 검색 지표를 순위 파일에서 낸다(S46, D-87 결정 3).

rag.eval.score는 층 전체를 요구해 표본을 받지 않고 보호 경로라 고치지 않는다. 검색을 다시 돌리지
않고 순위 파일과 정답을 표본으로 줄여 같은 지표 함수로 계산한다. 생성 기록의 근거 문서가 순위 파일의
상위 문서와 다르면 멈춘다. 지표가 답변의 입력을 설명하지 못하기 때문이다. 질의 원문은 출력하지
않는다. 인자는 Hydra override(test 1회 명령: slices/46-gen-test.md. dev는
gen_eval.retrieval_run=<순위 파일>).
"""

import json
import sys

from rag.eval.metrics import (
    gold_ranks,
    load_gold,
    metric_table,
    min_docs,
    per_query,
    read_run,
    to_markdown,
)
from rag.gen_eval.common import check_test_input, check_test_layer, eval_qids, read_jsonl
from rag.index import ROOT, load_cfg, write_guarded


def check_contexts(gens: dict[str, dict], run, qids: list[str], k: int) -> None:
    """질의마다 생성 기록의 근거 문서 순서가 순위 파일의 서로 다른 상위 k개 문서와 같은지 본다."""
    top = (run.sort_values(["qid", "rank"]).drop_duplicates(["qid", "doc_id"])
           .groupby("qid")["doc_id"].apply(lambda s: list(s)[:k]).to_dict())
    missing = [q for q in qids if q not in gens]
    if missing:
        raise SystemExit(f"생성 기록에 없는 질의 {len(missing)}개: {missing[:5]}")
    differ = [q for q in qids if [c["doc_id"] for c in gens[q]["contexts"]] != top.get(q)]
    if differ:
        raise SystemExit(f"근거 문서가 순위 파일과 다른 질의 {len(differ)}개: {differ[:5]}. "
                         "지금 검색이 이 순위 파일과 다른 순위를 낸다. 멈추고 보고한다")


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    g, ev = cfg.gen_eval, cfg.eval
    test = g.queries == "test"
    if test:  # 라벨을 읽기 전에 본다
        check_test_layer(cfg)
        check_test_input(cfg, "run")
    elif not g.retrieval_run:
        raise SystemExit("dev 층은 gen_eval.retrieval_run=<순위 파일>을 준다")
    qids = eval_qids(cfg)
    path = g.test_inputs.run.path if test else g.retrieval_run

    keep = set(qids)
    run = read_run(ROOT / path)
    run = run[run["qid"].isin(keep)]
    gold = load_gold(cfg, "test", allow_test=True) if test else load_gold(cfg, g.queries)
    gold = gold[gold.index.isin(keep)]
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    check_contexts(gens, run, qids, cfg.generator.context_docs)

    ranks = gold_ranks(run, gold, min_docs(ev.recall_ks, ev.mrr_k))
    table = metric_table(per_query(ranks, ev.recall_ks, ev.mrr_k), gold, ev.breakdowns)
    print(f"layer: {g.queries}, 질의 {len(qids)}개\nrun: {path}\n{to_markdown(table)}")
    result = {"layer": g.queries, "n_queries": len(qids), "run": path,
              "metrics": table.to_dict(orient="records")}
    out = ROOT / cfg.paths.gen_retrieval
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(f"-> {cfg.paths.gen_retrieval} ({write_guarded(out, text, cfg.search.overwrite)})")


if __name__ == "__main__":
    main()
