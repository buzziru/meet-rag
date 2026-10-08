import json

import pandas as pd
import pytest

from rag.eval_multi.compare import diff_table
from rag.eval_multi.metrics import load_gold, metric_table, per_query, ranked_docs

KS = [5, 10]
BS = {"n_resamples": 500, "seed": 0, "alpha": 0.05}


def make_gold(golds, types=None):
    n = len(golds)
    return pd.DataFrame(
        {"type": types or ["conf", "law"] * (n // 2) + ["conf"] * (n % 2),
         "pool_id": [f"p{i}" for i in range(n)],
         "gold": [frozenset(g) for g in golds]},
        index=pd.Index([f"q{i}" for i in range(n)], name="qid"),
    )


def make_run(placement):
    """placement[qid] = {순위: doc_id}. 나머지 순위는 오답 문서로 채운 10개."""
    rows = []
    for qid, at in placement.items():
        docs = [at.get(r, f"x{r}") for r in range(1, 11)]
        rows += [{"qid": qid, "rank": r, "doc_id": d} for r, d in enumerate(docs, 1)]
    return pd.DataFrame(rows)


def score(run, gold, ks=KS):
    return per_query(ranked_docs(run, gold, max(ks)), gold, ks)


def test_metrics_match_hand_computation():
    gold = make_gold([["a", "b"], ["c", "d", "e"], ["f", "g"], ["h", "i"]])
    run = make_run({
        "q0": {1: "a", 2: "b"},          # 둘 다 5위 안
        "q1": {1: "c", 6: "d"},          # @5 1/3, @10 2/3
        "q2": {7: "f", 8: "g"},          # @5 없음, @10 모두
        "q3": {},                        # 없음
    })
    s = score(run, gold)
    assert s["recall@5"].tolist() == pytest.approx([1, 1 / 3, 0, 0])
    assert s["recall@10"].tolist() == pytest.approx([1, 2 / 3, 1, 0])
    assert s["complete@5"].tolist() == [1, 0, 0, 0]
    assert s["complete@10"].tolist() == [1, 0, 1, 0]
    assert s["hit@5"].tolist() == [1, 1, 0, 0]
    assert s["hit@10"].tolist() == [1, 1, 1, 0]


def test_duplicate_docs_are_reranked():
    gold = make_gold([["a", "b"]])
    # 청크 결과: a가 1·2위에 중복. 제거하면 b가 5위가 된다
    rows = ["a", "a", "x1", "x2", "x3", "b", "x4", "x5", "x6", "x7", "x8"]
    run = pd.DataFrame({"qid": "q0", "rank": range(1, 12), "doc_id": rows})
    assert score(run, gold)["complete@5"].tolist() == [1]


@pytest.mark.parametrize("bad", ["missing", "extra", "short", "dup_rank"])
def test_invalid_runs_raise(bad):
    gold = make_gold([["a", "b"], ["c", "d"]])
    run = make_run({"q0": {1: "a"}, "q1": {1: "c"}})
    if bad == "missing":
        run = run[run["qid"] == "q0"]
    elif bad == "extra":
        run = pd.concat([run, make_run({"q9": {}})])
    elif bad == "short":
        run = run[~((run["qid"] == "q1") & (run["rank"] == 10))]
    else:
        run.loc[1, "rank"] = 1
    with pytest.raises(ValueError):
        score(run, gold)


def test_floor_follows_ks():
    gold = make_gold([["a", "b"]])
    run = make_run({"q0": {1: "a"}})
    run = run[run["rank"] <= 5]
    assert score(run, gold, [3, 5])["hit@5"].tolist() == [1]
    with pytest.raises(ValueError):
        score(run, gold, [5, 10])


def test_metric_table_groups_sum_to_total():
    gold = make_gold([["a", "b"]] * 5)
    run = make_run({q: {1: "a", 2: "b"} for q in gold.index})
    table = metric_table(score(run, gold), gold, ["type"])
    assert table.loc[table["group"] == "type", "n"].sum() == table.loc[0, "n"] == 5


def test_compare_same_run_is_zero():
    gold = make_gold([["a", "b"]] * 6)
    s = score(make_run({q: {1: "a"} for q in gold.index}), gold)
    for row in diff_table(s, s, gold, ["type"], **BS):
        assert row["diff"] == 0 and row["ci"] == [0, 0]
    assert "verdict" not in row


def test_compare_full_gain_and_seed_stable():
    gold = make_gold([["a", "b"]] * 6)
    base = score(make_run({q: {1: "a"} for q in gold.index}), gold)
    cand = score(make_run({q: {1: "a", 2: "b"} for q in gold.index}), gold)
    rows = diff_table(base, cand, gold, [], **BS)
    complete = next(r for r in rows if r["metric"] == "complete@5")
    assert complete["diff"] == 1 and complete["ci"] == [1, 1]
    assert rows == diff_table(base, cand, gold, [], **BS)


def test_bootstrap_unit_is_pool():
    # 두 질의가 같은 pool이면 늘 함께 뽑혀 차이 평균이 그 pool의 평균에 묶인다
    gold = make_gold([["a", "b"]] * 4)
    gold["pool_id"] = ["p0", "p0", "p1", "p1"]
    base = score(make_run({q: {} for q in gold.index}), gold)
    cand = score(make_run({"q0": {1: "a"}, "q1": {}, "q2": {}, "q3": {1: "a"}}), gold)
    hit = next(r for r in diff_table(base, cand, gold, [], **BS) if r["metric"] == "hit@5")
    assert hit["ci"] == [0.5, 0.5]


def test_load_gold_reads_frozen_fields(tmp_path):
    path = tmp_path / "q.jsonl"
    rec = {"qid": "md-conf-0001", "pool_id": "conf-0001", "type": "conf", "query": "질의",
           "gold_doc_ids": ["d1", "d2"], "answer": "…"}
    path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    gold = load_gold(path)
    assert gold.loc["md-conf-0001", "gold"] == frozenset({"d1", "d2"})
    assert list(gold.columns) == ["type", "pool_id", "gold"]
    assert len(gold) == 1
