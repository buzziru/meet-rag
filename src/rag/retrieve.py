"""평가(rag.search)와 생성(rag.generate)이 함께 쓰는 검색기(S12).

질의 하나의 dense 점수 행, BM25 토큰, 질의 조건을 받아 문서 순위를 낸다. 설정은 cfg.retriever다.
최종 순위(Retriever.final), 문서의 근거 청크 선택(best_chunks), 청크 본문 읽기(ChunkStore)도
평가와 생성이 여기서 같이 쓴다(S16). 후보 쌍 내보내기(EXP-005·006)는 평가 전용이라 rag.search에
있다.
규칙은 docs/slices/05-retrieve.md(dense), EXP-001·003·004·007·008·010·011·013·015·016 문서.
"""

import json
from pathlib import Path

import numpy as np

from rag.bm25 import BM25Retriever
from rag.conditions import ConditionIndex
from rag.index import (
    CHUNKS,
    ROOT,
    check_basis,
    corpus_meta,
    file_sha256,
    index_basis,
    index_path,
    load_embeddings,
)


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
    """점수 상위 pool개 청크로 문서 k개를 고른다. 모자라면 묶음을 두 배씩 키워 다시 고르고,
    묶음이 청크 수에 닿으면 전체를 정렬한다(S17).

    hybrid는 dense 목록에서 fusion.depth(100)개 문서를 골라, 첫 묶음 200개로는 자주 모자란다.
    전체 정렬로 바로 넘어가면 dev-full 질의 1,301건이 청크 약 34만 개를 정렬했다(S17 측정).

    Returns:
        (문서 목록, 전체 정렬로 넘어갔는지). 결과는 전체 정렬과 같다(경계의 동점 제외).
    """
    while pool is not None and pool < len(scores):
        top = np.argpartition(-scores, pool - 1)[:pool]
        docs = first_docs(top[np.lexsort((top, -scores[top]))], chunk_doc_ids, k)
        if len(docs) == k:
            return docs, False
        pool *= 2
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


def rrf_scores(rankings: list[list[str]], k: int,
               weights: list[float] | None = None) -> dict[str, float]:
    """문서마다 RRF 점수 Σ w / (k + 순위). 문서는 처음 나온 순서로 담는다(동점 순서의 기준)."""
    score: dict[str, float] = {}
    for i, docs in enumerate(rankings):
        w = weights[i] if weights else 1.0
        for rank, doc in enumerate(docs, 1):
            score[doc] = score.get(doc, 0.0) + w / (k + rank)
    return score


def rrf(rankings: list[list[str]], k: int, top_k: int | None,
        weights: list[float] | None = None) -> list[str]:
    """문서 순위 목록들을 RRF(Σ w / (k + 순위))로 합친다. top_k가 None이면 후보 전체를 낸다.

    weights는 목록마다의 가중치(EXP-010)이고 없으면 모두 1이다.
    동점이면 앞 목록(dense)에 먼저 나온 문서가 앞선다.
    """
    score = rrf_scores(rankings, k, weights)
    return sorted(score, key=score.__getitem__, reverse=True)[:top_k]


def minmax(docs: list[str], scores: list[float]) -> dict[str, float]:
    """순위 목록의 점수를 1위 1, 마지막 0으로 정규화한다(EXP-015). 점수가 모두 같으면 모두 0."""
    hi, lo = scores[0], scores[-1]
    if hi == lo:
        return dict.fromkeys(docs, 0.0)
    return {d: (s - lo) / (hi - lo) for d, s in zip(docs, scores, strict=True)}


def convex(dense: dict[str, float], bm25: dict[str, float], alpha: float) -> list[str]:
    """정규화 점수의 가중 합 alpha·dense + (1 − alpha)·BM25로 줄 세운다. 목록 밖 문서는 0.

    동점이면 dense 목록, BM25 목록 순으로 먼저 나온 문서가 앞선다.
    """
    docs = list(dict.fromkeys([*dense, *bm25]))
    score = {d: alpha * dense.get(d, 0.0) + (1 - alpha) * bm25.get(d, 0.0) for d in docs}
    return sorted(docs, key=score.__getitem__, reverse=True)


def conditions_first(docs: list[str], matched: set[str]) -> list[str]:
    """조건에 맞는 문서(matched)를 순서를 유지한 채 앞으로 옮긴다(EXP-004 필터링)."""
    return sorted(docs, key=lambda d: d not in matched)


