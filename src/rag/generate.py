"""질의 하나를 검색하고 근거를 넣은 프롬프트로 답변을 생성한다.

dev 질의(ask.qid)는 S5 질의 임베딩 캐시를, 자유 질의(ask.query)는 KURE를 쓴다. 단계는
LangSmith로 추적하고, 호출마다 질의·근거·답변·레시피를 paths.generate_dir에 JSON으로 남긴다.
명세는 docs/slices/06-generate.md. 생성은 전체 인덱스(index.scope=full)를 쓴다.
"""

import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime

import numpy as np
from langsmith import traceable
from langsmith.run_trees import get_cached_client
from langsmith.wrappers import wrap_openai
from omegaconf import OmegaConf
from openai import OpenAI

from rag.conditions import build_extractor
from rag.index import ROOT, corpus_meta, encoder, file_sha256, git_state, load_cfg, load_model
from rag.llm import answer_start, split_thought
from rag.retrieve import (
    ChunkStore,
    Retriever,
    best_chunks,
    chunks_by_doc,
    read_query_emb,
    read_rerank_scores,
)

CONTEXT_META = ["date", "committee_name", "meeting_number", "session_number", "original"]


def build_messages(prompt, contexts: list[dict], query: str) -> list[dict]:
    """근거에 번호와 회의 정보를 붙여 메시지를 만든다. URL은 넣지 않는다."""
    blocks = [prompt.context.format(n=c["n"], text=c["text"],
                                    **{k: c[k] for k in CONTEXT_META if k != "original"})
              for c in contexts]
    user = prompt.user.format(contexts="\n\n".join(blocks), query=query)
    return [{"role": "system", "content": prompt.system}, {"role": "user", "content": user}]


