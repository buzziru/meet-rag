"""multi-doc 생성 에이전트가 읽을 후보 집합별 입력과 문서 원문을 쓴다.

명세는 docs/slices/08-multidoc-queries.md. 코퍼스의 context와 메타데이터, 라벨의 질의자
이름·직위만 쓰고, 질의 파일과 검색 결과는 읽지 않는다.
출력이 이미 있는 후보 집합은 건너뛴다(재사용).
"""

import json
import sys
from pathlib import Path

import pandas as pd
from hydra import compose, initialize_config_dir

from rag.ingest import iter_labels, make_doc_id

ROOT = Path(__file__).resolve().parents[3]

META = ["date", "committee_name", "meeting_name", "meeting_number", "session_number", "agenda"]


def select(pools: list[dict], n_per_type: int) -> list[dict]:
    """유형마다 order 앞에서부터 n_per_type개."""
    return [p for p in pools if p["order"] < n_per_type]


def collect_speakers(records, doc_ids: set[str]) -> dict[str, list[dict]]:
    """문서마다 질의자 이름·직위 목록(이름 순). 라벨에서 질의자 필드만 읽는다."""
    out: dict[str, set] = {}
    for r in records:
        d = make_doc_id(r["conference_number"], r["context"])
        if d in doc_ids:
            name = r.get("questioner_name", "").strip()
            if name:
                out.setdefault(d, set()).add((name, r.get("questioner_position", "").strip()))
    return {d: [{"name": n, "position": p} for n, p in sorted(v)] for d, v in out.items()}


def speaker_text(speakers: list[dict]) -> str:
    return ", ".join(f"{s['name']} {s['position']}".strip() for s in speakers) or "미상"


def gen_input(pool: dict, docs: dict[str, dict], overview_chars: int) -> dict:
    """후보 집합 하나의 생성 입력. 문서마다 메타데이터, 질의자, context 앞부분만 넣는다."""
    return {
        "pool_id": pool["pool_id"],
        "type": pool["type"],
        "key": pool["key"],
        "seed_doc_ids": pool["seed_doc_ids"],
        "docs": [{"doc_id": d, **{k: docs[d][k] for k in META}, "speakers": docs[d]["speakers"],
                  "overview": docs[d]["context"][:overview_chars]} for d in pool["doc_ids"]],
    }


def write_new(path: Path, text: str) -> bool:
    """파일이 없을 때만 쓴다. 썼으면 True."""
    if path.exists():
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def load_docs(cfg, pools: list[dict]) -> dict[str, dict]:
    """후보 집합 문서의 코퍼스 행에 질의자(speakers)를 붙인다."""
    need = {d for p in pools for d in p["doc_ids"]}
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        docs = {r["doc_id"]: r for r in map(json.loads, f) if r["doc_id"] in need}
    speakers = collect_speakers((r for _, r in iter_labels(ROOT / cfg.paths.raw_dir)), need)
    for d, r in docs.items():
        r["speakers"] = speakers.get(d, [])
    return docs


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config", overrides=sys.argv[1:])
    with (ROOT / cfg.paths.multidoc_pools).open(encoding="utf-8") as f:
        pools = select([json.loads(line) for line in f], cfg.multidoc.gen.n_per_type)
    docs = load_docs(cfg, pools)
    need = set(docs)

    splits = pd.read_csv(ROOT / cfg.paths.splits, dtype=str)
    test_confs = set(splits.loc[splits["split"] == "test", "conference_number"])
    leaked = [d for d in need if docs[d]["conference_number"] in test_confs]
    if leaked:
        raise ValueError(f"test 회의 문서 {len(leaked)}개")

    gen_in, doc_dir = ROOT / cfg.paths.multidoc_gen_in, ROOT / cfg.paths.multidoc_docs
    gen_in.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)
    n_in = sum(write_new(gen_in / f"{p['pool_id']}.json", json.dumps(
        gen_input(p, docs, cfg.multidoc.gen.overview_chars), ensure_ascii=False, indent=1))
        for p in pools)
    n_doc = sum(write_new(doc_dir / f"{d}.txt", docs[d]["context"]) for d in sorted(need))
    print(f"후보 집합 {len(pools)}개(새로 씀 {n_in}), 문서 {len(need)}개(새로 씀 {n_doc})")
    print(f"→ {gen_in.relative_to(ROOT)}, {doc_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
