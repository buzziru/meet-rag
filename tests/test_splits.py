from collections import Counter

from rag.splits import assign_splits, pick_dev_small


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
