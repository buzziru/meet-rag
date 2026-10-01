import numpy as np
import pandas as pd
import pytest

from rag.eval.bootstrap import paired_bootstrap, verdict
from rag.eval.metrics import gold_ranks, metric_table, per_query


def make_gold(n=4):
    return pd.DataFrame(
        {
            "doc_id": [f"g{i}" for i in range(n)],
            "qna_type": ["추출형", "단답형"] * (n // 2),
            "meeting_name": ["국정감사"] * (n // 2) + ["본회의"] * (n - n // 2),
            "conference_number": [f"c{i // 2}" for i in range(n)],
        },
        index=pd.Index([f"q{i}" for i in range(n)], name="qid"),
    )


def make_run(gold, positions):
    """질의마다 정답을 positions[qid] 순위에 두고 나머지는 오답 문서로 채운 10개 순위."""
    rows = []
    for qid, doc in gold["doc_id"].items():
        docs = [f"x{j}" for j in range(10)]
        if positions.get(qid):
            docs[positions[qid] - 1] = doc
        rows += [{"qid": qid, "rank": r, "doc_id": d} for r, d in enumerate(docs, 1)]
    return pd.DataFrame(rows)


def test_metrics_match_hand_computation():
    gold = make_gold()
    run = make_run(gold, {"q0": 1, "q1": 3, "q2": 7, "q3": None})
    scores = per_query(gold_ranks(run, gold), [1, 5, 10], 10)

    assert scores["recall@1"].tolist() == [1, 0, 0, 0]
    assert scores["recall@5"].tolist() == [1, 1, 0, 0]
    assert scores["recall@10"].tolist() == [1, 1, 1, 0]
    assert scores["mrr@10"].tolist() == pytest.approx([1, 1 / 3, 1 / 7, 0])

    table = metric_table(scores, gold, ["meeting_name", "qna_type"])
    assert table.iloc[0]["recall@5"] == 0.5
    assert table.groupby("group")["n"].sum().to_dict() == {
        "all": 4, "meeting_name": 4, "qna_type": 4,
    }


def test_duplicate_docs_keep_best_rank_and_rerank():
    gold = make_gold(2)
    run = make_run(gold, {"q0": 1, "q1": 1})
    # q1: 같은 오답 문서가 1·2위에 반복되고 정답은 3위 → 중복 제거 후 정답 2위
    q1 = ["x0", "x0", "g1"] + [f"y{j}" for j in range(9)]
    run = pd.concat([run[run["qid"] == "q0"],
                     pd.DataFrame({"qid": "q1", "rank": range(1, 13), "doc_id": q1})])
    assert gold_ranks(run, gold).tolist() == [1, 2]


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r[r["qid"] != "q1"], "없는 qid"),
    (lambda r: pd.concat([r, pd.DataFrame([{"qid": "t9", "rank": 1, "doc_id": "a"}])]), "층 밖"),
    (lambda r: r[~((r["qid"] == "q0") & (r["rank"] == 10))], "10개 미만"),
    (lambda r: r.assign(rank=r["rank"].where(r["rank"] != 2, 1)), "중복"),
])
def test_invalid_runs_raise(mutate, message):
    gold = make_gold()
    with pytest.raises(ValueError, match=message):
        gold_ranks(mutate(make_run(gold, {})), gold)


def test_identical_runs_give_zero_and_hold():
    diff = np.zeros(20)
    groups = np.repeat(np.arange(10), 2)
    point, lo, hi = paired_bootstrap(diff, groups, 1000, 0, 0.05)
    assert (point, lo, hi) == (0, 0, 0)
    assert verdict(point, lo, hi, 0.01) == "보류"


def test_clear_gain_adopts_and_clear_loss_rejects():
    rng = np.random.default_rng(1)
    diff = (rng.random(200) < 0.3).astype(float)  # 후보만 맞힌 질의 약 30%
    groups = np.repeat(np.arange(50), 4)
    assert verdict(*paired_bootstrap(diff, groups, 2000, 0, 0.05), 0.01) == "채택"
    assert verdict(*paired_bootstrap(-diff, groups, 2000, 0, 0.05), 0.01) == "기각"


def test_bootstrap_is_deterministic_for_same_seed():
    diff = np.linspace(-1, 1, 30)
    groups = np.repeat(np.arange(10), 3)
    assert paired_bootstrap(diff, groups, 500, 7, 0.05) == paired_bootstrap(
        diff, groups, 500, 7, 0.05
    )


def test_resampling_unit_is_meeting():
    # 회의 둘: 한 회의는 질의 전부 +1, 다른 회의는 전부 -1.
    # 질의 단위로 뽑으면 0.5 근처 평균이 흔하지만, 회의 단위면 평균은 -1, 0, 1만 나온다
    diff = np.array([1.0] * 5 + [-1.0] * 5)
    groups = np.array(["a"] * 5 + ["b"] * 5)
    _, lo, hi = paired_bootstrap(diff, groups, 1000, 0, 0.05)
    assert (lo, hi) == (-1, 1)
