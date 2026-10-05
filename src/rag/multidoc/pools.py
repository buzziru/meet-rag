"""multi-doc 질의의 후보 집합과 시작 묶음을 메타데이터로 만든다.

절차는 docs/SPEC.md "보조 관찰: multi-doc 질의", 구체화는 docs/slices/07-bundles.md.
LLM 호출과 검색기 점수를 쓰지 않는다.
"""

import json
import random
from pathlib import Path

import pandas as pd
from hydra import compose, initialize_config_dir

from rag.ingest import iter_labels, make_doc_id

ROOT = Path(__file__).resolve().parents[3]

# 유형별 후보 집합 키 열. 키 값이 빈 행은 그 유형에서 뺀다
KEYS = {"conf": ["conf"], "law": ["law"], "questioner": ["questioner", "committee"]}
CROSS_CONF = {"law", "questioner"}  # 회의 2개 이상에 걸쳐야 하는 유형


def collect(records, test_confs: set[str]) -> pd.DataFrame:
    """라벨 레코드에서 묶음에 쓰는 메타데이터만 뽑는다. test 회의는 뺀다."""
    rows = []
    for r in records:
        conf = r["conference_number"]
        if conf in test_confs:
            continue
        rows.append({
            "doc_id": make_doc_id(conf, r["context"]),
            "conf": conf,
            "qn": r["question_number"],
            "law": r.get("law", "").strip(),
            "questioner": r.get("questioner_ID", "").strip(),
            "committee": r.get("committee_name", "").strip(),
        })
    return pd.DataFrame(rows)


def find_pools(rows: pd.DataFrame, kind: str, max_docs: int) -> list[tuple[str, pd.DataFrame]]:
    """(키, 문서 표[doc_id, conf, qn])를 키 오름차순으로 반환한다. qn은 문서의 첫 발언 번호다."""
    cols = KEYS[kind]
    rows = rows[(rows[cols] != "").all(axis=1)]
    # 조건을 먼저 한 번에 걸러 키마다 집계하는 수를 줄인다
    size = rows.groupby(cols)[["doc_id", "conf"]].transform("nunique")
    keep = size["doc_id"].between(2, max_docs)
    if kind in CROSS_CONF:
        keep &= size["conf"] >= 2
    docs_all = rows[keep].groupby(cols + ["doc_id"], as_index=False).agg(
        conf=("conf", "first"), qn=("qn", "min"))
    pools = []
    for key, g in docs_all.groupby(cols, sort=True):
        docs = g[["doc_id", "conf", "qn"]].reset_index(drop=True)
        key = "|".join(key) if isinstance(key, tuple) else key
        pools.append((key, docs))
    return pools


def pick_seed(kind: str, docs: pd.DataFrame, k: int, rng: random.Random) -> list[str]:
    if kind == "conf":
        ordered = docs.sort_values(["qn", "doc_id"])["doc_id"].tolist()
        k = min(k, len(ordered))
        start = rng.randrange(len(ordered) - k + 1)
        return ordered[start:start + k]
    confs = sorted(docs["conf"].unique())
    picked = rng.sample(confs, min(k, len(confs)))
    return [rng.choice(sorted(docs.loc[docs["conf"] == c, "doc_id"])) for c in picked]


def build(rows: pd.DataFrame, types: list[str], max_docs: int, n_pools: int,
          seed_sizes: list[int], seed: int) -> tuple[list[dict], dict[str, int]]:
    """유형별로 후보 집합을 섞어 n_pools개 고르고 시작 묶음을 붙인다.

    (레코드, 유형별 가용 후보 집합 수)를 반환한다.
    """
    rng = random.Random(seed)
    out, available = [], {}
    for kind in types:
        pools = find_pools(rows, kind, max_docs)
        available[kind] = len(pools)
        rng.shuffle(pools)
        for order, (key, docs) in enumerate(pools[:n_pools]):
            seed_ids = pick_seed(kind, docs, rng.choice(seed_sizes), rng)
            out.append({
                "pool_id": f"{kind}-{order:04d}",
                "type": kind,
                "key": key,
                "order": order,
                "doc_ids": sorted(docs["doc_id"]),
                "seed_doc_ids": seed_ids,
            })
    return out, available


def report(pools: list[dict], available: dict[str, int]) -> None:
    df = pd.DataFrame(pools)
    df["size"] = df["doc_ids"].str.len()
    df["seed_size"] = df["seed_doc_ids"].str.len()
    for kind, g in df.groupby("type", sort=False):
        s = g["size"]
        print(f"{kind}: 가용 {available[kind]}, 선택 {len(g)}, 크기 중앙값 {s.median():.0f}, "
              f"90% {s.quantile(0.9):.0f}, 최대 {s.max()}, "
              f"시작 묶음 크기 {g['seed_size'].value_counts().sort_index().to_dict()}")
    types_of = df.explode("doc_ids").groupby("doc_ids")["type"].nunique()
    print(f"문서 {len(types_of)}개 중 두 유형 이상에 든 문서 {(types_of > 1).sum()}개")


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config")
    splits = pd.read_csv(ROOT / cfg.paths.splits, dtype=str)
    test_confs = set(splits.loc[splits["split"] == "test", "conference_number"])
    rows = collect((r for _, r in iter_labels(ROOT / cfg.paths.raw_dir)), test_confs)

    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        corpus_ids = {json.loads(line)["doc_id"] for line in f}
    missing = set(rows["doc_id"]) - corpus_ids
    if missing:
        raise ValueError(f"코퍼스에 없는 doc_id {len(missing)}개")

    m = cfg.multidoc
    pools, available = build(rows, list(m.types), m.pool_max_docs, m.n_pools_per_type,
                             list(m.seed_sizes), cfg.seed)
    out = ROOT / cfg.paths.multidoc_pools
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for p in pools:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    report(pools, available)
    print(f"→ {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
