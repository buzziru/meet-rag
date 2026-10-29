"""G3 검수에서 뺀 질의를 제외하고 동결 세트를 쓴다 (PLAN G3).

queries.jsonl은 검사 기록 전체에서 다시 만들어지므로 고치지 않고, 제외 목록(multidoc_exclude)을
적용한 결과를 따로 쓴다. 출력 SHA-256을 DECISIONS에 적어 동결한다.

    uv run python -m rag.multidoc.freeze
"""

import hashlib
import json

from omegaconf import OmegaConf

from rag.index import ROOT, load_cfg, write_guarded


def excluded(exclude: dict) -> set[str]:
    return {qid for qids in exclude.values() for qid in qids}


def main() -> None:
    paths = load_cfg().paths
    drop = excluded(OmegaConf.to_container(OmegaConf.load(ROOT / paths.multidoc_exclude)))
    lines = (ROOT / paths.multidoc_queries).read_text(encoding="utf-8").splitlines(keepends=True)
    qids = [json.loads(line)["qid"] for line in lines]
    assert drop <= set(qids), f"queries.jsonl에 없는 제외 qid: {sorted(drop - set(qids))}"
    # 원래 줄을 그대로 옮겨 남은 질의의 내용이 queries.jsonl과 같게 한다
    kept = [line for line, qid in zip(lines, qids, strict=True) if qid not in drop]
    out = ROOT / paths.multidoc_frozen
    # 동결 뒤에는 덮어쓰지 않는다. 같은 내용이면 그대로 둔다(S30, 테스트 리뷰 T3-4)
    status = write_guarded(out, "".join(kept), False, "G3 동결 세트는 다시 만들지 않는다(D-15)")
    print(f"{len(lines)} - {len(drop)} = {len(kept)} -> {paths.multidoc_frozen} ({status})")
    print(hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
