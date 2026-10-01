"""G1 검수용으로 dev 질의(summary_q) 표본을 뽑아 CSV로 쓴다 (SPEC 미결 1).

dev 분할에서만 뽑는다. 검수 칸(verdict, issue, note)은 비워 두고 사람이 채운다.
"""

import json
import random
from pathlib import Path

import pandas as pd
from hydra import compose, initialize_config_dir

ROOT = Path(__file__).resolve().parents[2]
QUERY_FIELDS = [
    "qid", "doc_id", "qna_type", "query", "answer", "question_comment", "answer_comment",
]
REVIEW_COLUMNS = ["verdict", "issue", "note"]


def sample_qids(dev_qids: list[str], seed: int, n: int) -> list[str]:
    return sorted(random.Random(seed).sample(sorted(dev_qids), n))


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config")
    splits = pd.read_csv(ROOT / cfg.paths.splits, dtype=str)
    picked = set(sample_qids(splits.loc[splits["split"] == "dev", "qid"].tolist(),
                             cfg.seed, cfg.g1_sample_size))

    rows = []
    with (ROOT / cfg.paths.queries).open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q["qid"] in picked:
                rows.append({k: q[k] for k in QUERY_FIELDS})
    doc_ids = {r["doc_id"] for r in rows}
    meeting = {}
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["doc_id"] in doc_ids:
                meeting[d["doc_id"]] = d["meeting_name"]

    out = pd.DataFrame(rows).sort_values("qid")
    out.insert(2, "meeting_name", out["doc_id"].map(meeting))
    out[REVIEW_COLUMNS] = ""
    path = ROOT / cfg.paths.g1_sample
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")  # Excel 한글
    print(f"{len(out)} dev queries -> {cfg.paths.g1_sample}")
    print(out["meeting_name"].value_counts().to_string())
    print(out["qna_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
