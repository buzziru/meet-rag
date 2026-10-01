"""순위 파일 하나를 평가 층에서 채점한다. 명세는 docs/slices/03-eval.md."""

import argparse
import json
from pathlib import Path

from rag.eval.metrics import (
    LAYERS,
    gold_ranks,
    load_cfg,
    load_gold,
    metric_table,
    min_docs,
    per_query,
    read_run,
    sha256,
    to_markdown,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--layer", choices=LAYERS, required=True)
    p.add_argument("--allow-test", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    cfg = load_cfg()
    gold = load_gold(cfg, args.layer, args.allow_test)
    ev = cfg.eval
    ranks = gold_ranks(read_run(args.run), gold, min_docs(ev.recall_ks, ev.mrr_k))
    scores = per_query(ranks, ev.recall_ks, ev.mrr_k)
    table = metric_table(scores, gold, ev.breakdowns)

    digest = sha256(args.run)
    print(f"layer: {args.layer}\nrun: {args.run} (sha256 {digest})\n")
    print(to_markdown(table))
    if args.out:
        result = {"layer": args.layer, "run": str(args.run), "run_sha256": digest,
                  "metrics": table.to_dict(orient="records")}
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
