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
from rag.index import ROOT, encoder, load_cfg, load_model, write_guarded
from rag.retrieve import (
    ChunkStore,
    Retriever,
    adopt_query_basis,
    best_chunks,
    chunks_by_doc,
    query_basis_path,
    read_query_emb,
    read_rerank_scores,
    save_query_emb,
)
from rag.rewrite import needs_rewrite, rewrite_queries, signals

LAYERS = {"dev-small": "dev-small", "full": "dev-full"}  # index.scope → 평가 층


def write_pairs(cfg, dirs: list[Path], picks: list[tuple[str, str, int]], texts: dict) -> None:
    """후보 쌍(qid, doc_id, 질의, 문서의 최고점 청크)을 질의 순서대로 쓴다."""
    chunk_text = ChunkStore(dirs).texts({c for _, _, c in picks})
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


def check_test(cfg) -> None:
    """test 질의는 검색 단계 종료 시 1회만 쓴다(SPEC).

    명시적으로 허용해야 하고 질의 임베딩은 로컬에서만 한다.
    """
    if cfg.index.scope != "full":
        raise SystemExit("search.queries=test는 index.scope=full에서만 쓴다")
    if not cfg.search.allow_test:
        raise SystemExit("search.queries=test는 search.allow_test=true가 있어야 쓴다 "
                         "(검색 단계 종료 시 1회)")
    if cfg.search.mode in ("export-queries", "embed-queries"):
        raise SystemExit("test 질의는 VM 업로드 파일로 내보내지 않는다. "
                         "질의 임베딩은 로컬에서 한다")


def query_files(cfg) -> dict:
    """search.queries에 따른 VM 업로드 파일, 임베딩 캐시, 순위 파일 이름. 파일은 읽지 않는다."""
    if cfg.search.queries == "multidoc":
        if cfg.index.scope != "full":
            raise SystemExit("search.queries=multidoc은 index.scope=full에서만 쓴다")
        return {"vm": ROOT / cfg.paths.queries_multidoc_vm,
                "emb": ROOT / cfg.paths.query_emb_multidoc, "name": "multidoc"}
    if cfg.search.queries == "test":
        check_test(cfg)
        return {"vm": None, "emb": ROOT / cfg.paths.query_emb_test, "name": "test"}
    return {"vm": ROOT / cfg.paths.queries_dev, "emb": ROOT / cfg.paths.query_emb,
            "name": LAYERS[cfg.index.scope]}


def query_list(cfg) -> tuple[list[str], Path]:
    """질의 qid 목록(채점 순서)과 원문 파일. summary_q는 평가 층, multidoc은 동결 세트 순서다."""
    if cfg.search.queries == "multidoc":
        path = ROOT / cfg.paths.multidoc_frozen
        with path.open(encoding="utf-8") as f:
            return [json.loads(line)["qid"] for line in f], path
    if cfg.search.queries == "test":
        check_test(cfg)
        return load_gold(cfg, "test", allow_test=True).index.tolist(), ROOT / cfg.paths.queries
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


def query_embeddings(cfg, qids: list[str], emb_path: Path) -> np.ndarray:
    """질의 임베딩 캐시를 지문(S21)과 질의 목록을 대조해 읽는다. 캐시가 없거나 목록이 다르면
    로컬에서 임베딩하지 않고 멈춘다. 로컬 CPU 임베딩은 오래 걸리고, Colab에서 만든 캐시와 값이
    달라지면 검색 결과와 그 뒤 생성 평가가 바뀔 수 있다(이슈 #142)."""
    guide = "캐시는 Colab embed-queries로 만든다(slices/05-retrieve.md)"
    if not emb_path.exists():
        raise SystemExit(f"질의 임베딩 캐시가 없다: {emb_path}. 로컬에서 임베딩하지 않는다. "
                         f"{guide}")
    cached_qids, emb = read_query_emb(cfg, emb_path)
    if cached_qids != qids:
        raise SystemExit(f"질의 임베딩 캐시의 질의 목록이 지금과 다르다: {emb_path} "
                         f"(캐시 {len(cached_qids)}개, 지금 {len(qids)}개). 덮어쓰지 않는다. "
                         f"다시 만들려면 캐시를 다른 이름으로 옮긴 뒤 {guide}")
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
    save_query_emb(cfg, files["emb"], qids, embed_queries(cfg, [r["query"] for r in rows]))
    print(f"{len(qids)} queries -> {files['emb'].relative_to(ROOT)}")


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
    q_emb = query_embeddings(cfg, qids, files["emb"])
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
    use_rerank = ret.use_rerank and not export_pairs
    if export_pairs:
        doc_chunks = chunks_by_doc(ret.dense_ids)
        texts = dict(zip(qids, query_texts, strict=True))
        picks = []
    if use_rerank:
        rerank_scores = read_rerank_scores(cfg)
    use_rewrite = bool(r.get("rewrite") and r.rewrite.enabled)
    if use_rewrite and (export_pairs or use_rerank):
        raise SystemExit("retriever.rewrite는 재정렬(rerank-pairs, rerank)과 함께 쓰지 않는다")

    def finish(qid: str, docs: list[str], matched: set[str]) -> list[str]:
        return ret.final(docs, matched, rerank_scores[qid] if use_rerank else None)

    ranked, gated, fallbacks = {}, [], 0
    for start in range(0, len(qids), r.query_batch):
        scores = q_emb[start : start + r.query_batch] @ ret.chunk_emb.T
        for j, row in enumerate(scores, start):
            named, matched, full = ret.lists(row, tokens[j] if tokens else None,
                                             conds.get(qids[j]))
            fallbacks += full
            docs = ret.fuse(named)
            if ret.hybrid and export_pairs:
                head = docs[: r.rerank.depth]
                picks += [(qids[j], d, c) for d, c in
                          zip(head, best_chunks(row, doc_chunks, head), strict=True)]
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
    if cfg.adopt_basis:  # 지문 없는 기존 질의 임베딩 캐시에 지문만 쓰고 끝낸다(S21)
        path = query_files(cfg)["emb"]
        print(f"{query_basis_path(path).relative_to(ROOT)} ({adopt_query_basis(cfg, path)})")
        return
    mode = cfg.search.mode
    if mode in ("export-queries", "embed-queries") and cfg.index.scope != "full":
        raise SystemExit(f"{mode}는 index.scope=full에서만 쓴다")
    {"run": search, "rerank-pairs": search, "export-queries": export_queries,
     "embed-queries": embed_vm_queries}[mode](cfg)


if __name__ == "__main__":
    main()
