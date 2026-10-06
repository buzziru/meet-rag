from rag.ingest import make_doc_id
from rag.multidoc.prepare import collect_speakers, gen_input, select, speaker_text, write_new

META = {"date": "d", "committee_name": "c", "meeting_name": "m", "meeting_number": "n",
        "session_number": "s", "agenda": "a"}
SPK = [{"name": "김위원", "position": "위원"}]
DOCS = {"x": {"context": "가나다라마바사", "conference_number": "1", "summary_q": "질의",
              "speakers": SPK, **META},
        "y": {"context": "아자차", "conference_number": "2", "speakers": [], **META}}


def test_select_takes_first_orders_per_type():
    pools = [{"pool_id": f"{t}-{i}", "order": i} for t in ["conf", "law"] for i in range(3)]
    assert [p["pool_id"] for p in select(pools, 2)] == ["conf-0", "conf-1", "law-0", "law-1"]


def test_gen_input_has_only_metadata_and_overview():
    pool = {"pool_id": "law-0", "type": "law", "key": "법A", "order": 0,
            "doc_ids": ["x", "y"], "seed_doc_ids": ["x", "y"]}
    out = gen_input(pool, DOCS, 3)
    assert set(out) == {"pool_id", "type", "key", "seed_doc_ids", "docs"}
    assert set(out["docs"][0]) == {"doc_id", "overview", "speakers", *META}
    assert out["docs"][0]["speakers"] == SPK
    assert [d["overview"] for d in out["docs"]] == ["가나다", "아자차"]


def test_write_new_skips_existing(tmp_path):
    p = tmp_path / "a.json"
    assert write_new(p, "1")
    assert not write_new(p, "2")
    assert p.read_text(encoding="utf-8") == "1"


def test_collect_speakers_reads_only_questioner_fields_of_needed_docs():
    recs = [{"conference_number": "1", "context": "c1", "questioner_name": "김위원 ",
             "questioner_position": "위원", "summary_q": "질의"},
            {"conference_number": "1", "context": "c1", "questioner_name": "김위원",
             "questioner_position": "위원"},
            {"conference_number": "1", "context": "c1", "questioner_name": "",
             "questioner_position": ""},
            {"conference_number": "2", "context": "c2", "questioner_name": "이위원",
             "questioner_position": "소위원장"}]
    d1 = make_doc_id("1", "c1")
    out = collect_speakers(recs, {d1})
    assert out == {d1: [{"name": "김위원", "position": "위원"}]}
    assert speaker_text(out[d1]) == "김위원 위원"
    assert speaker_text([]) == "미상"
