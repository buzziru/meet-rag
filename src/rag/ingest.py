"""라벨 zip에서 코퍼스(corpus_context.jsonl)와 평가 질의(queries_summary_q.jsonl)를 만든다.

형식과 doc_id 규칙은 docs/data.md §16, 절차는 docs/slices/01-data.md.
"""

import hashlib
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

from hydra import compose, initialize_config_dir

ROOT = Path(__file__).resolve().parents[2]
SPLITS = {"Training": "TL_", "Validation": "VL_"}
META_FIELDS = [
    "conference_number", "date", "meeting_name", "generation_number", "committee_name",
    "meeting_number", "session_number", "agenda", "original",
]


def iter_labels(raw_dir: Path) -> Iterator[tuple[str, dict]]:
    """(AI Hub 분할, 라벨 레코드)를 zip을 풀지 않고 읽는다."""
    for split, prefix in SPLITS.items():
        for zip_path in sorted((raw_dir / split / "02.라벨링데이터").glob(f"{prefix}*.zip")):
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    base = name.rsplit("/", 1)[-1]
                    if base.startswith("LAB_") and base.endswith(".json"):
                        yield split, json.loads(zf.read(name))


def make_doc_id(conference_number: str, context: str) -> str:
    return f"{conference_number}-{hashlib.sha1(context.encode('utf-8')).hexdigest()[:10]}"


def build(records: Iterator[tuple[str, dict]]) -> tuple[list[dict], list[dict]]:
    """context 완전 일치 중복만 제거해 (코퍼스, 질의)를 doc_id·qid 순으로 반환한다."""
    queries = []
    docs, first_qid, splits, n_qa = {}, {}, {}, {}
    for split, r in records:
        doc_id = make_doc_id(r["conference_number"], r["context"])
        qid = f"{r['conference_number']}-{r['question_number']}"
        queries.append({
            "qid": qid,
            "doc_id": doc_id,
            "split": split,
            "qna_type": r["qna_type"],
            "query": r["context_summary"]["summary_q"],
            "answer": r["context_summary"]["summary_a"],
            "question_comment": r["question"]["comment"],
            "answer_comment": r["answer"]["comment"],
        })
        if doc_id not in docs or qid < first_qid[doc_id]:
            meta = {k: r.get(k, "") for k in META_FIELDS}
            docs[doc_id] = {"doc_id": doc_id, "context": r["context"], **meta}
            first_qid[doc_id] = qid
        splits.setdefault(doc_id, set()).add(split)
        n_qa[doc_id] = n_qa.get(doc_id, 0) + 1

    qids = [q["qid"] for q in queries]
    if len(set(qids)) != len(qids):
        raise ValueError("qid가 중복된다")
    queries.sort(key=lambda q: q["qid"])

    corpus = [
        {**docs[i], "splits": sorted(splits[i]), "n_qa": n_qa[i]} for i in sorted(docs)
    ]
    return corpus, queries


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        paths = compose(config_name="config").paths
    corpus, queries = build(iter_labels(ROOT / paths.raw_dir))
    write_jsonl(corpus, ROOT / paths.corpus)
    write_jsonl(queries, ROOT / paths.queries)
    print(f"corpus {len(corpus):,} docs -> {paths.corpus}")
    print(f"queries {len(queries):,} -> {paths.queries}")


if __name__ == "__main__":
    main()
