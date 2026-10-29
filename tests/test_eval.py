import json

import numpy as np
import pandas as pd
import pytest

from rag.eval.bootstrap import metadata_verdict, paired_bootstrap, verdict
from rag.eval.metrics import (
    gold_ranks,
    gold_sha256,
    load_gold,
    metric_table,
    min_docs,
    per_query,
)
from rag.index import load_cfg

N_MIN = min_docs([1, 5, 10], 10)


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
    scores = per_query(gold_ranks(run, gold, N_MIN), [1, 5, 10], 10)

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
    assert gold_ranks(run, gold, N_MIN).tolist() == [1, 2]


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r[r["qid"] != "q1"], "없는 qid"),
    (lambda r: pd.concat([r, pd.DataFrame([{"qid": "t9", "rank": 1, "doc_id": "a"}])]), "층 밖"),
    (lambda r: r[~((r["qid"] == "q0") & (r["rank"] == 10))], "10개 미만"),
    (lambda r: r.assign(rank=r["rank"].where(r["rank"] != 2, 1)), "중복"),
])
def test_invalid_runs_raise(mutate, message):
    gold = make_gold()
    with pytest.raises(ValueError, match=message):
        gold_ranks(mutate(make_run(gold, {})), gold, N_MIN)


def test_min_docs_follows_deepest_metric():
    assert min_docs([1, 5, 10], 10) == 10
    assert min_docs([1, 5, 20], 10) == 20
    gold = make_gold()
    with pytest.raises(ValueError, match="20개 미만"):
        gold_ranks(make_run(gold, {}), gold, min_docs([1, 5, 20], 10))


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


@pytest.mark.parametrize(("single", "recall5", "complete5_hi", "expected"), [
    ("채택", (0.0, -0.01, 0.01), -0.5, ("채택", "single-doc")),  # 1항: single-doc 판정 그대로
    ("기각", (0.05, 0.03, 0.07), 0.1, ("기각", "single-doc")),
    ("보류", (0.0165, 0.0091, 0.0249), 0.0483, ("채택", "multi-doc")),  # EXP-008 수치
    ("보류", (0.008, 0.002, 0.014), 0.05, ("보류", "multi-doc")),  # +1.0%p 미만(D-35의 예)
    ("보류", (0.0165, 0.0091, 0.0249), -0.001, ("보류", "multi-doc")),  # Complete@5가 떨어짐
    ("보류", (-0.02, -0.03, -0.01), 0.0, ("기각", "multi-doc")),
    ("보류", (0.01, 0.001, 0.02), 0.0, ("채택", "multi-doc")),  # 경계: 점 추정 = +1.0%p, 상한 = 0
    ("보류", (0.02, 0.0, 0.04), 0.1, ("보류", "multi-doc")),  # 경계: 하한 = 0
])
def test_metadata_verdict_follows_spec(single, recall5, complete5_hi, expected):
    out = metadata_verdict(single, recall5, complete5_hi, 0.01)
    assert (out["verdict"], out["stage"]) == expected


def _gold_files(tmp_path):
    """분할·질의·코퍼스·dev-small 목록 합성 파일. q1·q2는 dev(q2만 dev-small 문서), q3은 test."""
    (tmp_path / "splits.csv").write_text(
        "qid,conference_number,split\nq2,c2,dev\nq1,c1,dev\nq3,c3,test\n", encoding="utf-8")
    rows = [("q1", "d1", "추출형"), ("q2", "d2", "단답형"), ("q3", "d3", "추출형")]
    (tmp_path / "queries.jsonl").write_text("".join(
        json.dumps({"qid": q, "doc_id": d, "qna_type": t, "query": "질의"}, ensure_ascii=False)
        + "\n" for q, d, t in rows), encoding="utf-8")
    (tmp_path / "corpus.jsonl").write_text("".join(
        json.dumps({"doc_id": d, "meeting_name": m, "context": "본문"}, ensure_ascii=False) + "\n"
        for d, m in [("d1", "국정감사"), ("d2", "본회의"), ("d3", "소위원회")]), encoding="utf-8")
    (tmp_path / "small.txt").write_text("d2\n", encoding="utf-8")
    return load_cfg([f"paths.{k}='{(tmp_path / v).as_posix()}'" for k, v in
                     [("splits", "splits.csv"), ("queries", "queries.jsonl"),
                      ("corpus", "corpus.jsonl"), ("dev_small_docs", "small.txt")]])


def test_load_gold_filters_layers_and_attaches_meeting(tmp_path):
    cfg = _gold_files(tmp_path)
    full = load_gold(cfg, "dev-full")
    assert full.index.tolist() == ["q1", "q2"]  # dev만, qid 순
    assert full.loc["q1"].to_dict() == {"doc_id": "d1", "qna_type": "추출형",
                                        "conference_number": "c1", "meeting_name": "국정감사"}
    assert load_gold(cfg, "dev-small").index.tolist() == ["q2"]  # dev-small 문서의 질의만


