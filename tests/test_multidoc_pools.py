from rag.ingest import make_doc_id
from rag.multidoc.pools import build, collect, find_pools


def rec(conf, qn, context, law="", questioner="", committee="c1"):
    return {"conference_number": conf, "question_number": qn, "context": context, "law": law,
            "questioner_ID": questioner, "committee_name": committee, "summary_q": "질의"}


RECORDS = [
    # 회의 m1: 문서 4개
    rec("m1", "0003", "d1", law="법A", questioner="q1"),
    rec("m1", "0001", "d3", questioner="q1"),
    rec("m1", "0005", "d2"),
    rec("m1", "0007", "d4"),
    # 회의 m2·m3: 법A와 질의자 q1이 다른 회의에 다시 나옴
    rec("m2", "0001", "e1", law="법A ", questioner=" q1"),
    rec("m2", "0002", "e1", law="법A", questioner="q1"),  # 같은 context → 같은 문서
    rec("m3", "0001", "f1", law="법A", questioner="q2"),
    # 회의 m4: 법B는 한 회의에만 있어 법안 유형에서 빠진다
    rec("m4", "0001", "g1", law="법B"),
    rec("m4", "0002", "g2", law="법B"),
    # test 회의
    rec("t1", "0001", "h1", law="법A", questioner="q1"),
]


def rows():
    return collect(RECORDS, test_confs={"t1"})


def test_collect_drops_test_conferences_and_strips_fields():
    r = rows()
    assert "t1" not in set(r["conf"])
    assert set(r.columns) == {"doc_id", "conf", "law", "questioner", "committee"}
    assert set(r.loc[r["conf"] == "m2", "law"]) == {"법A"}
    assert set(r.loc[r["conf"] == "m2", "questioner"]) == {"q1"}


def test_find_pools_applies_type_conditions_and_size_cap():
    r = rows()
    assert [k for k, _ in find_pools(r, "conf", 20)] == ["m1", "m4"]
    assert [k for k, _ in find_pools(r, "conf", 3)] == ["m4"]  # m1(4개)은 상한 초과
    law = dict(find_pools(r, "law", 20))
    assert list(law) == ["법A"]  # 법B는 회의 하나뿐
    assert len(law["법A"]) == 3  # d1, e1(중복 레코드 하나로), f1
    assert [k for k, _ in find_pools(r, "questioner", 20)] == ["q1|c1"]


def test_build_seeds_only_law_pools_from_distinct_conferences_and_is_deterministic():
    r = rows()
    args = dict(types=["conf", "law", "questioner"], max_docs=20,
                n_pools={"conf": 10, "law": 10, "questioner": 10}, seed_sizes=[2, 3], seed=0)
    pools, available = build(r, **args)
    assert build(r, **args) == (pools, available)
    assert available == {"conf": 2, "law": 1, "questioner": 1}
    conf_of = dict(zip(r["doc_id"], r["conf"], strict=True))
    for p in pools:
        if p["type"] != "law":
            assert p["seed_doc_ids"] == []  # S8 생성 에이전트가 고른다
            continue
        assert set(p["seed_doc_ids"]) <= set(p["doc_ids"])
        assert 2 <= len(p["seed_doc_ids"]) <= 3
        assert len({conf_of[d] for d in p["seed_doc_ids"]}) == len(p["seed_doc_ids"])
    m1 = next(p for p in pools if p["key"] == "m1")
    assert m1["doc_ids"] == sorted(make_doc_id("m1", c) for c in ["d1", "d2", "d3", "d4"])
    assert set(pools[0]) == {"pool_id", "type", "key", "order", "doc_ids", "seed_doc_ids"}


def test_build_keeps_order_when_unseeded_types_grow():
    # law 수가 같으면 conf·questioner를 늘려도 기존 후보 집합과 시작 묶음이 그대로다
    r = rows()
    args = dict(types=["conf", "law", "questioner"], max_docs=20, seed_sizes=[2, 3], seed=0)
    small, _ = build(r, n_pools={"conf": 1, "law": 1, "questioner": 1}, **args)
    large, _ = build(r, n_pools={"conf": 2, "law": 1, "questioner": 2}, **args)
    assert small == [p for p in large if p["order"] < 1]


def test_build_limits_pools_per_type():
    pools, _ = build(rows(), types=["conf"], max_docs=20, n_pools={"conf": 1}, seed_sizes=[2],
                     seed=0)
    assert len(pools) == 1 and pools[0]["pool_id"] == "conf-0000"


def test_seed_size_shrinks_to_available():
    pools, _ = build(rows(), types=["law"], max_docs=20, n_pools={"law": 1}, seed_sizes=[5], seed=0)
    assert len(pools[0]["seed_doc_ids"]) == 3  # 법A의 회의는 3개
