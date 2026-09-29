from rag.sample_review import sample_qids


def test_sample_qids_is_deterministic_sorted_and_order_independent():
    qids = [f"q{i:03d}" for i in range(50)]
    picked = sample_qids(qids, seed=1, n=10)

    assert picked == sorted(picked)
    assert len(set(picked)) == 10 and set(picked) <= set(qids)
    assert sample_qids(list(reversed(qids)), seed=1, n=10) == picked
