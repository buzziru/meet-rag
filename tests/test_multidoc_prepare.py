from rag.multidoc.prepare import gen_input, select, write_new

META = {"date": "d", "committee_name": "c", "meeting_name": "m", "meeting_number": "n",
        "session_number": "s", "agenda": "a"}
DOCS = {"x": {"context": "가나다라마바사", "conference_number": "1", "summary_q": "질의", **META},
        "y": {"context": "아자차", "conference_number": "2", **META}}


def test_select_takes_first_orders_per_type():
    pools = [{"pool_id": f"{t}-{i}", "order": i} for t in ["conf", "law"] for i in range(3)]
    assert [p["pool_id"] for p in select(pools, 2)] == ["conf-0", "conf-1", "law-0", "law-1"]


def test_gen_input_has_only_metadata_and_overview():
    pool = {"pool_id": "law-0", "type": "law", "key": "법A", "order": 0,
            "doc_ids": ["x", "y"], "seed_doc_ids": ["x", "y"]}
    out = gen_input(pool, DOCS, 3)
    assert set(out) == {"pool_id", "type", "key", "seed_doc_ids", "docs"}
    assert set(out["docs"][0]) == {"doc_id", "overview", *META}
    assert [d["overview"] for d in out["docs"]] == ["가나다", "아자차"]


def test_write_new_skips_existing(tmp_path):
    p = tmp_path / "a.json"
    assert write_new(p, "1")
    assert not write_new(p, "2")
    assert p.read_text(encoding="utf-8") == "1"