def rerank_top(docs: list[str], scores: dict[str, float], depth: int) -> list[str]:
    """상위 depth개를 reranker 점수 내림차순으로 바꾸고 나머지는 그대로 둔다(EXP-005)."""
    return sorted(docs[:depth], key=lambda d: -scores[d]) + docs[depth:]


def rerank_basis_path(cfg) -> Path:
    scores = ROOT / cfg.paths.rerank_scores
    return scores.with_name(scores.name + ".basis.json")


def rerank_basis(cfg) -> dict:
    """재정렬 점수를 읽을 때 대조하는 지문(S15). device·dtype은 rag.rerank가 기록만 한다.
    EXP-017 점수는 Colab cuda·float16으로 만들었고 config 기본값은 로컬 cpu·float32다."""
    rr = cfg.retriever.rerank
    if rr.backend == "jev":
        b = {"backend": "jev", "model": rr.jev.model, "instructions": rr.jev.instructions,
             "levels": list(rr.jev.levels)}
    else:
        b = {"backend": rr.backend, "model": rr.model, "revision": rr.revision,
             "max_length": rr.max_length}
    return {**b, "pairs_sha256": file_sha256(ROOT / cfg.paths.rerank_pairs)}


def read_rerank_scores(cfg) -> dict[str, dict[str, float]]:
    """재정렬 점수 파일(rag.rerank)을 지문을 대조한 뒤 qid → 문서별 점수로 읽는다."""
    check_basis(rerank_basis_path(cfg), rerank_basis(cfg))
    path = ROOT / cfg.paths.rerank_scores
    scores: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8") as f:
        for x in map(json.loads, f):
            scores.setdefault(x["qid"], {})[x["doc_id"]] = x["score"]
    return scores


def final_order(fused: list[str], matched: set[str], rerank: dict[str, float] | None = None,
                depth: int = 0) -> list[str]:
    """결합 후보 → 재정렬(점수가 있을 때) → 최다 일치 필터. 평가(rag.search)와 생성이 같은
    순서 규칙을 쓴다(EXP-017, S14)."""
    if rerank is not None:
        fused = rerank_top(fused, rerank, depth)
    return conditions_first(fused, matched)


def condition_docs(counts: dict[int, int], doc_scores: np.ndarray, doc_names: np.ndarray,
                   depth: int, min_fields: int) -> list[str]:
    """조건 필드가 min_fields개 이상 맞은 문서를 맞은 필드 수, dense 문서 점수 내림차순으로
    depth개 고른다."""
    keep = [i for i, c in counts.items() if c >= min_fields]
    order = sorted(keep, key=lambda i: (-counts[i], -doc_scores[i], i))
    return [doc_names[i] for i in order[:depth]]


def chunks_by_doc(chunk_doc_ids: np.ndarray) -> dict[str, np.ndarray]:
    """문서마다 청크 번호 배열."""
    names, inv = np.unique(chunk_doc_ids, return_inverse=True)
    groups = np.split(np.argsort(inv, kind="stable"), np.cumsum(np.bincount(inv))[:-1])
    return dict(zip(names, groups, strict=True))


def best_chunks(scores: np.ndarray, doc_chunks: dict[str, np.ndarray],
                docs: list[str]) -> list[int]:
    """문서마다 dense 점수가 가장 높은 청크 번호를 문서 순서대로 돌려준다(D-05).

    재정렬 후보 쌍(rag.search)과 생성 근거(rag.generate)가 같은 청크를 쓴다(S16).
    추가 청크(retriever.extra_chunks)가 있으면 모든 크기의 청크 중에서 고른다(S12 결정 1).
    """
    return [int(doc_chunks[d][np.argmax(scores[doc_chunks[d]])]) for d in docs]


