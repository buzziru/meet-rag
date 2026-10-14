"""평가(rag.search)와 생성(rag.generate)이 함께 쓰는 검색기(S12).

질의 하나의 dense 점수 행, BM25 토큰, 질의 조건을 받아 문서 순위를 낸다. 설정은 cfg.retriever다.
재정렬 점수 파일과 후보 쌍 내보내기(EXP-005·006)는 평가 전용이라 rag.search에 있다.
규칙은 docs/slices/05-retrieve.md(dense), EXP-001·003·004·007·008·010·011 문서.
"""

import json
from pathlib import Path

import numpy as np

from rag.bm25 import BM25Retriever
from rag.conditions import ConditionIndex
from rag.index import ROOT, index_path


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


def conditions_first(docs: list[str], matched: set[str]) -> list[str]:
    """조건에 맞는 문서(matched)를 순서를 유지한 채 앞으로 옮긴다(EXP-004 필터링)."""
    return sorted(docs, key=lambda d: d not in matched)


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


def read_doc_ids(index_dir: Path) -> np.ndarray:
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        return np.array([json.loads(line)["doc_id"] for line in f])


def dense_dirs(cfg) -> list[Path]:
    """dense 검색 인덱스 디렉터리. 기본 청킹 뒤에 retriever.extra_chunks를 붙인다(EXP-011)."""
    extra = cfg.retriever.get("extra_chunks") or []
    keys = set(cfg.chunking)
    for c in extra:  # 빠진 키를 기본 청킹 값으로 채우면 다른 인덱스를 조용히 고르게 된다
        if not hasattr(c, "keys") or set(c) != keys:
            raise ValueError(f"extra_chunks 항목은 {sorted(keys)} 키를 모두 적는다: {c}")
    return [index_path(cfg, c) for c in [cfg.chunking, *extra]]