def recipe(cfg, index_meta: dict, stream: bool) -> dict:
    """같은 결과를 다시 만드는 데 필요한 설정 전부. 조건 추출 설정(conditions, name_titles)과
    재정렬 점수 파일 해시도 검색 결과를 바꾸므로 넣는다(S15)."""
    prompt = OmegaConf.to_container(cfg.prompt, resolve=True)
    commit, dirty = git_state()
    g = cfg.generator
    return {
        "git_commit": commit, "git_dirty": dirty,
        "embedding_model": cfg.embedding.model_name,
        # 질의 임베딩 캐시 지문과 같은 값(S21). 경로(embedding.slug)만으로는 구분되지 않는다
        "embedding_revision": cfg.embedding.get("revision"),
        "query_prompt": cfg.embedding.get("query_prompt"),
        "index": [f"{n}/{cfg.index.scope}" for n in index_meta["names"]],
        "n_chunks": index_meta["n_chunks"],
        "retriever": OmegaConf.to_container(cfg.retriever, resolve=True),
        "conditions": OmegaConf.to_container(cfg.conditions, resolve=True),
        "name_titles": list(cfg.ingest.name_titles),
        "rerank_scores_sha256": index_meta.get("rerank_scores_sha256"),
        "context_docs": g.context_docs,
        "prompt_version": prompt["version"],
        "prompt_sha256": hashlib.sha256(
            json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "model": g.model, "params": OmegaConf.to_container(g.params), "stream": stream,
        "extra_body": OmegaConf.to_container(g.extra_body) if g.get("extra_body") else None,
    }


class Pipeline:
    """인덱스·코퍼스 메타·클라이언트를 한 번 불러 두고 질의마다 run을 부른다."""

    def __init__(self, cfg):
        self.cfg = cfg
        r = cfg.retriever
        if r.get("rewrite") and r.rewrite.enabled:  # 생성 경로에는 재작성이 없다(EXP-013 기각, S16)
            raise SystemExit("생성은 retriever.rewrite를 지원하지 않는다. "
                             "retriever.rewrite.enabled=false로 실행한다")
        self.retriever = Retriever(cfg)
        self.doc_chunks = chunks_by_doc(self.retriever.dense_ids)
        self.store = ChunkStore(self.retriever.dirs)
        self.extractor = build_extractor(cfg) if self.retriever.use_cond else None
        self.index_meta = {"names": self.store.names, "n_chunks": int(self.store.bounds[-1])}
        # 근거에 붙일 회의 정보. 시작할 때 한 번 읽는다(질의마다 코퍼스를 읽지 않는다, PR #71).
        # 조건 색인·추출기가 읽은 코퍼스를 같이 쓴다(S17)
        self.doc_meta = {d["doc_id"]: {k: d[k] for k in CONTEXT_META} for d in corpus_meta(cfg)}
        self.client = wrap_openai(OpenAI(base_url=cfg.generator.base_url,
                                         api_key=os.environ[cfg.generator.api_key_env]))
        self._model = None
        # 재정렬 점수는 EXP-017이 Colab에서 만든 파일을 읽는다. 실시간 재정렬은 배포 SLICE(S14)
        use_rerank = self.retriever.use_rerank
        self.rerank_scores = read_rerank_scores(cfg) if use_rerank else None
        self.index_meta["rerank_scores_sha256"] = (
            file_sha256(ROOT / cfg.paths.rerank_scores) if use_rerank else None)

    def dev_query(self, qid: str) -> tuple[str, np.ndarray]:
        """dev 질의 원문과 S5 캐시 임베딩. dev만 담은 paths.queries_dev만 읽는다."""
        with (ROOT / self.cfg.paths.queries_dev).open(encoding="utf-8") as f:
            text = next((q["query"] for q in map(json.loads, f) if q["qid"] == qid), None)
        if text is None:
            raise SystemExit(f"dev 질의에 없는 qid: {qid}")
        qids, emb = read_query_emb(self.cfg, ROOT / self.cfg.paths.query_emb)
        return text, emb[qids.index(qid)]

    def embed(self, query: str) -> np.ndarray:
        if self._model is None:
            self._model = load_model(self.cfg, self.cfg.embedding.query_max_tokens)
        return encoder(self._model, self.cfg, self.cfg.embedding.get("query_prompt"))([query])[0]

    def rank(self, query: str, q_emb: np.ndarray, qid: str | None = None,
             ) -> tuple[np.ndarray, list[str], list[dict]]:
        """dense 청크 점수, 문서 순위, 문서별 단계 기록. rag.search와 같은 Retriever를 쓴다(S12)."""
        rerank = None
        if self.rerank_scores is not None:
            if qid not in self.rerank_scores:
                raise SystemExit("재정렬 점수 파일에 없는 질의다. 자유 질의의 실시간 재정렬은 "
                                 "배포 SLICE에서 만든다(S14 결정 1)")
            rerank = self.rerank_scores[qid]
        scores = self.retriever.chunk_emb @ q_emb
        tokens = self.retriever.query_tokens([query])
        conds = self.extractor.extract(query) if self.extractor else None
        docs, stages = self.retriever.explain(scores, tokens[0] if tokens else None, conds,
                                              rerank=rerank)
        return scores, docs, stages

    @traceable(name="retrieve", process_inputs=lambda i: {"k": i["k"]})
    def retrieve(self, query: str, q_emb: np.ndarray, k: int, qid: str | None = None,
                 ) -> list[dict]:
        """상위 k개 문서의 근거. score는 문서 순위를 정한 최종 점수(hybrid면 RRF, dense면 청크
        점수)이고, 근거 청크의 dense 점수와 단계별 순위를 함께 남긴다(PR #71 코멘트)."""
        scores, docs, stages = self.rank(query, q_emb, qid)
        picked = best_chunks(scores, self.doc_chunks, docs[:k])
        rows = [self.store.get(i) for i in picked]
        out = []
        for n, (i, r, st) in enumerate(zip(picked, rows, stages[:k], strict=True), 1):
            dense = float(scores[i])
            out.append({"n": n, "doc_id": r["doc_id"], "index": r["index"],
                        "chunk_id": r["chunk_id"], "score": st.get("rrf_score", dense),
                        "dense_score": dense, "stages": st, "text": r["text"],
                        **self.doc_meta[r["doc_id"]]})
        return out

    @traceable(name="build_messages", process_inputs=lambda i: {"query": i["query"]})
    def messages(self, contexts: list[dict], query: str) -> list[dict]:
        return build_messages(self.cfg.prompt, contexts, query)

    @traceable(name="generate", process_inputs=lambda i: {"stream": i["stream"]})
    def generate(self, messages: list[dict], stream: bool, echo: bool = True) -> dict:
        """답변 생성. 스트리밍이면 답변 첫 토큰까지의 시간(first_token_s)을 잰다(D-30·D-37).
        provider는 응답이 알려 준 실제 제공자다(OpenRouter, 제공자 고정 확인용)."""
        g = self.cfg.generator
        params = OmegaConf.to_container(g.params)
        extra = OmegaConf.to_container(g.extra_body) if g.get("extra_body") else None
        t0, first = time.perf_counter(), None
        if not stream:
            r = self.client.chat.completions.create(model=g.model, messages=messages,
                                                    extra_body=extra, **params)
            text, usage = r.choices[0].message.content, r.usage.model_dump()
            provider = getattr(r, "provider", None)
        else:
            text, usage, provider, printed = "", None, None, 0
            for chunk in self.client.chat.completions.create(
                    model=g.model, messages=messages, stream=True, extra_body=extra,
                    stream_options={"include_usage": True}, **params):
                provider = provider or getattr(chunk, "provider", None)
                if chunk.choices and chunk.choices[0].delta.content:
                    text += chunk.choices[0].delta.content
                    start = answer_start(text)
                    if start is not None:  # 사고 과정은 출력하지 않고 답변만 흘려보낸다
                        if first is None and text[start:].strip():
                            first = time.perf_counter() - t0
                        if echo:
                            piece = text[max(printed, start):]
                            print(piece.lstrip() if printed <= start else piece, end="",
                                  flush=True)
                        printed = len(text)
                if chunk.usage:
                    usage = chunk.usage.model_dump()
            if echo:
                print()
        thought, answer = split_thought(text)
        return {"answer": answer, "thought": thought, "usage": usage, "provider": provider,
                "first_token_s": first, "total_s": time.perf_counter() - t0}

    def run(self, query: str, q_emb: np.ndarray, qid: str | None = None,
            stream: bool | None = None, echo: bool = True) -> dict:
        """검색 → 프롬프트 → 생성. 레시피를 LangSmith 메타데이터와 기록에 함께 남긴다."""
        stream = self.cfg.generator.stream if stream is None else stream
        rec = recipe(self.cfg, self.index_meta, stream)
        run_id = uuid.uuid4()
        out = self._traced(query, q_emb, qid, stream, echo,
                           langsmith_extra={"run_id": run_id, "metadata": {**rec, "qid": qid}})
        return {"time": datetime.now().isoformat(timespec="seconds"), "qid": qid, "query": query,
                **out, "langsmith_run_id": str(run_id), "recipe": rec}

    @traceable(name="rag", process_inputs=lambda i: {"query": i["query"]})
    def _traced(self, query: str, q_emb: np.ndarray, qid: str | None, stream: bool,
                echo: bool) -> dict:
        contexts = self.retrieve(query, q_emb, self.cfg.generator.context_docs, qid)
        result = self.generate(self.messages(contexts, query), stream, echo)
        return {"contexts": contexts, **result}


def save(cfg, record: dict) -> str:
    out_dir = ROOT / cfg.paths.generate_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}-{record['qid'] or 'free'}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.relative_to(ROOT))


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if (cfg.ask.qid is None) == (cfg.ask.query is None):
        raise SystemExit("ask.qid와 ask.query 중 하나만 준다")
    pipe = Pipeline(cfg)
    if cfg.ask.qid is not None:
        query, q_emb = pipe.dev_query(str(cfg.ask.qid))
    else:
        query, q_emb = cfg.ask.query, pipe.embed(cfg.ask.query)
    record = pipe.run(query, q_emb, qid=cfg.ask.qid)
    get_cached_client().flush()

    if not record["recipe"]["stream"]:
        print(record["answer"])
    print("\n[근거]")
    for c in record["contexts"]:
        print(f"[{c['n']}] {c['date']} {c['committee_name']} ({c['doc_id']}, {c['score']:.4f})")
        print(f"    {c['original']}")
    print(f"\nusage {record['usage']}\nsaved {save(cfg, record)}")


if __name__ == "__main__":
    main()
