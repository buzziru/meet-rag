"""S1 산출물에서 평가 분할(queries.csv)과 dev-small 문서 목록을 만든다.

절차는 docs/SPEC.md "분할"·"평가 층", 구체화는 docs/slices/02-splits.md.
"""

import json
import random
from collections import deque
from pathlib import Path

import pandas as pd

from rag.index import ROOT, load_cfg, write_guarded

# 분할은 보호 경로(data/splits/)라 덮어쓰기 옵션을 두지 않는다(S15)
HINT = "보호 경로다. 사용자 승인을 받고 파일을 지운 뒤 다시 실행한다"


def assign_splits(
    meetings: dict[str, tuple[str, int]], seed: int, targets: list[tuple[str, int]]
) -> dict[str, str]:
    """회의(회의구분, 질의 수)를 질의 수 기준 회의구분 비율을 유지하며 분할에 차례로 배정한다."""
    order = sorted(meetings)
    random.Random(seed).shuffle(order)
    queues: dict[str, deque] = {}
    for conf in order:
        queues.setdefault(meetings[conf][0], deque()).append(conf)
    total = sum(n for _, n in meetings.values())
    share = {k: sum(n for m, n in meetings.values() if m == k) / total for k in queues}

    assigned = {}
    for split, min_queries in targets:
        filled = dict.fromkeys(queues, 0)
        while sum(filled.values()) < min_queries:
            k = min((k for k in queues if queues[k]), key=lambda k: (filled[k] / share[k], k))
            conf = queues[k].popleft()
            assigned[conf] = split
            filled[k] += meetings[conf][1]
    return assigned


def pick_dev_small(docs_by_meeting: dict[str, set[str]], seed: int, min_docs: int) -> list[str]:
    """dev 회의를 섞어 문서 수가 min_docs 이상이 될 때까지 회의 단위로 문서를 모은다."""
    order = sorted(docs_by_meeting)
    random.Random(seed).shuffle(order)
    picked: set[str] = set()
    for conf in order:
        if len(picked) >= min_docs:
            break
        picked |= docs_by_meeting[conf]
    return sorted(picked)


def read_jsonl(path: Path, fields: list[str]) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        return pd.DataFrame([{k: json.loads(line)[k] for k in fields} for line in f])


def main() -> None:
    cfg = load_cfg()
    docs = read_jsonl(ROOT / cfg.paths.corpus, ["doc_id", "conference_number", "meeting_name"])
    q = read_jsonl(ROOT / cfg.paths.queries, ["qid", "doc_id", "qna_type"]).merge(docs, on="doc_id")

    meetings = {
        conf: (g["meeting_name"].iat[0], len(g)) for conf, g in q.groupby("conference_number")
    }
    targets = [("dev", cfg.splits.dev_min_queries), ("test", cfg.splits.test_min_queries)]
    q["split"] = q["conference_number"].map(assign_splits(meetings, cfg.seed, targets))

    out = q.dropna(subset=["split"]).sort_values("qid")
    table = out[["qid", "conference_number", "split"]].to_csv(index=False, lineterminator="\n")
    print(f"{cfg.paths.splits}: {write_guarded(ROOT / cfg.paths.splits, table, False, HINT)}")

    dev = out[out["split"] == "dev"]
    docs_by_meeting = dev.groupby("conference_number")["doc_id"].agg(set).to_dict()
    dev_small = pick_dev_small(docs_by_meeting, cfg.seed, cfg.splits.dev_small_min_docs)
    state = write_guarded(ROOT / cfg.paths.dev_small_docs, "".join(f"{d}\n" for d in dev_small),
                          False, HINT)
    print(f"{cfg.paths.dev_small_docs}: {state}")

    q["split"] = q["split"].fillna("unused")
    by_split = q.groupby("split")
    print(by_split.agg(queries=("qid", "size"), meetings=("conference_number", "nunique")))
    print(f"dev_small docs {len(dev_small):,}")
    for col in ["meeting_name", "qna_type"]:
        table = pd.crosstab(q[col], q["split"], normalize="columns").mul(100).round(2)
        table["all"] = q[col].value_counts(normalize=True).mul(100).round(2)
        print(table[["all", "dev", "test"]])


if __name__ == "__main__":
    main()
