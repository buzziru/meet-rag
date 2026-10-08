"""multi-doc 동결 세트로 순위 파일을 검증하고 질의별 지표와 지표 표를 만든다.

규칙은 docs/SPEC.md "보조 관찰: multi-doc 질의", 구체화는 docs/slices/09-multidoc-eval.md.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

METRICS = ("recall", "complete", "hit")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_gold(path: Path) -> pd.DataFrame:
    """질의별 type, pool_id, gold(정답 doc_id 집합) (index: qid)."""
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            rows.append({"qid": q["qid"], "type": q["type"], "pool_id": q["pool_id"],
                         "gold": frozenset(q["gold_doc_ids"])})
    return pd.DataFrame(rows).set_index("qid").sort_index()


def read_run(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"qid": str, "doc_id": str, "rank": int})


def ranked_docs(run: pd.DataFrame, gold: pd.DataFrame, n_min: int) -> pd.Series:
    """질의별 문서 목록(순위순). 같은 문서는 가장 높은 순위만 남긴다."""
    qids = set(run["qid"])
    extra = qids - set(gold.index)
    if extra:
        raise ValueError(f"동결 세트 밖의 qid {len(extra)}개: {sorted(extra)[:5]}")
    missing = set(gold.index) - qids
    if missing:
        raise ValueError(f"순위 파일에 없는 qid {len(missing)}개: {sorted(missing)[:5]}")
    if run.duplicated(["qid", "rank"]).any():
        raise ValueError("같은 qid 안에서 rank가 중복된다")

    run = run.sort_values(["qid", "rank"]).drop_duplicates(["qid", "doc_id"])
    docs = run.groupby("qid")["doc_id"].agg(list).reindex(gold.index)
    short = docs[docs.map(len) < n_min]
    if len(short):
        raise ValueError(
            f"서로 다른 문서가 {n_min}개 미만인 qid {len(short)}개: {list(short.index[:5])}"
        )
    return docs


def per_query(docs: pd.Series, gold: pd.DataFrame, ks) -> pd.DataFrame:
    size = gold["gold"].map(len)
    pairs = list(zip(gold["gold"], docs[gold.index], strict=True))
    out = {}
    for k in ks:
        found = pd.Series([len(g.intersection(d[:k])) for g, d in pairs], index=gold.index)
        out[f"recall@{k}"] = found / size
        out[f"complete@{k}"] = (found == size).astype(float)
        out[f"hit@{k}"] = (found > 0).astype(float)
    return pd.DataFrame(out, index=gold.index)


def metric_table(scores: pd.DataFrame, gold: pd.DataFrame, breakdowns) -> pd.DataFrame:
    """전체 한 줄과 breakdowns 각 열 값별 한 줄. 열: group, value, n, 지표들."""
    rows = [{"group": "all", "value": "all", "n": len(scores), **scores.mean().to_dict()}]
    for col in breakdowns:
        for value, part in scores.groupby(gold[col]):
            rows.append({"group": col, "value": value, "n": len(part), **part.mean().to_dict()})
    return pd.DataFrame(rows)


def to_markdown(table: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(table.columns) + " |", "|" + " --- |" * len(table.columns)]
    for row in table.itertuples(index=False):
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
