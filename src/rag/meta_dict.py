"""코퍼스 문서 필드에서 질의 조건 추출(S11)용 값 사전을 만든다.

값마다 그 값을 가진 문서 수를 센다. 코퍼스 밖 파일(평가 질의, 분할, 동결 세트)은 읽지 않는다
(docs/slices/10-speaker-fields.md, protocol-guard P9).
"""

import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from rag.index import ROOT, load_cfg
from rag.ingest import SPEAKER_KEYS, SPEAKERS

DOC_FIELDS = ["committee_name", "meeting_name"]


def doc_values(doc: dict) -> dict[str, set[str]]:
    """문서 하나의 항목별 값 집합. 빈 값은 뺀다."""
    values = {f: {doc.get(f, "")} for f in DOC_FIELDS}
    for key in SPEAKER_KEYS:
        values[key] = {p[key] for field in SPEAKERS for p in doc[field]}
    return {k: v - {""} for k, v in values.items()}


def build(docs: Iterable[dict]) -> dict[str, dict[str, int]]:
    counts = {k: Counter() for k in DOC_FIELDS + SPEAKER_KEYS}
    for doc in docs:
        for k, values in doc_values(doc).items():
            counts[k].update(values)
    return {k: dict(sorted(c.items())) for k, c in counts.items()}


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        result = build(map(json.loads, f))
    out = ROOT / cfg.paths.meta_dict
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    sizes = ", ".join(f"{k} {len(v):,}" for k, v in result.items())
    print(f"{sizes} -> {Path(cfg.paths.meta_dict)}")


if __name__ == "__main__":
    main()
