"""순위 파일을 검증하고 질의별 정답 순위와 지표 표를 만든다.

규칙은 docs/SPEC.md "지표", 구체화는 docs/slices/03-eval.md.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
from hydra import compose, initialize_config_dir

ROOT = Path(__file__).resolve().parents[3]
LAYERS = ("dev-small", "dev-full", "test")


def load_cfg():
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        return compose(config_name="config")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_gold(cfg, layer: str, allow_test: bool = False) -> pd.DataFrame:
    """평가 층의 질의별 정답 doc_id, qna_type, meeting_name, conference_number (index: qid)."""
    if layer not in LAYERS:
        raise ValueError(f"알 수 없는 평가 층: {layer}")
    if layer == "test" and not allow_test:
        raise SystemExit("test 층은 --allow-test가 있어야 채점한다 (검색 단계 종료 시 1회)")

    splits = pd.read_csv(ROOT / cfg.paths.splits, dtype=str)
    splits = splits[splits["split"] == ("test" if layer == "test" else "dev")]
    keep = set(splits["qid"])
    rows = []
    with (ROOT / cfg.paths.queries).open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q["qid"] in keep:
                rows.append({"qid": q["qid"], "doc_id": q["doc_id"], "qna_type": q["qna_type"]})
    gold = pd.DataFrame(rows).merge(splits[["qid", "conference_number"]], on="qid")

    doc_ids = set(gold["doc_id"])
    meeting = {}
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["doc_id"] in doc_ids:
                meeting[d["doc_id"]] = d["meeting_name"]
    gold["meeting_name"] = gold["doc_id"].map(meeting)

    if layer == "dev-small":
        small = set((ROOT / cfg.paths.dev_small_docs).read_text(encoding="utf-8").split())
        gold = gold[gold["doc_id"].isin(small)]
    return gold.set_index("qid").sort_index()


def read_run(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"qid": str, "doc_id": str, "rank": int})


def min_docs(recall_ks, mrr_k: int) -> int:
    """질의마다 필요한 서로 다른 문서 수. 지표가 보는 가장 깊은 순위다 (SPEC "출력").

    지표 깊이에서 계산해, recall_ks·mrr_k를 바꾸면 하한도 함께 바뀌게 한다.
    """
    return max(*recall_ks, mrr_k)


def gold_ranks(run: pd.DataFrame, gold: pd.DataFrame, n_min: int) -> pd.Series:
    """질의별 정답 문서 순위(목록에 없으면 NaN). 같은 문서는 가장 높은 순위만 남기고 다시 매긴다."""
    qids = set(run["qid"])
    extra = qids - set(gold.index)
    if extra:
        raise ValueError(f"평가 층 밖의 qid {len(extra)}개: {sorted(extra)[:5]}")
    missing = set(gold.index) - qids
    if missing:
        raise ValueError(f"순위 파일에 없는 qid {len(missing)}개: {sorted(missing)[:5]}")
    if run.duplicated(["qid", "rank"]).any():
        raise ValueError("같은 qid 안에서 rank가 중복된다")

    run = run.sort_values(["qid", "rank"]).drop_duplicates(["qid", "doc_id"])
    n_docs = run.groupby("qid").size()
    short = n_docs[n_docs < n_min]
    if len(short):
        raise ValueError(
            f"서로 다른 문서가 {n_min}개 미만인 qid {len(short)}개: {list(short.index[:5])}"
        )
    run = run.assign(rank=run.groupby("qid").cumcount() + 1)

    hit = run.merge(gold["doc_id"].reset_index(), on=["qid", "doc_id"])
    return hit.set_index("qid")["rank"].reindex(gold.index).astype(float)


def per_query(ranks: pd.Series, recall_ks, mrr_k: int) -> pd.DataFrame:
    out = pd.DataFrame(index=ranks.index)
    for k in recall_ks:
        out[f"recall@{k}"] = (ranks <= k).astype(float)
    out[f"mrr@{mrr_k}"] = (1 / ranks).where(ranks <= mrr_k, 0.0)
    return out


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