class ChunkStore:
    """dense 청크 번호(인덱스를 이어 붙인 순서, load_dense와 같다)로 청크 행을 읽는다.

    청크 텍스트를 모두 메모리에 올리지 않고 파일마다 줄 시작 위치만 들고 있다.
    """

    def __init__(self, dirs: list[Path]):
        self.paths, starts, sizes = [], [], []
        for d in dirs:
            offs = [0]
            with (d / CHUNKS).open("rb") as f:
                for line in f:
                    offs.append(offs[-1] + len(line))
            self.paths.append(d / CHUNKS)
            starts.append(np.array(offs[:-1]))
            sizes.append(len(offs) - 1)
        self.starts = starts
        self.bounds = np.cumsum([0, *sizes])
        self.names = [d.parent.name for d in dirs]

    def _locate(self, i: int) -> tuple[int, int]:
        k = int(np.searchsorted(self.bounds, i, side="right")) - 1
        return k, int(self.starts[k][i - self.bounds[k]])

    def get(self, i: int) -> dict:
        k, pos = self._locate(i)
        with self.paths[k].open("rb") as f:
            f.seek(pos)
            return {**json.loads(f.readline()), "index": self.names[k]}

    def texts(self, ids: set[int]) -> dict[int, str]:
        """여러 청크의 본문. 파일마다 한 번 열고 위치 순으로 읽는다."""
        by_file: dict[int, list[tuple[int, int]]] = {}
        for i in sorted(ids):
            k, pos = self._locate(i)
            by_file.setdefault(k, []).append((i, pos))
        out = {}
        for k, items in by_file.items():
            with self.paths[k].open("rb") as f:
                for i, pos in items:
                    f.seek(pos)
                    out[i] = json.loads(f.readline())["text"]
        return out


def read_doc_ids(index_dir: Path) -> np.ndarray:
    with (index_dir / CHUNKS).open(encoding="utf-8") as f:
        return np.array([json.loads(line)["doc_id"] for line in f])


def dense_chunkings(cfg) -> list:
    """dense 검색 인덱스의 청킹 설정. 기본 청킹 뒤에 retriever.extra_chunks를 붙인다(EXP-011)."""
    extra = cfg.retriever.get("extra_chunks") or []
    keys = set(cfg.chunking)
    for c in extra:  # 빠진 키를 기본 청킹 값으로 채우면 다른 인덱스를 조용히 고르게 된다
        if not hasattr(c, "keys") or set(c) != keys:
            raise ValueError(f"extra_chunks 항목은 {sorted(keys)} 키를 모두 적는다: {c}")
    return [cfg.chunking, *extra]


def dense_dirs(cfg) -> list[Path]:
    return [index_path(cfg, c) for c in dense_chunkings(cfg)]