def load_dense(dirs: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """dense 청크의 문서 id와 임베딩. 인덱스 순서대로 이어 붙인다."""
    ids = np.concatenate([read_doc_ids(d) for d in dirs])
    parts = [p for d in dirs for p in sorted((d / "emb").glob("part-*.npy"))]
    return ids, np.concatenate([np.load(p) for p in parts])


class Retriever:
    """인덱스·BM25·조건 색인을 한 번 읽고 질의마다 문서 순위를 낸다."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.r = r = cfg.retriever
        self.index_dir = index_path(cfg, cfg.chunking)
        self.dirs = dense_dirs(cfg)
        self.dense_ids, self.chunk_emb = load_dense(self.dirs)
        self.hybrid = r.type == "hybrid"
        self.depth = r.fusion.depth if self.hybrid else r.top_k
        if self.hybrid:
            self.bm25_ids = read_doc_ids(self.index_dir)  # BM25는 기본 청크만 쓴다
            self.bm25 = BM25Retriever(cfg, self.index_dir)
        self.use_cond = bool(self.hybrid and r.get("conditions") and r.conditions.enabled)
        self.weighted = r.get("doc_agg") is not None
        if self.use_cond or self.weighted:
            self.doc_names, self.chunk_doc = np.unique(self.dense_ids, return_inverse=True)
        if self.use_cond:
            self.cond_index = self._condition_index()

    def _condition_index(self) -> ConditionIndex:
        pos = {d: i for i, d in enumerate(self.doc_names)}
        docs = [None] * len(self.doc_names)
        with (ROOT / self.cfg.paths.corpus).open(encoding="utf-8") as f:
            for doc in map(json.loads, f):
                if doc["doc_id"] in pos:
                    docs[pos[doc["doc_id"]]] = doc
        c = self.cfg.conditions
        law_min = c.law_min_chars if c.get("agenda_law") else None
        return ConditionIndex(docs, self.r.conditions.year_ref_offsets, law_min)

    def query_tokens(self, texts: list[str]) -> list[list[int]] | None:
        """BM25 질의 토큰. hybrid가 아니면 None."""
        return self.bm25.query_ids(texts) if self.hybrid else None

    def lists(self, row: np.ndarray, tokens: list[int] | None = None,
              conditions: dict | None = None) -> tuple[dict[str, list[str]], set[str], bool]:
        """RRF에 넣는 목록(dense, bm25, conditions 순), 최다 일치 문서, dense 전체 정렬 여부.

        dense 단독이면 dense 목록 하나다.

        Args:
            row: 질의와 dense 청크(dense_ids 순서)의 점수.
            tokens: BM25 질의 토큰(hybrid).
            conditions: 질의 조건(조건 목록을 쓸 때).
        """
        r = self.r
        full = False
        if self.weighted:
            dense_scores = weighted_doc_scores(row, self.chunk_doc, len(self.doc_names),
                                               list(r.doc_agg.weights))
            docs = top_docs(dense_scores, self.doc_names, self.depth)
        else:
            docs, full = rank_with_pool(row, self.dense_ids, self.depth, r.chunk_pool)
        named = {"dense": docs}
        matched: set[str] = set()
        if not self.hybrid:
            return named, matched, full
        named["bm25"] = rank_docs(self.bm25.scores(tokens), self.bm25_ids, self.depth,
                                  r.chunk_pool)
        counts = self.cond_index.match_counts(conditions) if self.use_cond else {}
        if counts and max(counts.values()) >= r.conditions.min_fields:
            if self.weighted:  # doc_names는 dense_ids의 np.unique 결과다
                doc_scores = dense_scores
            else:
                doc_scores = np.full(len(self.doc_names), -np.inf, dtype=row.dtype)
                np.maximum.at(doc_scores, self.chunk_doc, row)
            named["conditions"] = condition_docs(counts, doc_scores, self.doc_names, self.depth,
                                                 r.conditions.min_fields)
            if r.conditions.get("filter") == "best":  # 맞은 필드 수가 가장 많은 문서
                top = max(counts.values())
                matched = {self.doc_names[i] for i, c in counts.items() if c == top}
        return named, matched, full

    def _rrf_scores(self, named: dict[str, list[str]]) -> dict[str, float]:
        weights = self.r.fusion.get("weights")  # [dense, BM25, 조건 목록]
        return rrf_scores(list(named.values()), self.r.fusion.rrf_k,
                          list(weights) if weights else None)

    def candidates(self, row: np.ndarray, tokens: list[int] | None = None,
                   conditions: dict | None = None) -> tuple[list[str], set[str], bool]:
        """재정렬 전 후보 순위, 최다 일치 문서, dense 전체 정렬 여부.

        dense 단독이면 상위 top_k 문서, hybrid면 RRF로 합친 후보 전체다.
        """
        named, matched, full = self.lists(row, tokens, conditions)
        if not self.hybrid:
            return named["dense"], matched, full
        score = self._rrf_scores(named)
        return sorted(score, key=score.__getitem__, reverse=True), matched, full

    def explain(self, row: np.ndarray, tokens: list[int] | None = None,
                conditions: dict | None = None) -> tuple[list[str], list[dict]]:
        """상위 top_k 문서와 문서마다 단계별 기록(목록별 순위, RRF 점수, 최다 일치 여부).

        순위는 rank와 같다. 실패·성공 원인을 나중에 나눠 보려고 단계별 값을 남긴다(PR #71 코멘트).
        """
        named, matched, _ = self.lists(row, tokens, conditions)
        if not self.hybrid:
            return named["dense"], [{"dense_rank": i} for i in range(1, len(named["dense"]) + 1)]
        score = self._rrf_scores(named)
        fused = sorted(score, key=score.__getitem__, reverse=True)
        docs = conditions_first(fused, matched)[: self.r.top_k]
        pos = {n: {d: i for i, d in enumerate(lst, 1)} for n, lst in named.items()}
        return docs, [{"rrf_score": score[d], **{f"{n}_rank": pos[n].get(d) for n in named},
                       "best_match": d in matched} for d in docs]

    def rank(self, row: np.ndarray, tokens: list[int] | None = None,
             conditions: dict | None = None) -> list[str]:
        """상위 top_k 문서. hybrid면 최다 일치 문서를 앞으로 옮긴 뒤 자른다."""
        return self.explain(row, tokens, conditions)[0]
