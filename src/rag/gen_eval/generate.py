"""dev 질의 표본을 일괄 생성해 질의마다 한 줄씩 paths.gen_runs에 쓴다(S14).

생성은 rag.generate.Pipeline의 검색·프롬프트·생성 메서드를 그대로 쓴다. 검색과 프롬프트는 차례로
만들고, 생성 API 호출만 gen_eval.concurrency개씩 동시에 보낸다(S24 결정 사항 1 (b)). 검색 단계의
형태소 분석기·조건 추출기가 스레드 안전한지 확인하지 않았고, 생성 지연에 로컬 검색 CPU가 섞이지
않게 하려는 것이다. 스트리밍으로 받아 답변 첫 토큰 시간을 재고, 검색·프롬프트 조립 시간
(retrieve_s)과 동시 수를 함께 남긴다. 기록은 표본 순서대로 쓰고, 생성이 실패한 질의만 빼고
쓴 뒤 멈추므로 다시 실행하면 이어 쓴다. 이미 쓴 qid는 건너뛰고, 레시피가 다른 기록이 있으면
멈춘다. 반복 번호(gen_eval.gen_rep)는 레시피가 아니라 경로와 기록 필드에 남긴다. 명세는
docs/slices/14-gen-eval.md, docs/slices/24-variance.md. 인자는 Hydra override(기본은 판정용
세트 dev-full 330질의, D-50. 예: +exp=exp017 gen_eval.gen_rep=1, S14 표본은
gen_eval.queries=dev-small gen_eval.n=20).
"""

import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langsmith.run_trees import get_cached_client

from rag.gen_eval.common import done_qids, eval_qids
from rag.generate import Pipeline, recipe
from rag.index import ROOT, load_cfg
from rag.retrieve import read_query_emb


def generate_all(pipe, items: list[tuple[str, str, object]], rec: dict, concurrency: int,
                 gen_rep: int, write) -> None:
    """items의 (qid, 질의, 질의 임베딩)을 검색은 차례로, 생성은 동시에 처리해 표본 순서대로
    write(record)한다. 기록 형식은 Pipeline.run과 같고 retrieve_s(검색·프롬프트 조립 시간)·
    concurrency·gen_rep를 더한다. 생성이 실패한 질의는 건너뛰고 나머지는 모두 쓴 뒤, 실패가
    있으면 그 qid를 알리고 멈춘다. 다시 실행하면 쓰지 않은 질의만 생성한다."""
    k = pipe.cfg.generator.context_docs

    def gen(qid, query, contexts, messages, retrieve_s):
        run_id = uuid.uuid4()
        out = pipe.generate(messages, True, False,
                            langsmith_extra={"run_id": run_id, "metadata": {**rec, "qid": qid}})
        return {"time": datetime.now().isoformat(timespec="seconds"), "qid": qid, "query": query,
                "contexts": contexts, **out, "retrieve_s": retrieve_s,
                "concurrency": concurrency, "gen_rep": gen_rep,
                "langsmith_run_id": str(run_id), "recipe": rec}

    with ThreadPoolExecutor(concurrency) as ex:
        futures = []
        for qid, query, emb in items:
            t0 = time.perf_counter()
            contexts = pipe.retrieve(query, emb, k, qid)
            messages = pipe.messages(contexts, query)
            futures.append(ex.submit(gen, qid, query, contexts, messages,
                                     time.perf_counter() - t0))
        failed = []
        for (qid, _, _), f in zip(items, futures, strict=True):
            try:
                write(f.result())
            except Exception as e:  # 429 등 한 질의의 실패로 끝난 다른 생성을 버리지 않는다
                failed.append(f"{qid}: {type(e).__name__}: {e}")
    if failed:
        raise SystemExit(f"생성 실패 {len(failed)}건(다시 실행하면 이어 쓴다):\n"
                         + "\n".join(failed))


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    g = cfg.gen_eval
    if g.concurrency < 1:
        raise SystemExit(f"gen_eval.concurrency는 1 이상이다: {g.concurrency}")
    qids = eval_qids(cfg)
    path = ROOT / cfg.paths.gen_runs
    pipe = Pipeline(cfg)
    rec = recipe(cfg, pipe.index_meta, True)
    done = done_qids(path, rec)
    todo = [q for q in qids if q not in done]
    print(f"표본 {len(qids)}개 중 남은 {len(todo)}개, 동시 {g.concurrency} -> {cfg.paths.gen_runs}")
    if not todo:
        return

    keep = set(todo)
    with (ROOT / cfg.paths.queries_dev).open(encoding="utf-8") as f:
        texts = {q["qid"]: q["query"] for q in map(json.loads, f) if q["qid"] in keep}
    cached_qids, emb = read_query_emb(cfg, ROOT / cfg.paths.query_emb)
    pos = {q: i for i, q in enumerate(cached_qids)}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        n = 0

        def write(r):
            nonlocal n
            n += 1
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(todo)}] {r['qid']} provider={r['provider']} "
                  f"first={r['first_token_s']}")

        generate_all(pipe, [(q, texts[q], emb[pos[q]]) for q in todo], rec, g.concurrency,
                     g.gen_rep, write)
    get_cached_client().flush()


if __name__ == "__main__":
    main()