def load_dense(dirs: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """dense 청크의 문서 id와 임베딩. 인덱스 순서대로 이어 붙인다. 인덱스마다 청크 수와 임베딩
    행 수가 다르면 멈춘다(행이 밀리면 다른 문서의 임베딩과 짝지어진다, S15)."""
    ids, embs = [read_doc_ids(d) for d in dirs], [load_embeddings(d) for d in dirs]
    for d, i, e in zip(dirs, ids, embs, strict=True):
        if len(i) != len(e):
            raise SystemExit(f"{d}: 청크 {len(i)}개와 임베딩 {len(e)}행이 다르다")
    return np.concatenate(ids), np.concatenate(embs)


class Retriever:
    """인덱스·BM25·조건 색인을 한 번 읽고 질의마다 문서 순위를 낸다."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.r = r = cfg.retriever
        self.index_dir = index_path(cfg, cfg.chunking)
        self.dirs = dense_dirs(cfg)
        for d, c in zip(self.dirs, dense_chunkings(cfg), strict=True):
            check_basis(d / "basis.json", index_basis(cfg, c))
        self.dense_ids, self.chunk_emb = load_dense(self.dirs)
        self.hybrid = r.type == "hybrid"
        self.depth = r.fusion.depth if self.hybrid else r.top_k
        if self.hybrid:
            self.bm25_ids = read_doc_ids(self.index_dir)  # BM25는 기본 청크만 쓴다
            self.bm25 = BM25Retriever(cfg, self.index_dir)
        self.use_cond = bool(self.hybrid and r.get("conditions") and r.conditions.enabled)
        # 재정렬 점수로 상위 후보를 다시 줄 세우는지. 평가와 생성이 이 값을 읽는다(S16)
        self.use_rerank = bool(self.hybrid and r.get("rerank") and r.rerank.enabled)
        self.weighted = r.get("doc_agg") is not None
        self.score_fusion = self.hybrid and r.fusion.get("method", "rrf") == "score"
        if self.use_cond or self.weighted or self.score_fusion:
            self.doc_names, self.chunk_doc = np.unique(self.dense_ids, return_inverse=True)
        if self.score_fusion:  # BM25 청크의 문서 번호(doc_names 순서)
            self.bm25_doc = np.searchsorted(self.doc_names, self.bm25_ids)
        if self.use_cond:
            self.cond_index = self._condition_index()

    def _condition_index(self) -> ConditionIndex:
        pos = {d: i for i, d in enumerate(self.doc_names)}
        docs = [None] * len(self.doc_names)
        for doc in corpus_meta(self.cfg):
            if doc["doc_id"] in pos:
                docs[pos[doc["doc_id"]]] = doc
        c = self.cfg.conditions
        law_min = c.law_min_chars if c.get("agenda_law") else None
        return ConditionIndex(docs, self.r.conditions.year_ref_offsets, law_min)

    def query_tokens(self, texts: list[str]) -> list[list[int]] | None:
        """BM25 질의 토큰. hybrid가 아니면 None."""
        return self.bm25.query_ids(texts) if self.hybrid else None

    def _dense(self, row: np.ndarray) -> tuple[list[str], bool, np.ndarray | None]:
        """dense 문서 목록, 전체 정렬 여부, 가중 집계 문서 점수(doc_agg가 없으면 None)."""
        if self.weighted:
            scores = weighted_doc_scores(row, self.chunk_doc, len(self.doc_names),
                                         list(self.r.doc_agg.weights))
            return top_docs(scores, self.doc_names, self.depth), False, scores
        docs, full = rank_with_pool(row, self.dense_ids, self.depth, self.r.chunk_pool)
        return docs, full, None

    def lists(self, row: np.ndarray, tokens: list[int] | None = None,
              conditions: dict | None = None,
              rewrite: tuple[np.ndarray, list[int]] | None = None,
              ) -> tuple[dict[str, list[str]], set[str], bool]:
        """RRF에 넣는 목록(dense, bm25, conditions, dense_rw, bm25_rw 순), 최다 일치 문서,
        dense 전체 정렬 여부.

        dense 단독이면 dense 목록 하나다. fusion.method가 score면 dense·BM25 두 목록 대신
        정규화 점수로 합친 cc 목록 하나를 둔다(EXP-015). conditions.fuse가 false면 조건 목록을
        두지 않고, 조건 목록에 든 최다 일치 문서 중 cc에 없는 것을 cc 뒤에 붙인다(EXP-016).

        Args:
            row: 질의와 dense 청크(dense_ids 순서)의 점수.
            tokens: BM25 질의 토큰(hybrid).
            conditions: 질의 조건(조건 목록을 쓸 때).
            rewrite: 재작성 질의의 (dense 점수 행, BM25 토큰). retriever.rewrite.lists의 목록을
                원 질의 목록 뒤에 더한다(EXP-013). 조건은 원 질의 것만 쓴다.
        """
        r = self.r
        docs, full, dense_scores = self._dense(row)
        named = {"dense": docs}
        matched: set[str] = set()
        if not self.hybrid:
            return named, matched, full
        bm25_chunk = self.bm25.scores(tokens)
        named["bm25"] = rank_docs(bm25_chunk, self.bm25_ids, self.depth, r.chunk_pool)
        if self.score_fusion:
            named = {"cc": self._convex(named, row, bm25_chunk, dense_scores)}
        counts = self.cond_index.match_counts(conditions) if self.use_cond else {}
        if counts and max(counts.values()) >= r.conditions.min_fields:
            if self.weighted:  # doc_names는 dense_ids의 np.unique 결과다
                doc_scores = dense_scores
            else:
                doc_scores = np.full(len(self.doc_names), -np.inf, dtype=row.dtype)
                np.maximum.at(doc_scores, self.chunk_doc, row)
            cond = condition_docs(counts, doc_scores, self.doc_names, self.depth,
                                  r.conditions.min_fields)
            if r.conditions.get("filter") == "best":  # 맞은 필드 수가 가장 많은 문서
                top = max(counts.values())
                matched = {self.doc_names[i] for i, c in counts.items() if c == top}
            if r.conditions.get("fuse", True):
                named["conditions"] = cond
            else:  # 조건 목록 대신 결합 목록 밖 최다 일치 문서를 결합 목록 뒤에 붙인다(EXP-016)
                have = set(named["cc"])
                named["cc"] = named["cc"] + [d for d in cond if d in matched and d not in have]
        if rewrite is not None:
            rw_row, rw_tokens = rewrite
            if "dense" in r.rewrite.lists:
                named["dense_rw"] = self._dense(rw_row)[0]
            if "bm25" in r.rewrite.lists:
                named["bm25_rw"] = rank_docs(self.bm25.scores(rw_tokens), self.bm25_ids,
                                             self.depth, r.chunk_pool)
        return named, matched, full

    def _convex(self, named: dict[str, list[str]], row: np.ndarray, bm25_chunk: np.ndarray,
                dense_scores: np.ndarray | None) -> list[str]:
        """dense·BM25 목록의 문서 점수(청크 최댓값)를 목록마다 min-max로 정규화해 합친다."""
        n = len(self.doc_names)
        if dense_scores is None:
            dense_scores = np.full(n, -np.inf, dtype=row.dtype)
            np.maximum.at(dense_scores, self.chunk_doc, row)
        bm25_scores = np.full(n, -np.inf, dtype=bm25_chunk.dtype)
        np.maximum.at(bm25_scores, self.bm25_doc, bm25_chunk)
        pos = np.searchsorted(self.doc_names, named["dense"] + named["bm25"])
        k = len(named["dense"])
        dense = minmax(named["dense"], dense_scores[pos[:k]].tolist())
        bm25 = minmax(named["bm25"], bm25_scores[pos[k:]].tolist())
        return convex(dense, bm25, self.r.fusion.alpha)

    def _rrf_scores(self, named: dict[str, list[str]]) -> dict[str, float]:
        weights = self.r.fusion.get("weights")  # [dense, BM25, 조건 목록]
        return rrf_scores(list(named.values()), self.r.fusion.rrf_k,
                          list(weights) if weights else None)

    def fuse(self, named: dict[str, list[str]]) -> list[str]:
        """lists의 목록을 합친 후보 순위. dense 단독이면 dense 목록, hybrid면 RRF 후보 전체다."""
        if not self.hybrid:
            return named["dense"]
        score = self._rrf_scores(named)
        return sorted(score, key=score.__getitem__, reverse=True)

    def candidates(self, row: np.ndarray, tokens: list[int] | None = None,
                   conditions: dict | None = None,
                   rewrite: tuple[np.ndarray, list[int]] | None = None,
                   ) -> tuple[list[str], set[str], bool]:
        """재정렬 전 후보 순위(fuse), 최다 일치 문서, dense 전체 정렬 여부."""
        named, matched, full = self.lists(row, tokens, conditions, rewrite)
        return self.fuse(named), matched, full

    def final(self, fused: list[str], matched: set[str],
              rerank: dict[str, float] | None = None) -> list[str]:
        """결합 후보 → 최종 상위 top_k. 평가(rag.search)와 생성(explain)이 같이 부른다(S16).

        hybrid면 final_order(재정렬 → 최다 일치 필터) 뒤 top_k로 자른다. 재정렬 깊이는 점수가
        있을 때만 retriever.rerank.depth다. dense 단독이면 후보가 이미 top_k개다.
        """
        if not self.hybrid:
            return fused
        depth = self.r.rerank.depth if rerank is not None else 0
        return final_order(fused, matched, rerank, depth)[: self.r.top_k]

    def explain(self, row: np.ndarray, tokens: list[int] | None = None,
                conditions: dict | None = None,
                rerank: dict[str, float] | None = None,
                ) -> tuple[list[str], list[dict]]:
        """상위 top_k 문서와 문서마다 단계별 기록(목록별 순위, RRF·재정렬 점수, 최다 일치 여부).

        순위는 final로 정한다. 실패·성공 원인을 나중에 나눠 보려고 단계별 값을 남긴다(PR #71).
        rerank는 문서별 재정렬 점수이고, 주면 RRF 상위 retriever.rerank.depth개를 다시 줄 세운다.
        """
        named, matched, _ = self.lists(row, tokens, conditions)
        if not self.hybrid:
            return named["dense"], [{"dense_rank": i} for i in range(1, len(named["dense"]) + 1)]
        score = self._rrf_scores(named)
        fused = sorted(score, key=score.__getitem__, reverse=True)
        docs = self.final(fused, matched, rerank)
        pos = {n: {d: i for i, d in enumerate(lst, 1)} for n, lst in named.items()}
        stages = []
        for d in docs:
            st = {"rrf_score": score[d], **{f"{n}_rank": pos[n].get(d) for n in named}}
            if rerank is not None:
                st["rerank_score"] = rerank.get(d)
            stages.append({**st, "best_match": d in matched})
        return docs, stages

    def rank(self, row: np.ndarray, tokens: list[int] | None = None,
             conditions: dict | None = None) -> list[str]:
        """상위 top_k 문서. hybrid면 최다 일치 문서를 앞으로 옮긴 뒤 자른다."""
        return self.explain(row, tokens, conditions)[0]
