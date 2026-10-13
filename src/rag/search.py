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

from rag.bm25 import BM25Retriever
from rag.conditions import ConditionIndex
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


def weighted_doc_scores(scores: np.ndarray, chunk_doc: np.ndarray, n_docs: int,
                        weights: list[float]) -> np.ndarray:
    """문서마다 i번째로 높은 청크 점수에 weights[i]를 곱해 더한다(EXP-007).

    [1.0]이면 최고점(max), [1.0, 1.0]이면 상위 2개 합, [1.0, 0.1]이면 max + 0.1·2위다.
    청크가 len(weights)개보다 적은 문서는 있는 것만 더한다.

    Args:
        scores: 청크 점수.
        chunk_doc: 청크의 문서 번호(0..n_docs-1).
        n_docs: 문서 수.
        weights: 순위별 가중치.

    Returns:
        문서 점수 배열(길이 n_docs).
    """
    order = np.lexsort((-scores, chunk_doc))  # 문서 번호 순, 문서 안에서 점수 내림차순
    docs = chunk_doc[order]
    first = np.r_[0, np.flatnonzero(docs[1:] != docs[:-1]) + 1]
    rank = np.arange(len(order)) - np.repeat(first, np.diff(np.r_[first, len(order)]))
    sel = rank < len(weights)
    keep = order[sel]
    w = np.asarray(weights, dtype=scores.dtype)[rank[sel]]
    out = np.zeros(n_docs, dtype=scores.dtype)
    np.add.at(out, chunk_doc[keep], scores[keep] * w)
    return out


def top_docs(doc_scores: np.ndarray, doc_names: np.ndarray, k: int) -> list[str]:
    """문서 점수 내림차순 상위 k개 문서. 같은 점수는 문서 번호 순."""
    return list(doc_names[np.argsort(-doc_scores, kind="stable")[:k]])


def rrf(rankings: list[list[str]], k: int, top_k: int | None) -> list[str]:
    """문서 순위 목록들을 RRF(Σ 1/(k + 순위))로 합친다. top_k가 None이면 후보 전체를 낸다.

    동점이면 앞 목록(dense)에 먼저 나온 문서가 앞선다.
    """
    score: dict[str, float] = {}
    for docs in rankings:
        for rank, doc in enumerate(docs, 1):
            score[doc] = score.get(doc, 0.0) + 1 / (k + rank)
    return sorted(score, key=score.__getitem__, reverse=True)[:top_k]


def conditions_first(docs: list[str], matched: set[str]) -> list[str]:
    """조건에 맞는 문서(matched)를 순서를 유지한 채 앞으로 옮긴다(EXP-004 필터링)."""
    return sorted(docs, key=lambda d: d not in matched)


def rerank_top(docs: list[str], scores: dict[str, float], depth: int) -> list[str]:
    """상위 depth개를 reranker 점수 내림차순으로 바꾸고 나머지는 그대로 둔다(EXP-005)."""
    return sorted(docs[:depth], key=lambda d: -scores[d]) + docs[depth:]


def chunks_by_doc(chunk_doc_ids: np.ndarray) -> dict[str, np.ndarray]:
    """문서마다 청크 번호 배열."""
    names, inv = np.unique(chunk_doc_ids, return_inverse=True)
    groups = np.split(np.argsort(inv, kind="stable"), np.cumsum(np.bincount(inv))[:-1])
    return dict(zip(names, groups, strict=True))


def write_pairs(cfg, index_dir: Path, picks: list[tuple[str, str, int]], texts: dict) -> None:
    """후보 쌍(qid, doc_id, 질의, 문서의 최고점 청크)을 질의 순서대로 쓴다."""
    need = {c for _, _, c in picks}
    chunk_text = {}
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i in need:
                chunk_text[i] = json.loads(line)["text"]
    out = ROOT / cfg.paths.rerank_pairs
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for qid, doc, c in picks:
            row = {"qid": qid, "doc_id": doc, "query": texts[qid], "text": chunk_text[c]}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(picks):,} pairs -> {cfg.paths.rerank_pairs}")


def condition_docs(counts: dict[int, int], doc_scores: np.ndarray, doc_names: np.ndarray,
                   depth: int, min_fields: int) -> list[str]:
    """조건 필드가 min_fields개 이상 맞은 문서를 맞은 필드 수, dense 문서 점수 내림차순으로
    depth개 고른다."""
    keep = [i for i, c in counts.items() if c >= min_fields]
    order = sorted(keep, key=lambda i: (-counts[i], -doc_scores[i], i))
    return [doc_names[i] for i in order[:depth]]


