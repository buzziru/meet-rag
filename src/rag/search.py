"""평가 층 질의(search.queries=summary_q) 또는 multi-doc 동결 세트 질의(multidoc)로
인덱스를 전수 검색해 순위 파일을 쓴다.

질의 임베딩은 한 번 만들어 캐시에 두고 다시 쓴다. dev-full·multi-doc 질의 임베딩은
qid·query만 내보낸 파일을 Colab에서 임베딩해 받아 온다(D-07).
명세는 docs/slices/04-index.md "검색", docs/slices/05-retrieve.md, docs/slices/09-multidoc-eval.md.
인자는 Hydra override.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rag.eval.metrics import load_gold
from rag.index import ROOT, encoder, load_cfg, load_embeddings, load_model

LAYERS = {"dev-small": "dev-small", "full": "dev-full"}  # index.scope → 평가 층


def first_docs(order: np.ndarray, chunk_doc_ids: np.ndarray, k: int) -> list[str]:
    """청크 순서에서 문서가 처음 나온 순서로 최대 k개 문서를 고른다."""
    seen: list[str] = []
    for i in order:
        doc = chunk_doc_ids[i]
        if doc not in seen:
            seen.append(doc)
            if len(seen) == k:
                break
    return seen


def rank_with_pool(scores: np.ndarray, chunk_doc_ids: np.ndarray, k: int,
                   pool: int | None) -> tuple[list[str], bool]:
    """점수 상위 pool개 청크로 문서 k개를 고른다. 모자라면 전체를 정렬한다.

    Returns:
        (문서 목록, 전체 정렬로 넘어갔는지). 결과는 전체 정렬과 같다(경계의 동점 제외).
    """
    if pool is not None and pool < len(scores):
        top = np.argpartition(-scores, pool - 1)[:pool]
        docs = first_docs(top[np.lexsort((top, -scores[top]))], chunk_doc_ids, k)
        if len(docs) == k:
            return docs, False
    return first_docs(np.argsort(-scores, kind="stable"), chunk_doc_ids, k), True


def rank_docs(scores: np.ndarray, chunk_doc_ids: np.ndarray, k: int,
              pool: int | None = None) -> list[str]:
    """청크 점수 내림차순에서 문서가 처음 나온 순서로 상위 k개 문서를 고른다."""
    return rank_with_pool(scores, chunk_doc_ids, k, pool)[0]


def embed_queries(cfg, texts: list[str]) -> np.ndarray:
    model = load_model(cfg, cfg.embedding.query_max_tokens)
    encode = encoder(model, cfg)
    step = cfg.embedding.max_batch_size
    return np.concatenate([encode(texts[i : i + step]) for i in range(0, len(texts), step)])


def query_files(cfg) -> dict:
    """search.queries에 따른 VM 업로드 파일, 임베딩 캐시, 순위 파일 이름. 파일은 읽지 않는다."""
    if cfg.search.queries == "multidoc":
        if cfg.index.scope != "full":
            raise SystemExit("search.queries=multidoc은 index.scope=full에서만 쓴다")
        return {"vm": ROOT / cfg.paths.queries_multidoc_vm,
                "emb": ROOT / cfg.paths.query_emb_multidoc, "name": "multidoc"}
    return {"vm": ROOT / cfg.paths.queries_dev, "emb": ROOT / cfg.paths.query_emb,
            "name": LAYERS[cfg.index.scope]}


def query_list(cfg) -> tuple[list[str], Path]:
    """질의 qid 목록(채점 순서)과 원문 파일. summary_q는 평가 층, multidoc은 동결 세트 순서다."""
    if cfg.search.queries == "multidoc":
        path = ROOT / cfg.paths.multidoc_frozen
        with path.open(encoding="utf-8") as f:
            return [json.loads(line)["qid"] for line in f], path
    return load_gold(cfg, LAYERS[cfg.index.scope]).index.tolist(), ROOT / cfg.paths.queries


def read_texts(path: Path, qids: list[str]) -> list[str]:
    keep = set(qids)
    text = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q["qid"] in keep:
                text[q["qid"]] = q["query"]
    return [text[q] for q in qids]


def save_query_emb(path: Path, qids: list[str], emb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, qids=np.array(qids), emb=emb)


def query_embeddings(cfg, qids: list[str], text_path: Path, emb_path: Path) -> np.ndarray:
    """캐시의 질의 목록이 같으면 캐시를, 아니면 로컬에서 임베딩해 캐시한다."""
    if emb_path.exists():
        cached = np.load(emb_path)
        if cached["qids"].tolist() == qids:
            return cached["emb"]
    emb = embed_queries(cfg, read_texts(text_path, qids))
    save_query_emb(emb_path, qids, emb)
    return emb


def export_queries(cfg) -> None:
    """질의의 qid·query만 채점 순서대로 VM 업로드 파일에 쓴다. 다른 필드는 VM에 보내지 않는다."""
    out = query_files(cfg)["vm"]
    qids, text_path = query_list(cfg)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for q, t in zip(qids, read_texts(text_path, qids), strict=True):
            f.write(json.dumps({"qid": q, "query": t}, ensure_ascii=False) + "\n")
    print(f"{len(qids)} queries -> {out.relative_to(ROOT)}")


def embed_vm_queries(cfg) -> None:
    """VM 업로드 파일만 읽어 임베딩한다. 원본 질의·분할·동결 세트 파일이 없는 VM에서 쓴다."""
    files = query_files(cfg)
    with files["vm"].open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    qids = [r["qid"] for r in rows]
    save_query_emb(files["emb"], qids, embed_queries(cfg, [r["query"] for r in rows]))
    print(f"{len(qids)} queries -> {files['emb'].relative_to(ROOT)}")


def search(cfg) -> None:
    files = query_files(cfg)
    index_dir = ROOT / cfg.paths.index_dir
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        chunk_doc_ids = np.array([json.loads(line)["doc_id"] for line in f])
    chunk_emb = load_embeddings(index_dir)

    qids, text_path = query_list(cfg)
    q_emb = query_embeddings(cfg, qids, text_path, files["emb"])
    r = cfg.retriever
    rows, fallbacks = [], 0
    for start in range(0, len(qids), r.query_batch):
        scores = q_emb[start : start + r.query_batch] @ chunk_emb.T
        for qid, row in zip(qids[start : start + r.query_batch], scores, strict=True):
            docs, full = rank_with_pool(row, chunk_doc_ids, r.top_k, r.chunk_pool)
            fallbacks += full
            rows += [{"qid": qid, "rank": i, "doc_id": d} for i, d in enumerate(docs, 1)]
    out = ROOT / cfg.paths.runs_dir / f"{index_dir.parent.name}-{files['name']}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, lineterminator="\n")
    print(f"{len(qids)} queries -> {out.relative_to(ROOT)} (전체 정렬 {fallbacks}건)")


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    mode = cfg.search.mode
    if mode in ("export-queries", "embed-queries") and cfg.index.scope != "full":
        raise SystemExit(f"{mode}는 index.scope=full에서만 쓴다")
    {"run": search, "export-queries": export_queries, "embed-queries": embed_vm_queries}[mode](cfg)


if __name__ == "__main__":
    main()
