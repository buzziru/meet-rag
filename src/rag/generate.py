"""질의 하나를 검색하고 근거를 넣은 프롬프트로 답변을 생성한다.

dev 질의(ask.qid)는 S5 질의 임베딩 캐시를, 자유 질의(ask.query)는 KURE를 쓴다. 단계는
LangSmith로 추적하고, 호출마다 질의·근거·답변·레시피를 paths.generate_dir에 JSON으로 남긴다.
명세는 docs/slices/06-generate.md. 생성은 전체 인덱스(index.scope=full)를 쓴다.
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime

import numpy as np
from langsmith import traceable
from langsmith.run_trees import get_cached_client
from langsmith.wrappers import wrap_openai
from omegaconf import OmegaConf
from openai import OpenAI

from rag.index import ROOT, encoder, load_cfg, load_embeddings, load_model
from rag.search import rank_with_pool

CONTEXT_META = ["date", "committee_name", "meeting_number", "session_number", "original"]
# Gemma 4는 이 엔드포인트에서 사고 과정을 끌 수 없어 답변 앞에 붙여 낸다
THOUGHT_START, THOUGHT_END = "<thought>", "</thought>"


def split_thought(text: str) -> tuple[str, str]:
    """응답을 (사고 과정, 답변)으로 나눈다. 사고 과정이 없으면 빈 문자열."""
    if not text.lstrip().startswith(THOUGHT_START):
        return "", text.strip()
    head, sep, tail = text.partition(THOUGHT_END)
    if not sep:
        return head.lstrip()[len(THOUGHT_START):].strip(), ""
    return head.lstrip()[len(THOUGHT_START):].strip(), tail.strip()


def answer_start(text: str) -> int | None:
    """스트리밍 중 답변이 시작하는 위치. 아직 사고 과정 안이면 None."""
    if not text.lstrip().startswith(THOUGHT_START[: len(text.lstrip())]):
        return 0
    end = text.find(THOUGHT_END)
    return None if end < 0 else end + len(THOUGHT_END)


def best_chunks(scores: np.ndarray, chunk_doc_ids: np.ndarray, k: int, pool: int) -> list[int]:
    """상위 k개 문서마다 점수가 가장 높은 청크 번호를 문서 순위대로 돌려준다(D-05)."""
    docs, _ = rank_with_pool(scores, chunk_doc_ids, k, pool)
    out = []
    for doc in docs:
        idx = np.flatnonzero(chunk_doc_ids == doc)
        out.append(int(idx[np.argmax(scores[idx])]))
    return out


def build_messages(prompt, contexts: list[dict], query: str) -> list[dict]:
    """근거에 번호와 회의 정보를 붙여 메시지를 만든다. URL은 넣지 않는다."""
    blocks = [prompt.context.format(n=c["n"], text=c["text"],
                                    **{k: c[k] for k in CONTEXT_META if k != "original"})
              for c in contexts]
    user = prompt.user.format(contexts="\n\n".join(blocks), query=query)
    return [{"role": "system", "content": prompt.system}, {"role": "user", "content": user}]


def git_state() -> tuple[str, bool]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8").stdout.strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain", "--untracked-files=no"))


def recipe(cfg, index_meta: dict, stream: bool) -> dict:
    """같은 결과를 다시 만드는 데 필요한 설정 전부."""
    prompt = OmegaConf.to_container(cfg.prompt, resolve=True)
    commit, dirty = git_state()
    g = cfg.generator
    return {
        "git_commit": commit, "git_dirty": dirty,
        "embedding_model": cfg.embedding.model_name,
        "index": f"{index_meta['name']}/{cfg.index.scope}", "n_chunks": index_meta["n_chunks"],
        "chunk_pool": cfg.retriever.chunk_pool, "context_docs": g.context_docs,
        "prompt_version": prompt["version"],
        "prompt_sha256": hashlib.sha256(
            json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "model": g.model, "params": OmegaConf.to_container(g.params), "stream": stream,
    }


class Pipeline:
    """인덱스·코퍼스 메타·클라이언트를 한 번 불러 두고 질의마다 run을 부른다."""

    def __init__(self, cfg):
        self.cfg = cfg
        index_dir = ROOT / cfg.paths.index_dir
        with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f]
        self.chunk_doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.chunk_emb = load_embeddings(index_dir)
        meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))
        self.index_meta = {"name": index_dir.parent.name, "n_chunks": meta["n_chunks"]}
        self.client = wrap_openai(OpenAI(base_url=cfg.generator.base_url,
                                         api_key=os.environ[cfg.generator.api_key_env]))
        self._model = None

    def dev_query(self, qid: str) -> tuple[str, np.ndarray]:
        """dev 질의 원문과 S5 캐시 임베딩. dev만 담은 paths.queries_dev만 읽는다."""
        with (ROOT / self.cfg.paths.queries_dev).open(encoding="utf-8") as f:
            text = next((q["query"] for q in map(json.loads, f) if q["qid"] == qid), None)
        if text is None:
            raise SystemExit(f"dev 질의에 없는 qid: {qid}")
        cached = np.load(ROOT / self.cfg.paths.query_emb)
        return text, cached["emb"][cached["qids"].tolist().index(qid)]

    def embed(self, query: str) -> np.ndarray:
        if self._model is None:
            self._model = load_model(self.cfg, self.cfg.embedding.query_max_tokens)
        return encoder(self._model, self.cfg)([query])[0]

    @traceable(name="retrieve", process_inputs=lambda i: {"k": i["k"]})
    def retrieve(self, q_emb: np.ndarray, k: int) -> list[dict]:
        scores = self.chunk_emb @ q_emb
        picked = best_chunks(scores, self.chunk_doc_ids, k, self.cfg.retriever.chunk_pool)
        meta = self._doc_meta({self.chunk_doc_ids[i] for i in picked})
        return [{"n": n, "doc_id": self.chunks[i]["doc_id"], "chunk_id": self.chunks[i]["chunk_id"],
                 "score": float(scores[i]), "text": self.chunks[i]["text"],
                 **meta[self.chunks[i]["doc_id"]]}
                for n, i in enumerate(picked, 1)]

    def _doc_meta(self, doc_ids: set[str]) -> dict[str, dict]:
        out = {}
        with (ROOT / self.cfg.paths.corpus).open(encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d["doc_id"] in doc_ids:
                    out[d["doc_id"]] = {k: d[k] for k in CONTEXT_META}
        return out

    @traceable(name="build_messages", process_inputs=lambda i: {"query": i["query"]})
    def messages(self, contexts: list[dict], query: str) -> list[dict]:
        return build_messages(self.cfg.prompt, contexts, query)

    @traceable(name="generate", process_inputs=lambda i: {"stream": i["stream"]})
    def generate(self, messages: list[dict], stream: bool) -> dict:
        g = self.cfg.generator
        params = OmegaConf.to_container(g.params)
        if not stream:
            r = self.client.chat.completions.create(model=g.model, messages=messages, **params)
            text, usage = r.choices[0].message.content, r.usage.model_dump()
        else:
            text, usage, printed = "", None, 0
            for chunk in self.client.chat.completions.create(
                    model=g.model, messages=messages, stream=True,
                    stream_options={"include_usage": True}, **params):
                if chunk.choices and chunk.choices[0].delta.content:
                    text += chunk.choices[0].delta.content
                    start = answer_start(text)
                    if start is not None:  # 사고 과정은 출력하지 않고 답변만 흘려보낸다
                        piece = text[max(printed, start):]
                        print(piece.lstrip() if printed <= start else piece, end="", flush=True)
                        printed = len(text)
                if chunk.usage:
                    usage = chunk.usage.model_dump()
            print()
        thought, answer = split_thought(text)
        return {"answer": answer, "thought": thought, "usage": usage}

    def run(self, query: str, q_emb: np.ndarray, qid: str | None = None,
            stream: bool | None = None) -> dict:
        """검색 → 프롬프트 → 생성. 레시피를 LangSmith 메타데이터와 기록에 함께 남긴다."""
        stream = self.cfg.generator.stream if stream is None else stream
        rec = recipe(self.cfg, self.index_meta, stream)
        run_id = uuid.uuid4()
        out = self._traced(query, q_emb, stream,
                           langsmith_extra={"run_id": run_id, "metadata": {**rec, "qid": qid}})
        return {"time": datetime.now().isoformat(timespec="seconds"), "qid": qid, "query": query,
                **out, "langsmith_run_id": str(run_id), "recipe": rec}

    @traceable(name="rag", process_inputs=lambda i: {"query": i["query"]})
    def _traced(self, query: str, q_emb: np.ndarray, stream: bool) -> dict:
        contexts = self.retrieve(q_emb, self.cfg.generator.context_docs)
        result = self.generate(self.messages(contexts, query), stream)
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
