"""dev-small 질의로 인덱스를 전수 검색해 순위 파일을 쓴다.

질의 임베딩은 한 번 만들어 paths.query_emb에 두고 청크 크기 후보끼리 다시 쓴다.
명세는 docs/slices/04-index.md "검색". 인자는 Hydra override.
"""

import json
import sys

import numpy as np
import pandas as pd

from rag.eval.metrics import load_gold
from rag.index import ROOT, encoder, load_cfg, load_embeddings, load_model

LAYER = "dev-small"


def rank_docs(scores: np.ndarray, chunk_doc_ids: np.ndarray, k: int) -> list[str]:
    """청크 점수 내림차순에서 문서가 처음 나온 순서로 상위 k개 문서를 고른다."""
    seen: list[str] = []
    for i in np.argsort(-scores, kind="stable"):
        doc = chunk_doc_ids[i]
        if doc not in seen:
            seen.append(doc)
            if len(seen) == k:
                break
    return seen


def query_embeddings(cfg, qids: list[str]) -> np.ndarray:
    path = ROOT / cfg.paths.query_emb
    if path.exists():
        cached = np.load(path)
        if cached["qids"].tolist() == qids:
            return cached["emb"]
    text = {}
    keep = set(qids)
    with (ROOT / cfg.paths.queries).open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q["qid"] in keep:
                text[q["qid"]] = q["query"]
    model = load_model(cfg, cfg.embedding.query_max_tokens)
    emb = encoder(model, cfg)([text[q] for q in qids])
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, qids=np.array(qids), emb=emb)
    return emb


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    if cfg.index.scope != LAYER:
        raise SystemExit("전수 검색은 dev-small 인덱스에만 쓴다 (dev-full은 S5)")
    index_dir = ROOT / cfg.paths.index_dir
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        chunk_doc_ids = np.array([json.loads(line)["doc_id"] for line in f])
    chunk_emb = load_embeddings(index_dir)

    qids = load_gold(cfg, LAYER).index.tolist()
    scores = query_embeddings(cfg, qids) @ chunk_emb.T
    rows = [
        {"qid": qid, "rank": r, "doc_id": doc}
        for qid, row in zip(qids, scores, strict=True)
        for r, doc in enumerate(rank_docs(row, chunk_doc_ids, cfg.retriever.top_k), 1)
    ]
    out = ROOT / cfg.paths.runs_dir / f"{index_dir.parent.name}-{LAYER}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, lineterminator="\n")
    print(f"{len(qids)} queries -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
