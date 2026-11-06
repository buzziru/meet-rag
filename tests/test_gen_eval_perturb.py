"""judge 변형 시험(S53). judge 호출만 가짜로 바꾸고 main을 지나 요약 값을 단언한다."""

import json
import sys

import pytest

from rag.gen_eval import perturb
from rag.index import load_cfg

SENT = "근거에 없는 문장 [1]."


def gen(qid: str, answer: str) -> dict:
    ctx = {"n": 1, "speakers": {"questioners": [{"name": "김질의"}],
                                "answerers": [{"name": "박답변"}]}}
    return {"qid": qid, "query": f"질의 {qid}", "answer": answer, "contexts": [ctx],
            "recipe": {"model": "m", "git_commit": "c1"}}


GENS = [gen("q1", "박답변 장관은 검토하겠다고 답했습니다 [1]."),
        gen("q2", "박답변 차관이 설명했습니다 [1]."),
        gen("q3", "위원회는 의결했습니다 [1]."),  # 답변자 이름이 없어 speaker_swap에서 빠진다
        gen("q4", "박답변 청장은 반대했습니다 [1].")]


def row(qid: str, faith=1.0, rel=1.0, mismatch=False) -> dict:
    reason = "발언자 불일치: 다른 사람" if mismatch else "근거에 있음"
    verdicts = [{"verdict": 1, "reason": reason}]
    return {"qid": qid, "faithfulness": {"score": faith, "verdicts": verdicts},
            "relevance": {"score": rel}}


class FakeJudge:
    calls = hits = 0

    def __init__(self, cfg, session):
        self.http = type("H", (), {"summary": staticmethod(lambda calls: "")})()


def fake_record(judge, g, ref, cfg, committees):
    """변형을 답변으로 알아본다. off_topic은 q1만 관련성이 그대로라 '같음'이 하나 나온다."""
    if SENT in g["answer"]:
        return row(g["qid"], faith=0.5)
    if "김질의" in g["answer"]:
        return row(g["qid"], mismatch=True)
    return row(g["qid"], rel=1.0 if g["qid"] == "q1" else 0.0)


@pytest.fixture
def run(tmp_path, monkeypatch):
    runs, base_path, out = (tmp_path / n for n in ("runs.jsonl", "judge.jsonl", "perturb.jsonl"))
    args = ["+exp=current", f"paths.gen_runs='{runs.as_posix()}'",
            f"paths.gen_judge='{base_path.as_posix()}'", f"paths.gen_perturb='{out.as_posix()}'",
            "gen_eval.perturb.n=3", f"gen_eval.perturb.unsupported_sentence='{SENT}'"]
    rec = perturb.judge_recipe(load_cfg(["index.scope=full", *args]), [g["recipe"] for g in GENS])
    lines = "".join(json.dumps(g, ensure_ascii=False) + "\n" for g in GENS)
    runs.write_text(lines, encoding="utf-8")
    called = []

    def record(*a):
        called.append(a[1]["qid"])
        return fake_record(*a)

    monkeypatch.setattr(perturb, "Judge", FakeJudge)
    monkeypatch.setattr(perturb, "judge_record", record)
    monkeypatch.setattr(perturb, "load_refs", lambda cfg, qids: {q: {} for q in qids})
    monkeypatch.setattr(perturb, "load_committees", lambda cfg: set())
    client = type("C", (), {"flush": lambda s: None})()
    monkeypatch.setattr(perturb, "get_cached_client", lambda: client)

    def go(extra=(), base_recipe=rec):
        base_path.write_text("".join(json.dumps({**row(g["qid"]), "judge_recipe": base_recipe},
                                                ensure_ascii=False) + "\n" for g in GENS),
                             encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["perturb", *args, *extra])
        perturb.main()
        return json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))

    return go, out, called, rec


def test_perturbations_are_deterministic_and_keep_original():
    g = GENS[0]
    before = json.dumps(g, ensure_ascii=False)
    assert perturb.unsupported(g["answer"], SENT) == f"{g['answer']}\n\n{SENT}"
    assert perturb.speaker_swap(g) == "김질의 장관은 검토하겠다고 답했습니다 [1]."
    assert perturb.speaker_swap(g) == perturb.speaker_swap(g)
    assert perturb.speaker_swap(GENS[2]) is None
    assert json.dumps(g, ensure_ascii=False) == before


def test_main_counts_worse_in_expected_direction(run):
    go, _, _, _ = run
    s = go()
    keys = ("metric", "n", "worse", "same", "better", "worse_rate")
    assert {k: s["unsupported"][k] for k in keys} == {"metric": "faithfulness", "n": 3, "worse": 3,
                                                      "same": 0, "better": 0, "worse_rate": 1.0}
    assert (s["unsupported"]["base_mean"], s["unsupported"]["perturbed_mean"]) == (1.0, 0.5)
    # 답변자 이름이 있는 q1·q2·q4만 표본이 되고 모두 불일치가 오른다
    assert (s["speaker_swap"]["n"], s["speaker_swap"]["worse"]) == (3, 3)
    assert s["speaker_swap"]["metric"] == "speaker_mismatch"
    # 표본에 q1이 들면 관련성이 그대로라 '같음'이고, 나머지는 떨어진다
    off = s["off_topic"]
    assert off["worse"] + off["same"] == 3 and off["better"] == 0
    assert off["worse_rate"] == pytest.approx(off["worse"] / 3)


def test_main_stops_before_judge_when_output_exists(run):
    go, out, called, _ = run
    out.write_text("기존\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        go()
    assert called == []


def test_main_runs_only_on_dev_full(run):
    go, _, called, _ = run
    with pytest.raises(SystemExit, match="dev-full"):
        go(["gen_eval.queries=dev-small"])
    assert called == []


def test_main_stops_when_baseline_judge_differs(run):
    go, _, called, rec = run
    with pytest.raises(SystemExit, match="judge 설정"):
        go(base_recipe={**rec, "prompt_sha256": "다른 지시"})
    assert called == []


def test_main_stops_before_judge_when_summary_exists(run):
    go, out, called, _ = run
    out.with_suffix(".summary.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        go()
    assert called == []


@pytest.mark.parametrize("n, match", [(1, "2 이상"), (4, "speaker_swap 대상 질의가 3개")])
def test_main_stops_when_sample_cannot_be_drawn(run, n, match):
    """n이 1이면 off_topic이 자기 답변을 넣고, 대상보다 크면 표본이 조용히 준다.
    둘 다 judge 전에 멈춘다."""
    go, _, called, _ = run
    with pytest.raises(SystemExit, match=match):
        go([f"gen_eval.perturb.n={n}"])
    assert called == []
