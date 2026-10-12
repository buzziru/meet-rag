"""라벨 zip에서 코퍼스(corpus_context.jsonl)와 평가 질의(queries_summary_q.jsonl)를 만든다.

형식과 doc_id 규칙은 docs/data.md §16, 절차는 docs/slices/01-data.md,
화자 필드는 docs/slices/10-speaker-fields.md.
"""

import hashlib
import json
import re
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
# 문서 필드 이름 → 라벨 키 접두사. 화자는 QA 라벨에만 있어 문서의 QA들에서 모은다(S10)
SPEAKERS = {"questioners": "questioner", "answerers": "answerer"}
SPEAKER_KEYS = ["name", "position", "affiliation"]


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


def normalize_name(name: str, titles: tuple[str, ...]) -> str:
    """끝의 괄호 표기를 지우고, 공백이 있으면 직함 앞 토막이나 마지막 토막을 이름으로 둔다.

    `○○○ 위원` → `○○○`, `조달청장 ○○○` → `○○○`, `○○○(비)` → `○○○` (D-20).
    """
    name = re.sub(r"\s*[(（][^)）]*[)）]$", "", name).strip()
    if " " in name:
        parts = name.split()
        name = parts[0] if parts[-1].endswith(titles) else parts[-1]
    return name


def speaker(r: dict, prefix: str, titles: tuple[str, ...]) -> dict:
    person = {k: (r.get(f"{prefix}_{k}") or "").strip() for k in SPEAKER_KEYS}
    person["name"] = normalize_name(person["name"], titles)
    return person


def collect_speakers(entries: list[tuple[str, dict]]) -> dict:
    """(qid, 역할별 화자) 목록을 qid 순으로 훑어 역할마다 중복 없는 화자 목록을 만든다.

    세 값이 모두 빈 항목은 넣지 않는다.
    """
    out = {field: [] for field in SPEAKERS}
    for _, people in sorted(entries, key=lambda e: e[0]):
        for field, person in people.items():
            if any(person.values()) and person not in out[field]:
                out[field].append(person)
    return out


def build(
    records: Iterator[tuple[str, dict]], titles: tuple[str, ...]
) -> tuple[list[dict], list[dict]]:
    """context 완전 일치 중복만 제거해 (코퍼스, 질의)를 doc_id·qid 순으로 반환한다."""
    queries = []
    docs, first_qid, splits, n_qa, speakers = {}, {}, {}, {}, {}
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
        people = {field: speaker(r, prefix, titles) for field, prefix in SPEAKERS.items()}
        speakers.setdefault(doc_id, []).append((qid, people))

    qids = [q["qid"] for q in queries]
    if len(set(qids)) != len(qids):
        raise ValueError("qid가 중복된다")
    queries.sort(key=lambda q: q["qid"])

    corpus = [
        {**docs[i], "splits": sorted(splits[i]), "n_qa": n_qa[i], **collect_speakers(speakers[i])}
        for i in sorted(docs)
    ]
    return corpus, queries


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config")
    paths = cfg.paths
    corpus, queries = build(iter_labels(ROOT / paths.raw_dir), tuple(cfg.ingest.name_titles))
    write_jsonl(corpus, ROOT / paths.corpus)
    write_jsonl(queries, ROOT / paths.queries)
    print(f"corpus {len(corpus):,} docs -> {paths.corpus}")
    print(f"queries {len(queries):,} -> {paths.queries}")


if __name__ == "__main__":
    main()
