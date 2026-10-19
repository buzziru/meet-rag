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

from rag.conditions import build_extractor
from rag.eval.metrics import load_gold
from rag.index import ROOT, encoder, load_cfg, load_model
from rag.retrieve import Retriever, chunks_by_doc, conditions_first
from rag.rewrite import needs_rewrite, rewrite_queries, signals

LAYERS = {"dev-small": "dev-small", "full": "dev-full"}  # index.scope → 평가 층


def rerank_top(docs: list[str], scores: dict[str, float], depth: int) -> list[str]:
    """상위 depth개를 reranker 점수 내림차순으로 바꾸고 나머지는 그대로 둔다(EXP-005)."""
    return sorted(docs[:depth], key=lambda d: -scores[d]) + docs[depth:]


def read_chunk_texts(dirs: list[Path], need: set[int]) -> dict[int, str]:
    """dense 청크 번호(인덱스를 이어 붙인 순서, load_dense와 같다)로 청크 본문을 읽는다."""
    chunk_text, offset = {}, 0
    for d in dirs:
        with (d / "chunks.jsonl").open(encoding="utf-8") as f:
            for i, line in enumerate(f, offset):
                if i in need:
                    chunk_text[i] = json.loads(line)["text"]
        offset = i + 1
    return chunk_text


def write_pairs(cfg, dirs: list[Path], picks: list[tuple[str, str, int]], texts: dict) -> None:
    """후보 쌍(qid, doc_id, 질의, 문서의 최고점 청크)을 질의 순서대로 쓴다."""
    chunk_text = read_chunk_texts(dirs, {c for _, _, c in picks})
    rows = [{"qid": qid, "doc_id": doc, "query": texts[qid], "text": chunk_text[c]}
            for qid, doc, c in picks]
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    # 재정렬 점수 파일은 이 후보 쌍으로 계산한다. 덮어쓰면 점수 파일과 쌍이 어긋난다
    state = write_guarded(ROOT / cfg.paths.rerank_pairs, text, cfg.search.overwrite)
    print(f"{len(picks):,} pairs -> {cfg.paths.rerank_pairs} ({state})")


def embed_queries(cfg, texts: list[str]) -> np.ndarray:
    model = load_model(cfg, cfg.embedding.query_max_tokens)
    encode = encoder(model, cfg, cfg.embedding.get("query_prompt"))
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


def write_guarded(path: Path, text: str, overwrite: bool) -> str:
    """실험 산출물(순위 파일, 재정렬 후보 쌍)을 쓴다. 같은 경로에 내용이 다른 파일이 있으면
    overwrite가 아닐 때 멈춘다(S12).

    run_name을 빠뜨린 실행이 과거 실험 기록(판정 기준 등)을 되돌릴 수 없게 덮어쓰지 않게 한다.
    """
    if path.exists() and not overwrite:
        if path.read_text(encoding="utf-8") == text:
            return "같은 내용, 그대로 둠"
        raise SystemExit(f"{path.relative_to(ROOT)}에 내용이 다른 파일이 있다. "
                         "retriever.run_name·경로를 확인하고, 바꾸려면 search.overwrite=true")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return "씀"


def write_run(path: Path, rows: list[dict], overwrite: bool) -> str:
    """순위 파일(qid, rank, doc_id)을 쓴다."""
    return write_guarded(path, pd.DataFrame(rows).to_csv(index=False, lineterminator="\n"),
                         overwrite)


def rewrite_ranks(cfg, ret, ranked, gated, qids, query_texts, q_emb, tokens, conds,
                  finish) -> None:
    """판단 규칙에 걸린 질의(gated, qids 위치)를 재작성하고, 재작성 질의의 목록을 더한 순위로
    ranked를 바꾼다(EXP-013). 재작성이 비거나 형식이 틀린 질의는 원 순위를 둔다."""
    rewrites = rewrite_queries(cfg, {qids[j]: query_texts[j] for j in gated})
    ok = [j for j in gated if rewrites[qids[j]] is not None]
    print(f"재작성 대상 {len(gated)}/{len(qids)}건({len(gated) / len(qids):.1%}), "
          f"형식 통과 {len(ok)}건")
    if not ok:
        return
    rw_texts = [rewrites[qids[j]] for j in ok]
    rw_emb = embed_queries(cfg, rw_texts)
    rw_tokens = ret.query_tokens(rw_texts)
    for k, j in enumerate(ok):
        row = ret.chunk_emb @ q_emb[j]
        docs, matched, _ = ret.candidates(row, tokens[j], conds.get(qids[j]),
                                          rewrite=(ret.chunk_emb @ rw_emb[k], rw_tokens[k]))
        ranked[qids[j]] = finish(qids[j], docs, matched)


