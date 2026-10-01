"""청크 크기 후보의 dev-small 순위 파일을 채점해 비교표를 낸다.

결정 규칙과 보고 형식은 docs/slices/04-index.md "비교와 결정".
"""

import json

import numpy as np
import pandas as pd

from rag.eval.bootstrap import paired_bootstrap
from rag.eval.metrics import gold_ranks, load_gold, min_docs, per_query, read_run, to_markdown
from rag.index import ROOT, load_cfg

LAYER = "dev-small"
PRIMARY = "recall@5"


def query_metrics(ranks: pd.Series, recall_ks, mrr_ks) -> pd.DataFrame:
    out = per_query(ranks, recall_ks, mrr_ks[0])
    for k in mrr_ks[1:]:
        out[f"mrr@{k}"] = per_query(ranks, [], k)[f"mrr@{k}"]
    return out


def main() -> None:
    base = load_cfg()
    sw = base.chunk_sweep
    gold = load_gold(base, LAYER)
    n_min = min_docs(sw.recall_ks, max(sw.mrr_ks))

    scores, ranks, info = {}, {}, {}
    for ct, ov in sw.candidates:
        cfg = load_cfg([f"chunking.chunk_tokens={ct}", f"chunking.overlap_tokens={ov}"])
        index_dir = ROOT / cfg.paths.index_dir
        name = str(ct)
        run = ROOT / cfg.paths.runs_dir / f"{index_dir.parent.name}-{LAYER}.csv"
        ranks[name] = gold_ranks(read_run(run), gold, n_min)
        scores[name] = query_metrics(ranks[name], sw.recall_ks, sw.mrr_ks)
        meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))
        info[name] = {"chunk_tokens": ct, "overlap_tokens": ov, "n_chunks": meta["n_chunks"],
                      "chunks_per_doc": round(meta["n_chunks"] / meta["n_docs"], 2)}

    overall = pd.DataFrame(
        [{"size": n, **info[n], **scores[n].mean().round(4).to_dict()} for n in scores]
    )
    best = max(scores, key=lambda n: scores[n][PRIMARY].mean())
    bs = base.eval.bootstrap
    groups = gold[bs.unit].to_numpy()
    diffs = []
    for n in scores:
        point, lo, hi = paired_bootstrap(
            (scores[n][PRIMARY] - scores[best][PRIMARY]).to_numpy(), groups,
            bs.n_resamples, bs.seed, bs.alpha,
        )
        diffs.append({"size": n, "diff_vs_best": round(point, 4), "ci_lo": round(lo, 4),
                      "ci_hi": round(hi, 4), "ci_has_0": bool(lo <= 0 <= hi)})
    breakdown = pd.DataFrame([
        {"group": col, "value": value, "size": n, "n": len(part), **part.mean().round(4).to_dict()}
        for col in base.eval.breakdowns
        for n in scores
        for value, part in scores[n].groupby(gold[col])
    ])

    print(f"## 전체 (dev-small, 질의 {len(gold)})\n\n{to_markdown(overall)}\n")
    print(f"## {PRIMARY} 기준 후보({best}) 대비 차이\n\n{to_markdown(pd.DataFrame(diffs))}\n")
    print(f"## 회의구분·qna_type별\n\n{to_markdown(breakdown)}")

    per_query_ranks = pd.DataFrame(ranks).replace({np.nan: None})
    result = {
        "layer": LAYER, "primary": PRIMARY, "best": best,
        "overall": overall.to_dict(orient="records"), "diff_vs_best": diffs,
        "breakdown": breakdown.to_dict(orient="records"),
        "per_query_gold_rank": per_query_ranks.to_dict(orient="index"),
    }
    out = ROOT / base.paths.runs_dir / "chunk_sweep.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
