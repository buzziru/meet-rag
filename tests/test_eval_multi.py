import json
from pathlib import Path

import pandas as pd
import pytest
from omegaconf import OmegaConf

from rag.eval_multi.compare import check_single, diff_table, metadata_result
from rag.eval_multi.metrics import (
    frozen_path,
    load_gold,
    metric_table,
    per_query,
    ranked_docs,
    sha256,
)

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


def test_metadata_result_uses_overall_recall_and_complete():
    gold = make_gold([["a", "b"]] * 6)
    base = score(make_run({q: {1: "a"} for q in gold.index}), gold)
    cand = score(make_run({q: {1: "a", 2: "b"} for q in gold.index}), gold)
    rows = diff_table(base, cand, gold, ["type"], **BS)
    hold = {"layer": "dev-full", "diff": 0.0, "ci": [0.0, 0.0], "verdict": "보류"}
    out = metadata_result(hold, rows, 0.01)
    # Recall@5 +50%p, Complete@5 +100%p
    assert (out["verdict"], out["stage"]) == ("채택", "multi-doc")
    assert out["recall@5"] == {"diff": 0.5, "ci": [0.5, 0.5]}
    reject = {"layer": "dev-full", "diff": -0.02, "ci": [-0.03, -0.01], "verdict": "기각"}
    assert metadata_result(reject, rows, 0.01)["stage"] == "single-doc"


P = "data/runs/kure-v1-fixed-512-64-"
MULTI = (Path(P + "hybrid-cond-filter-multidoc.csv"),
         Path(P + "hybrid-cond-filter-law-multidoc.csv"))


def single_json(base, cand, layer="dev-full"):
    return {"layer": layer, "diff": 0.0, "ci": [0.0, 0.0], "verdict": "보류",
            "base": {"run": P + base}, "cand": {"run": P + cand}}


def test_check_single_matches_run_names_across_layers():
    check_single(single_json("hybrid-cond-filter-dev-full.csv",
                             "hybrid-cond-filter-law-dev-full.csv"), *MULTI)
    # EXP-003의 single-doc 결과를 EXP-008의 multi-doc 순위와 섞으면 멈춘다
    with pytest.raises(SystemExit, match="실험이 아니다"):
        check_single(single_json("hybrid-dev-full.csv", "hybrid-cond-dev-full.csv"), *MULTI)


@pytest.mark.parametrize("bad", [
    {"diffs": [], "frozen_sha256": "x"},  # multi-doc 비교 결과를 잘못 넣음(전에는 KeyError)
    single_json("hybrid-cond-filter-dev-small.csv", "hybrid-cond-filter-law-dev-small.csv",
                layer="dev-small"),  # 층이 다름(전에는 "같은 실험이 아니다")
    [],
])
def test_check_single_reports_wrong_input_before_name_check(bad):
    with pytest.raises(SystemExit, match="dev-full 결과 JSON이어야 한다"):
        check_single(bad, *MULTI)


def test_metadata_result_stops_when_single_verdict_used_other_min_gain():
    # min_gain 0.01일 때 채택(+1.5%p, 하한 > 0)으로 기록된 결과를 min_gain 0.02로 넣으면 멈춘다
    gold = make_gold([["a", "b"]] * 2)
    s = score(make_run({q: {1: "a"} for q in gold.index}), gold)
    rows = diff_table(s, s, gold, [], **BS)
    old = {"layer": "dev-full", "diff": 0.015, "ci": [0.005, 0.025], "verdict": "채택"}
    assert metadata_result(old, rows, 0.01)["verdict"] == "채택"
    with pytest.raises(SystemExit, match="min_gain"):
        metadata_result(old, rows, 0.02)


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


def _frozen_cfg(tmp_path):
    """질의 둘(q{i}, 정답 d{i}, pool p{i})의 합성 동결 세트와 그 sha256을 넣은 config."""
    from rag.index import load_cfg
    frozen = tmp_path / "frozen.jsonl"
    frozen.write_text("".join(json.dumps(
        {"qid": f"q{i}", "pool_id": f"p{i}", "type": "conf", "query": "질의",
         "gold_doc_ids": [f"d{i}"], "answer": "…"}) + "\n" for i in range(2)), encoding="utf-8")
    return load_cfg([f"paths.multidoc_frozen='{frozen.as_posix()}'",
                     f"multidoc.frozen_sha256={sha256(frozen)}"])


def test_frozen_set_stops_when_sha_differs(tmp_path):
    from rag.conditions import read_queries
    cfg = _frozen_cfg(tmp_path)
    multi = OmegaConf.merge(cfg, {"search": {"queries": "multidoc"}})
    assert frozen_path(cfg).name == "frozen.jsonl"
    assert [q["qid"] for q in read_queries(multi)] == ["q0", "q1"]
    with Path(cfg.paths.multidoc_frozen).open("a", encoding="utf-8") as f:
        f.write("\n")  # 한 글자만 달라져도 멈춘다
    for read in (lambda: frozen_path(cfg), lambda: read_queries(multi)):
        with pytest.raises(SystemExit, match="G3 동결 값"):
            read()