def search(cfg) -> None:
    files = query_files(cfg)
    ret = Retriever(cfg)
    qids, text_path = query_list(cfg)
    q_emb = query_embeddings(cfg, qids, text_path, files["emb"])
    r = cfg.retriever
    query_texts = read_texts(text_path, qids)
    tokens = ret.query_tokens(query_texts)
    conds = {}
    if ret.use_cond:
        # 생성과 같이 실행 config의 추출기로 질의 원문에서 뽑는다. 미리 만든 조건 파일을 읽으면
        # 추출 설정·값 사전이 바뀐 뒤 옛 파일이 조용히 쓰일 수 있다(S12, PR #71 코멘트)
        ex = build_extractor(cfg)
        conds = {q: ex.extract(t) for q, t in zip(qids, query_texts, strict=True)}
    export_pairs = cfg.search.mode == "rerank-pairs"
    use_rerank = ret.hybrid and r.get("rerank") and r.rerank.enabled and not export_pairs
    if export_pairs:
        doc_chunks = chunks_by_doc(ret.dense_ids)
        texts = dict(zip(qids, query_texts, strict=True))
        picks = []
    if use_rerank:
        rerank_scores: dict[str, dict[str, float]] = {}
        with (ROOT / cfg.paths.rerank_scores).open(encoding="utf-8") as f:
            for x in map(json.loads, f):
                rerank_scores.setdefault(x["qid"], {})[x["doc_id"]] = x["score"]
    use_rewrite = bool(r.get("rewrite") and r.rewrite.enabled)
    if use_rewrite and (export_pairs or use_rerank):
        raise SystemExit("retriever.rewrite는 재정렬(rerank-pairs, rerank)과 함께 쓰지 않는다")

    def finish(qid: str, docs: list[str], matched: set[str]) -> list[str]:
        if ret.hybrid:
            if use_rerank:
                docs = rerank_top(docs, rerank_scores[qid], r.rerank.depth)
            docs = conditions_first(docs, matched)[: r.top_k]
        return docs

    ranked, gated, fallbacks = {}, [], 0
    for start in range(0, len(qids), r.query_batch):
        scores = q_emb[start : start + r.query_batch] @ ret.chunk_emb.T
        for j, row in enumerate(scores, start):
            named, matched, full = ret.lists(row, tokens[j] if tokens else None,
                                             conds.get(qids[j]))
            fallbacks += full
            docs = ret.fuse(named)
            if ret.hybrid and export_pairs:
                picks += [(qids[j], d, int(doc_chunks[d][np.argmax(row[doc_chunks[d]])]))
                          for d in docs[: r.rerank.depth]]
                continue
            if use_rewrite and needs_rewrite(
                    signals(named, row, ret.chunk_doc, len(ret.doc_names), r.rewrite.gate),
                    r.rewrite.gate):
                gated.append(j)
            ranked[qids[j]] = finish(qids[j], docs, matched)
    if export_pairs:
        write_pairs(cfg, ret.dirs, picks, texts)
        return
    if use_rewrite:
        rewrite_ranks(cfg, ret, ranked, gated, qids, query_texts, q_emb, tokens, conds, finish)
    rows = [{"qid": q, "rank": i, "doc_id": d}
            for q in qids for i, d in enumerate(ranked[q], 1)]
    # dense는 기존 이름을 유지해 기준 순위 파일과 같은 경로를 쓴다. run_name이 있으면 그 이름을 쓴다
    name = r.get("run_name") or r.type
    kind = "" if name == "dense" else f"-{name}"
    out = ROOT / cfg.paths.runs_dir / f"{ret.index_dir.parent.name}{kind}-{files['name']}.csv"
    state = write_run(out, rows, cfg.search.overwrite)
    print(f"{len(qids)} queries -> {out.relative_to(ROOT)} ({state}, 전체 정렬 {fallbacks}건)")


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    mode = cfg.search.mode
    if mode in ("export-queries", "embed-queries") and cfg.index.scope != "full":
        raise SystemExit(f"{mode}는 index.scope=full에서만 쓴다")
    {"run": search, "rerank-pairs": search, "export-queries": export_queries,
     "embed-queries": embed_vm_queries}[mode](cfg)


if __name__ == "__main__":
    main()