def test_load_gold_blocks_test_unless_allowed(tmp_path):
    cfg = _gold_files(tmp_path)
    with pytest.raises(SystemExit, match="allow-test"):
        load_gold(cfg, "test")
    assert load_gold(cfg, "test", allow_test=True).index.tolist() == ["q3"]
    with pytest.raises(ValueError, match="알 수 없는 평가 층"):
        load_gold(cfg, "dev")


def test_gold_sha256_covers_split_queries_and_small_list(tmp_path):
    cfg = _gold_files(tmp_path)
    full, small = gold_sha256(cfg, "dev-full"), gold_sha256(cfg, "dev-small")
    assert list(full) == [cfg.paths.splits, cfg.paths.queries]  # 코퍼스는 넣지 않는다
    assert list(small) == [cfg.paths.splits, cfg.paths.queries, cfg.paths.dev_small_docs]
    (tmp_path / "queries.jsonl").write_text("{}\n", encoding="utf-8")
    assert gold_sha256(cfg, "dev-full")[cfg.paths.queries] != full[cfg.paths.queries]


def _run_main(module, args, monkeypatch):
    monkeypatch.setattr("sys.argv", ["x", *args])
    module.main()


def _check_compare_result(result, cfg):
    """기준 a(q1 1위, q2 3위)와 후보 b(q1 2위, q2 없음). 주지표 Recall@5는 q2에서만 1 → 0."""
    bs = cfg.eval.bootstrap
    assert result["primary"] == cfg.eval.primary
    assert result["diff"] == pytest.approx(-0.5)  # 후보 - 기준
    assert result["verdict"] == verdict(result["diff"], *result["ci"], bs.min_gain)


def test_compare_resamples_by_meeting(tmp_path, monkeypatch):
    # 두 질의가 한 회의면 회의 단위 재표본에서 차이는 늘 -0.5다. 질의 단위면 -1·0도 나온다
    from rag.eval import compare
    cfg = _gold_files(tmp_path)
    (tmp_path / "splits.csv").write_text(
        "qid,conference_number,split\nq1,c1,dev\nq2,c1,dev\n", encoding="utf-8")
    monkeypatch.setattr(compare, "load_cfg", lambda: cfg)
    gold = load_gold(cfg, "dev-full")
    for name, pos in [("a", {"q1": 1, "q2": 3}), ("b", {"q1": 2})]:
        make_run(gold, pos).to_csv(tmp_path / f"{name}.csv", index=False)
    out = tmp_path / "compare.json"
    _run_main(compare, ["--base", str(tmp_path / "a.csv"), "--cand", str(tmp_path / "b.csv"),
                        "--out", str(out)], monkeypatch)
    result = json.loads(out.read_text(encoding="utf-8"))
    _check_compare_result(result, cfg)
    assert result["ci"] == pytest.approx([-0.5, -0.5])


def test_score_and_compare_out_are_guarded(tmp_path, monkeypatch, capsys):
    from rag.eval import compare, score
    cfg = _gold_files(tmp_path)
    monkeypatch.setattr(score, "load_cfg", lambda: cfg)
    monkeypatch.setattr(compare, "load_cfg", lambda: cfg)
    gold = load_gold(cfg, "dev-full")
    runs = {}
    for name, pos in [("a", {"q1": 1, "q2": 3}), ("b", {"q1": 2})]:
        runs[name] = tmp_path / f"{name}.csv"
        make_run(gold, pos).to_csv(runs[name], index=False)
    for module, first, other in [
        (score, ["--run", str(runs["a"]), "--layer", "dev-full"],
         ["--run", str(runs["b"]), "--layer", "dev-full"]),
        (compare, ["--base", str(runs["a"]), "--cand", str(runs["b"])],
         ["--base", str(runs["b"]), "--cand", str(runs["a"])]),
    ]:
        out = tmp_path / f"{module.__name__}.json"
        _run_main(module, [*first, "--out", str(out)], monkeypatch)
        before = out.read_text(encoding="utf-8")
        assert json.loads(before)["gold_sha256"] == gold_sha256(cfg, "dev-full")
        if module is compare:
            _check_compare_result(json.loads(before), cfg)
        _run_main(module, [*first, "--out", str(out)], monkeypatch)  # 같은 내용
        assert "그대로 둠" in capsys.readouterr().out
        with pytest.raises(SystemExit, match="--overwrite"):
            _run_main(module, [*other, "--out", str(out)], monkeypatch)
        assert out.read_text(encoding="utf-8") == before
        _run_main(module, [*other, "--out", str(out), "--overwrite"], monkeypatch)
        assert out.read_text(encoding="utf-8") != before