def test_freeze_does_not_overwrite_frozen_set(tmp_path, monkeypatch, capsys):
    from rag.index import load_cfg
    from rag.multidoc import freeze
    (tmp_path / "queries.jsonl").write_text("".join(
        json.dumps({"qid": q}) + "\n" for q in ["q0", "q1", "q2"]), encoding="utf-8")
    exclude = tmp_path / "exclude.yaml"
    exclude.write_text("sample: [q1]\n", encoding="utf-8")
    cfg = load_cfg([f"paths.{k}='{(tmp_path / v).as_posix()}'" for k, v in
                    [("multidoc_queries", "queries.jsonl"), ("multidoc_exclude", "exclude.yaml"),
                     ("multidoc_frozen", "frozen.jsonl")]])
    monkeypatch.setattr(freeze, "load_cfg", lambda: cfg)
    freeze.main()
    lines = (tmp_path / "frozen.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["qid"] for x in lines] == ["q0", "q2"]
    freeze.main()  # 같은 내용
    assert "그대로 둠" in capsys.readouterr().out
    exclude.write_text("sample: [q2]\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="다시 만들지 않는다"):
        freeze.main()


def test_compare_diff_is_cand_minus_base_and_single_path_runs(tmp_path, monkeypatch, capsys):
    from rag.eval.bootstrap import verdict
    from rag.eval_multi import compare
    cfg = _frozen_cfg(tmp_path)
    monkeypatch.setattr(compare, "load_cfg", lambda: cfg)
    runs = {}
    for name, at in [("base", {"q0": {1: "d0"}, "q1": {}}),
                     ("cand", {"q0": {1: "d0"}, "q1": {2: "d1"}})]:
        runs[name] = tmp_path / f"{name}-multidoc.csv"
        make_run(at).to_csv(runs[name], index=False)
    single = tmp_path / "single.json"
    single.write_text(json.dumps({
        "layer": "dev-full", "diff": 0.0, "ci": [-0.01, 0.01],
        "verdict": verdict(0.0, -0.01, 0.01, cfg.eval.bootstrap.min_gain),
        "base": {"run": "base-dev-full.csv"}, "cand": {"run": "cand-dev-full.csv"}}),
        encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "--base", str(runs["base"]),
                                     "--cand", str(runs["cand"]), "--single", str(single)])
    compare.main()
    result = json.loads(capsys.readouterr().out)
    recall = next(r for r in result["diffs"] if r["group"] == "all" and r["metric"] == "recall@5")
    assert recall["diff"] == pytest.approx(0.5)  # 후보 - 기준: q1만 0 → 1
    meta = result["metadata_verdict"]
    assert (meta["single_verdict"], meta["stage"]) == ("보류", "multi-doc")
    assert meta["recall@5"]["diff"] == pytest.approx(0.5)
    assert meta["single"]["path"] == str(single)


def test_score_and_compare_out_are_guarded(tmp_path, monkeypatch, capsys):
    from rag.eval_multi import compare, score
    cfg = _frozen_cfg(tmp_path)
    monkeypatch.setattr(score, "load_cfg", lambda: cfg)
    monkeypatch.setattr(compare, "load_cfg", lambda: cfg)
    runs = {}
    for name, at in [("a", {"q0": {1: "d0"}, "q1": {}}), ("b", {"q0": {}, "q1": {2: "d1"}})]:
        runs[name] = tmp_path / f"{name}.csv"
        make_run(at).to_csv(runs[name], index=False)
    for module, first, other in [
        (score, ["--run", str(runs["a"])], ["--run", str(runs["b"])]),
        (compare, ["--base", str(runs["a"]), "--cand", str(runs["b"])],
         ["--base", str(runs["b"]), "--cand", str(runs["a"])]),
    ]:
        out = tmp_path / f"{module.__name__}.json"
        monkeypatch.setattr("sys.argv", ["x", *first, "--out", str(out)])
        module.main()
        before = out.read_text(encoding="utf-8")
        module.main()  # 같은 내용
        assert "그대로 둠" in capsys.readouterr().out
        monkeypatch.setattr("sys.argv", ["x", *other, "--out", str(out)])
        with pytest.raises(SystemExit, match="--overwrite"):
            module.main()
        assert out.read_text(encoding="utf-8") == before
        monkeypatch.setattr("sys.argv", ["x", *other, "--out", str(out), "--overwrite"])
        module.main()
        assert out.read_text(encoding="utf-8") != before
