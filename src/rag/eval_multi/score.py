"""순위 파일 하나를 multi-doc 동결 세트로 채점한다. 명세는 docs/slices/09-multidoc-eval.md."""

import argparse
import json
from pathlib import Path

from rag.eval_multi.metrics import (
    load_gold,
    metric_table,
    per_query,
    ranked_docs,
    read_run,
    sha256,
    to_markdown,
)
from rag.index import ROOT, load_cfg


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    cfg = load_cfg()
    ev = cfg.multidoc.eval
    frozen = ROOT / cfg.paths.multidoc_frozen
    gold = load_gold(frozen)
    scores = per_query(ranked_docs(read_run(args.run), gold, max(ev.ks)), gold, ev.ks)
    table = metric_table(scores, gold, ev.breakdowns)

    digest, frozen_digest = sha256(args.run), sha256(frozen)
    print(f"run: {args.run} (sha256 {digest})\nfrozen: {frozen_digest}\n")
    print(to_markdown(table))
    if args.out:
        result = {"run": str(args.run), "run_sha256": digest, "frozen_sha256": frozen_digest,
                  "metrics": table.to_dict(orient="records")}
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
