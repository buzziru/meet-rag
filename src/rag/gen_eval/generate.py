"""dev 질의 표본을 일괄 생성해 질의마다 한 줄씩 paths.gen_runs에 쓴다(S14).

생성은 rag.generate.Pipeline을 그대로 쓴다(검색 → 재정렬 → 프롬프트 → 생성). 스트리밍으로 받아
답변 첫 토큰 시간을 잰다. 이미 쓴 qid는 건너뛰고, 레시피가 다른 기록이 있으면 멈춘다.
명세는 docs/slices/14-gen-eval.md. 인자는 Hydra override(예: +exp=exp017 gen_eval.n=20).
"""

import json
import sys

import numpy as np
from langsmith.run_trees import get_cached_client

from rag.gen_eval.common import done_qids, eval_qids
from rag.generate import Pipeline, recipe
from rag.index import ROOT, load_cfg


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    qids = eval_qids(cfg)
    path = ROOT / cfg.paths.gen_runs
    pipe = Pipeline(cfg)
    done = done_qids(path, recipe(cfg, pipe.index_meta, True))
    todo = [q for q in qids if q not in done]
    print(f"표본 {len(qids)}개 중 남은 {len(todo)}개 -> {cfg.paths.gen_runs}")
    if not todo:
        return

    keep = set(todo)
    with (ROOT / cfg.paths.queries_dev).open(encoding="utf-8") as f:
        texts = {q["qid"]: q["query"] for q in map(json.loads, f) if q["qid"] in keep}
    cached = np.load(ROOT / cfg.paths.query_emb)
    pos = {q: i for i, q in enumerate(cached["qids"].tolist())}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for i, qid in enumerate(todo, 1):
            rec = pipe.run(texts[qid], cached["emb"][pos[qid]], qid=qid, stream=True, echo=False)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(todo)}] {qid} provider={rec['provider']} "
                  f"first={rec['first_token_s']}")
    get_cached_client().flush()


if __name__ == "__main__":
    main()