def condition_setup(cfg, chunk_doc_ids: np.ndarray):
    """조건 목록(EXP-003)에 쓰는 문서 이름, 청크의 문서 번호, 역색인, 질의 조건."""
    doc_names, chunk_doc = np.unique(chunk_doc_ids, return_inverse=True)
    pos = {d: i for i, d in enumerate(doc_names)}
    docs = [None] * len(doc_names)
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        for doc in map(json.loads, f):
            if doc["doc_id"] in pos:
                docs[pos[doc["doc_id"]]] = doc
    c = cfg.conditions
    law_min = c.law_min_chars if c.get("agenda_law") else None
    index = ConditionIndex(docs, cfg.retriever.conditions.year_ref_offsets, law_min)
    with (ROOT / cfg.paths.conditions).open(encoding="utf-8") as f:
        conds = {r["qid"]: r["conditions"] for r in map(json.loads, f)}
    return doc_names, chunk_doc, index, conds


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
    hybrid = r.type == "hybrid"
    if hybrid:
        bm25 = BM25Retriever(cfg, index_dir)
        q_ids = bm25.query_ids(read_texts(text_path, qids))
    use_cond = hybrid and r.get("conditions") and r.conditions.enabled
    if use_cond:
        doc_names, chunk_doc, cond_index, conds = condition_setup(cfg, chunk_doc_ids)
    export_pairs = cfg.search.mode == "rerank-pairs"
    use_rerank = hybrid and r.get("rerank") and r.rerank.enabled and not export_pairs
    if export_pairs:
        doc_chunks = chunks_by_doc(chunk_doc_ids)
        texts = dict(zip(qids, read_texts(text_path, qids), strict=True))
        picks = []
    if use_rerank:
        rerank_scores: dict[str, dict[str, float]] = {}
        with (ROOT / cfg.paths.rerank_scores).open(encoding="utf-8") as f:
            for x in map(json.loads, f):
                rerank_scores.setdefault(x["qid"], {})[x["doc_id"]] = x["score"]
    depth = r.fusion.depth if hybrid else r.top_k
    agg = r.get("doc_agg")
    weighted = agg is not None
    if weighted:
        agg_names, agg_doc = np.unique(chunk_doc_ids, return_inverse=True)
    rows, fallbacks = [], 0
    for start in range(0, len(qids), r.query_batch):
        scores = q_emb[start : start + r.query_batch] @ chunk_emb.T
        for j, row in enumerate(scores, start):
            if weighted:
                dense_scores = weighted_doc_scores(row, agg_doc, len(agg_names), list(agg.weights))
                docs = top_docs(dense_scores, agg_names, depth)
            else:
                docs, full = rank_with_pool(row, chunk_doc_ids, depth, r.chunk_pool)
                fallbacks += full
            if hybrid:
                lexical = rank_docs(bm25.scores(q_ids[j]), chunk_doc_ids, depth, r.chunk_pool)
                lists = [docs, lexical]
                counts = cond_index.match_counts(conds[qids[j]]) if use_cond else {}
                matched = set()
                if counts and max(counts.values()) >= r.conditions.min_fields:
                    if weighted:  # agg_names와 doc_names는 같은 np.unique 결과다
                        doc_scores = dense_scores
                    else:
                        doc_scores = np.full(len(doc_names), -np.inf, dtype=row.dtype)
                        np.maximum.at(doc_scores, chunk_doc, row)
                    lists.append(condition_docs(counts, doc_scores, doc_names, depth,
                                                r.conditions.min_fields))
                    if r.conditions.get("filter") == "best":  # 맞은 필드 수가 가장 많은 문서
                        top = max(counts.values())
                        matched = {doc_names[i] for i, c in counts.items() if c == top}
                fused = rrf(lists, r.fusion.rrf_k, None)
                if export_pairs:
                    picks += [(qids[j], d, int(doc_chunks[d][np.argmax(row[doc_chunks[d]])]))
                              for d in fused[: r.rerank.depth]]
                    continue
                if use_rerank:
                    fused = rerank_top(fused, rerank_scores[qids[j]], r.rerank.depth)
                docs = conditions_first(fused, matched)[: r.top_k]
            rows += [{"qid": qids[j], "rank": i, "doc_id": d} for i, d in enumerate(docs, 1)]
    if export_pairs:
        write_pairs(cfg, index_dir, picks, texts)
        return
    # dense는 기존 이름을 유지해 기준 순위 파일과 같은 경로를 쓴다. run_name이 있으면 그 이름을 쓴다
    name = r.get("run_name") or r.type
    kind = "" if name == "dense" else f"-{name}"
    out = ROOT / cfg.paths.runs_dir / f"{index_dir.parent.name}{kind}-{files['name']}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, lineterminator="\n")
    print(f"{len(qids)} queries -> {out.relative_to(ROOT)} (전체 정렬 {fallbacks}건)")


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    mode = cfg.search.mode
    if mode in ("export-queries", "embed-queries") and cfg.index.scope != "full":
        raise SystemExit(f"{mode}는 index.scope=full에서만 쓴다")
    {"run": search, "rerank-pairs": search, "export-queries": export_queries,
     "embed-queries": embed_vm_queries}[mode](cfg)


if __name__ == "__main__":
    main()
