import json
import zipfile

import pytest

from rag.index import load_cfg
from rag.ingest import build, iter_labels, make_doc_id, normalize_name

TITLES = tuple(load_cfg().ingest.name_titles)


def label(conf: str, qnum: str, context: str, **kw) -> dict:
    return {
        "conference_number": conf, "question_number": qnum, "context": context,
        "qna_type": "추출형", "date": kw.get("date", "d"), "meeting_name": "본회의",
        "generation_number": "20", "committee_name": "c", "meeting_number": "m",
        "session_number": "s", "agenda": "a", "original": "http://x",
        "context_summary": {"summary_q": f"q{qnum}", "summary_a": f"a{qnum}"},
        "question": {"comment": "qc"}, "answer": {"comment": "ac"},
        **kw.get("people", {}),
    }


def write_zip(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for i, r in enumerate(records):
            zf.writestr(f"/LAB_{i}.json", json.dumps(r, ensure_ascii=False))
        zf.writestr("/readme.txt", "무시")


def test_build_dedupes_context_and_tracks_splits(tmp_path):
    write_zip(tmp_path / "Training/02.라벨링데이터/TL_본회의.zip", [
        label("000001", "0002", "같은 구간", date="late"),
        label("000002", "0001", "다른 구간"),
    ])
    write_zip(tmp_path / "Validation/02.라벨링데이터/VL_본회의.zip", [
        label("000001", "0001", "같은 구간", date="early"),
    ])

    corpus, queries = build(iter_labels(tmp_path), TITLES)

    assert [q["qid"] for q in queries] == ["000001-0001", "000001-0002", "000002-0001"]
    assert [d["doc_id"] for d in corpus] == sorted(d["doc_id"] for d in corpus)
    shared = next(d for d in corpus if d["context"] == "같은 구간")
    assert list(shared) == [
        "doc_id", "context", "conference_number", "date", "meeting_name", "generation_number",
        "committee_name", "meeting_number", "session_number", "agenda", "original",
        "splits", "n_qa", "questioners", "answerers",
    ]
    assert shared["doc_id"] == make_doc_id("000001", "같은 구간")
    assert shared["splits"] == ["Training", "Validation"]
    assert shared["n_qa"] == 2
    assert shared["date"] == "early"  # qid가 가장 작은 레코드의 메타데이터
    assert queries[0]["doc_id"] == queries[1]["doc_id"] == shared["doc_id"]
    assert queries[0] == {
        "qid": "000001-0001", "doc_id": shared["doc_id"], "split": "Validation",
        "qna_type": "추출형", "query": "q0001", "answer": "a0001",
        "question_comment": "qc", "answer_comment": "ac",
    }


def test_build_rejects_duplicate_qid():
    records = [
        ("Training", label("000001", "0001", "x")),
        ("Validation", label("000001", "0001", "y")),
    ]
    with pytest.raises(ValueError):
        build(iter(records), TITLES)


def test_build_collects_speakers_in_qid_order(tmp_path):
    kim = {"questioner_name": " 김갑 ", "questioner_position": "위원", "questioner_affiliation": ""}
    lee = {"questioner_name": "이을 위원", "questioner_position": "위원장"}
    minister = {"answerer_name": "박병", "answerer_position": "장관",
                "answerer_affiliation": "교육부", "answerer_ID": " "}
    write_zip(tmp_path / "Training/02.라벨링데이터/TL_본회의.zip", [
        label("000001", "0003", "구간", people={**kim, **minister}),
        label("000001", "0002", "구간", people={**lee, "answerer_name": " "}),
        label("000001", "0001", "구간", people={**kim, **minister}),
    ])

    (doc,), _ = build(iter_labels(tmp_path), TITLES)

    assert doc["questioners"] == [
        {"name": "김갑", "position": "위원", "affiliation": ""},
        {"name": "이을", "position": "위원장", "affiliation": ""},
    ]
    # 0002의 응답자는 세 값이 모두 비어 빠진다. ID는 넣지 않는다
    assert doc["answerers"] == [{"name": "박병", "position": "장관", "affiliation": "교육부"}]


@pytest.mark.parametrize("raw, name", [
    ("김갑", "김갑"),
    ("김갑 위원", "김갑"),
    ("조달청장 김갑", "김갑"),
    ("김갑(비)", "김갑"),
    ("데이비드 스트라우브", "스트라우브"),
    ("김갑위원", "김갑위원"),  # 붙여 쓴 직함은 그대로 둔다
])
def test_normalize_name(raw, name):
    assert normalize_name(raw, TITLES) == name
