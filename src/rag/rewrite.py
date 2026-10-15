"""1차 검색의 신뢰도가 낮은 질의를 LLM으로 다시 쓴다(EXP-013, H8).

재작성 여부는 1차 검색 결과(dense·BM25 목록, dense 점수)로만 정하고 정답 라벨은 쓰지 않는다.
재작성 응답은 만든 기준(모델, 경로, 사고 과정, 지시, 판단 규칙)과 함께 paths.rewrites에
남겨 다시 쓰고, 읽을 때 지금 config와 다르면 멈춘다. 호출은 LangSmith로 추적한다(입력 메시지,
출력 원문, 토큰, 지연). 명세는 docs/experiments/EXP-013.md.
"""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from langsmith import traceable
from langsmith.run_trees import get_cached_client
from langsmith.wrappers import wrap_openai
from omegaconf import OmegaConf
from openai import OpenAI

from rag.generate import split_thought
from rag.index import ROOT


def signals(named: dict[str, list[str]], row: np.ndarray, chunk_doc: np.ndarray,
            n_docs: int, gate) -> dict:
    """판단 신호. A′는 dense·BM25 상위 overlap_k개 문서의 교집합 크기, B′는 dense 문서 점수
    (청크 최댓값)의 spread_ranks 두 순위 차다."""
    k = gate.overlap_k
    overlap = len(set(named["dense"][:k]) & set(named["bm25"][:k]))
    doc_scores = np.full(n_docs, -np.inf, dtype=row.dtype)
    np.maximum.at(doc_scores, chunk_doc, row)
    hi, lo = gate.spread_ranks
    top = np.sort(doc_scores)[::-1]
    return {"overlap": overlap, "spread": float(top[hi - 1] - top[lo - 1])}


def needs_rewrite(sig: dict, gate) -> bool:
    """신호 하나라도 "낮음"이면 재작성한다."""
    return sig["overlap"] <= gate.max_overlap or sig["spread"] <= gate.max_spread


def parse(raw: str, max_chars: int) -> str | None:
    """응답에서 사고 과정을 떼고 첫 줄을 재작성 질의로 쓴다. 비거나 max_chars를 넘으면 None."""
    _, text = split_thought(raw)
    line = next((x.strip() for x in text.splitlines() if x.strip()), "")
    return line if 0 < len(line) <= max_chars else None


def basis(cfg) -> dict:
    """재작성 파일을 만든 기준. 읽을 때 지금 config와 대조한다."""
    w = cfg.rewriter
    prompt = OmegaConf.to_container(w.prompt, resolve=True)
    return {
        "base_url": w.base_url, "model": w.model, "reasoning": w.reasoning,
        "params": OmegaConf.to_container(w.params), "prompt_version": prompt["version"],
        "prompt_sha256": hashlib.sha256(
            json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "gate": OmegaConf.to_container(cfg.retriever.rewrite.gate),
    }


class Rewriter:
    """질의 하나를 재작성 지시로 한 번 호출한다. 지시 틀이 요구하면 발췌 같은 값을 함께 넘긴다."""

    def __init__(self, cfg):
        w = self.w = cfg.rewriter
        self.client = wrap_openai(OpenAI(base_url=w.base_url, api_key=os.environ[w.api_key_env],
                                         timeout=w.timeout))
        # OpenRouter는 reasoning으로 사고 과정을 끈다. Google 경로는 끌 수 없어 보내지 않는다(D-11)
        self.extra = None if w.reasoning else {"reasoning": {"enabled": False}}
        self.meta = {"rewriter": w.name, "model": w.model, "reasoning": w.reasoning,
                     "prompt_version": w.prompt.version}

    def call(self, query: str, qid: str | None = None, **fields: str) -> dict:
        """재작성 응답 원문, 호출 시간(초), 토큰 사용량. 추적에는 qid와 재작성기 설정을 붙인다.

        fields는 지시의 user 틀에 질의와 함께 넣는 값이다(예: H8 사전 확인의 검색 발췌 passages).
        """
        return self._traced(query, langsmith_extra={"metadata": {**self.meta, "qid": qid}},
                            **fields)

    @traceable(name="rewrite")
    def _traced(self, query: str, **fields: str) -> dict:
        p = self.w.prompt
        messages = [{"role": "system", "content": p.system},
                    {"role": "user", "content": p.user.format(query=query, **fields)}]
        start = time.perf_counter()
        r = self.client.chat.completions.create(
            model=self.w.model, messages=messages, extra_body=self.extra,
            **OmegaConf.to_container(self.w.params))
        return {"raw": r.choices[0].message.content or "",
                "seconds": round(time.perf_counter() - start, 3),
                "usage": r.usage.model_dump() if r.usage else None}


def load_rewrites(cfg) -> dict[str, dict]:
    """재작성 파일의 응답(qid → 응답). 파일이 없으면 빈 dict, 기준이 다르면 멈춘다."""
    path = ROOT / cfg.paths.rewrites
    if not path.exists():
        return {}
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved["basis"] != basis(cfg):
        raise SystemExit(f"{cfg.paths.rewrites}의 기준이 지금 config와 다르다: "
                         f"{saved['basis']} != {basis(cfg)}")
    return saved["items"]


def rewrite_queries(cfg, queries: dict[str, str]) -> dict[str, str | None]:
    """질의(qid → 원문)의 재작성 질의(형식이 틀리면 None).

    파일에 없는 질의만 호출하고 파일에 더한다.
    """
    path = ROOT / cfg.paths.rewrites
    items = load_rewrites(cfg)
    todo = [q for q in queries if q not in items]
    if todo:
        rw = Rewriter(cfg)
        try:
            with ThreadPoolExecutor(cfg.rewriter.concurrency) as pool:
                futures = {pool.submit(rw.call, queries[q], q): q for q in todo}
                for f in as_completed(futures):
                    items[futures[f]] = f.result()
        finally:  # 호출이 중간에 실패해도 받은 응답은 남긴다
            get_cached_client().flush()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"basis": basis(cfg), "items": items},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"재작성 {len(queries)}건(호출 {len(todo)}건) -> {cfg.paths.rewrites}")
    max_chars = cfg.retriever.rewrite.max_chars
    return {q: parse(items[q]["raw"], max_chars) for q in queries}
