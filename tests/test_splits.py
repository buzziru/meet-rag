import json
from collections import Counter

import pytest

from rag.index import load_cfg
from rag.splits import assign_splits, pick_dev_small
from rag.splits import main as splits_main


def test_assign_splits_keeps_query_ratio_and_stops_at_minimum():
    meetings = {f"a{i:02d}": ("A", 1) for i in range(30)}
    meetings |= {f"b{i:02d}": ("B", 1) for i in range(10)}
    assigned = assign_splits(meetings, seed=0, targets=[("dev", 20), ("test", 8)])

    assert assign_splits(meetings, seed=0, targets=[("dev", 20), ("test", 8)]) == assigned
    dev = Counter(meetings[c][0] for c, s in assigned.items() if s == "dev")
    assert dev == {"A": 15, "B": 5}
    assert Counter(assigned.values()) == {"dev": 20, "test": 8}


def test_assign_splits_counts_queries_not_meetings():
    meetings = {"big": ("A", 5), "a1": ("A", 1), "b1": ("B", 1), "b2": ("B", 1)}
    assigned = assign_splits(meetings, seed=0, targets=[("dev", 3)])

    dev_queries = sum(meetings[c][1] for c, s in assigned.items() if s == "dev")
    last = list(assigned)[-1]
    assert dev_queries >= 3
    assert dev_queries - meetings[last][1] < 3


def test_pick_dev_small_takes_whole_meetings_until_minimum():
    docs = {"m1": {"d1", "d2"}, "m2": {"d3"}, "m3": {"d4", "d5"}, "m4": {"d6"}}
    picked = pick_dev_small(docs, seed=0, min_docs=3)

    assert picked == sorted(picked)
    included = [m for m, ds in docs.items() if ds <= set(picked)]
    assert sum(len(docs[m]) for m in included) == len(picked)
    assert len(picked) >= 3
    assert any(len(picked) - len(docs[m]) < 3 for m in included)  # 마지막 회의 전에는 미달


def test_main_keeps_same_splits_and_stops_on_different_content(tmp_path, monkeypatch):
    corpus, queries = tmp_path / "corpus.jsonl", tmp_path / "queries.jsonl"
    docs = [{"doc_id": f"d{i}", "conference_number": f"c{i}", "meeting_name": "본회의"}
            for i in range(4)]
    corpus.write_text("".join(json.dumps(d) + "\n" for d in docs), encoding="utf-8")
    queries.write_text("".join(json.dumps({"qid": f"q{i}", "doc_id": f"d{i}", "qna_type": "t"})
                               + "\n" for i in range(4)), encoding="utf-8")
    splits, small = tmp_path / "splits.csv", tmp_path / "dev_small.txt"
    cfg = load_cfg([f"paths.corpus='{corpus.as_posix()}'", f"paths.queries='{queries.as_posix()}'",
                    f"paths.splits='{splits.as_posix()}'",
                    f"paths.dev_small_docs='{small.as_posix()}'", "splits.dev_min_queries=2",
                    "splits.test_min_queries=1", "splits.dev_small_min_docs=1"])
    monkeypatch.setattr("rag.splits.load_cfg", lambda: cfg)
    splits_main()
    before = splits.read_text(encoding="utf-8")
    splits_main()  # 같은 입력이면 같은 내용이라 그대로 둔다
    assert splits.read_text(encoding="utf-8") == before
    splits.write_text(before.replace("dev", "test", 1), encoding="utf-8")
    with pytest.raises(SystemExit, match="보호 경로"):
        splits_main()
