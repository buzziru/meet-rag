import json
import sys

import pytest

from rag.gen_eval.checks import (
    HANDLINGS,
    OUTCOMES,
    STATES,
    citation_check,
    gold_position,
    item_counts,
    item_outcome,
    metadata_mismatches,
    refusal_split,
    sentences,
    unlisted_refusal,
)
from rag.gen_eval.common import done_qids, sample_qids
from rag.gen_eval.judge import (
    check_item_steps,
    check_prompt,
    faithfulness,
    inclusion,
    item_eval,
    judge_recipe,
    judge_record,
    key_presence,
    key_statements,
    parse_json,
    relevance,
    render,
    sha,
)
from rag.gen_eval.judge import main as judge_main
from rag.gen_eval.report import (
    case_agreement,
    chunk_ratio_table,
    criterion,
    item_summary,
    refusal_table,
    require_s22,
    unlisted_table,
)
from rag.gen_eval.review import main as review_main
from rag.index import load_cfg

REFUSAL = "제공된 회의록에서 답을 찾지 못했습니다"


def ctx(n, doc_id="d1", date="2020년3월5일(목)", committee="국방위원회", text="본문"):
    return {"n": n, "doc_id": doc_id, "date": date, "committee_name": committee,
            "meeting_number": "제1회", "session_number": "제2차", "text": text}


FILLERS = ["다음과 같습니다"]
PARTIAL = "A 위원은 B를 제안했습니다[1]. C의 시행 시기는 제공된 회의록에서 답을 찾지 못했습니다."


def test_refusal_split_full_partial_none():
    assert refusal_split("제공된 회의록에서  답을 찾지 못했습니다.", REFUSAL, FILLERS)[0] == "full"
    assert refusal_split("다음과 같습니다.\n" + REFUSAL + ".", REFUSAL, FILLERS)[0] == "full"
    ans = "집행률이 낮아 줄였습니다[1].\n통합했습니다[2]."
    assert refusal_split(ans, REFUSAL, FILLERS) == (None, [], ans)
    kind, refused, rest = refusal_split(PARTIAL, REFUSAL, FILLERS)
    assert kind == "partial" and rest == "A 위원은 B를 제안했습니다[1]."
    assert refused == ["C의 시행 시기는 제공된 회의록에서 답을 찾지 못했습니다."]


UNLISTED = ["제공된 회의록에서", "찾지 못했"]


def test_unlisted_refusal_only_without_phrase():
    # S25 베이스라인의 형태: 지정 문구 사이에 대상이 끼어 refusal_split이 거부로 보지 않는다
    ans = "제공된 회의록에서 청장의 대응 계획에 대한 답을 찾지 못했습니다."
    assert refusal_split(ans, REFUSAL, FILLERS)[0] is None
    assert unlisted_refusal(ans, REFUSAL, UNLISTED)
    assert unlisted_refusal("A입니다[1]. 다만, 제공된 회의록에서는 대책을 찾지 못했습니다.",
                            REFUSAL, UNLISTED)
    assert not unlisted_refusal(PARTIAL, REFUSAL, UNLISTED)  # 지정 문구 거부
    assert not unlisted_refusal("자료를 찾지 못했다고 답했습니다[1].", REFUSAL, UNLISTED)


def test_unlisted_table_crosses_no_statements(tmp_path):
    answers = {"q1": "제공된 회의록에서 X에 대한 답을 찾지 못했습니다.",
               "q2": "제공된 회의록에서 Y는 찾지 못했습니다. Z입니다[1].",
               "q3": "아니요, 위원 [1]"}
    path = tmp_path / "runs.jsonl"
    path.write_text("".join(json.dumps({"qid": q, "answer": a, "recipe": {"a": 1}},
                                       ensure_ascii=False) + "\n" for q, a in answers.items()),
                    encoding="utf-8")
    cfg = load_cfg([f"paths.gen_runs={path}"])
    rec = {"refusal": REFUSAL, "gen_recipe_sha256": sha({"a": 1})}
    none = {"score": None, "error": "진술 없음"}
    rows = [{"qid": "q1", "faithfulness": none, "judge_recipe": rec},
            {"qid": "q2", "faithfulness": {"score": 1.0}, "judge_recipe": rec},
            {"qid": "q3", "faithfulness": none, "judge_recipe": rec}]
    assert [k for _, k in unlisted_table(cfg, rows)] == [1, 1, 1]
    # 진술 없음은 judge 형식 오류가 아니라 뺀 이유로 센다
    assert criterion(rows, "faithfulness") == ([1.0], {"no_statements": 2}, 0)
    with pytest.raises(SystemExit):  # 다른 생성 기록이면 멈춘다
        other = {**rec, "gen_recipe_sha256": "x"}
        unlisted_table(cfg, [{**r, "judge_recipe": other} for r in rows])


def test_sentences_attach_trailing_citation():
    assert sentences("예산을 줄였습니다. [1]\n통합했습니다[2].") == ["예산을 줄였습니다. [1]",
                                                               "통합했습니다[2]."]


def test_citation_check_counts_invalid_and_uncited():
    ans = "예산을 줄였습니다[1]. 사업을 통합했습니다[7]. 집행률이 낮았습니다."
    got = citation_check(ans, 5, [])
    assert got == {"n_sentences": 3, "invalid": [7], "uncited": 1, "filler": 0}


def test_citation_check_skips_list_marks_and_fillers():
    ans = ("주요 내용은 다음과 같습니다.\n1. 집행률이 낮았습니다[1].\n"
           "2. 예산을 줄였습니다[2]. 감사합니다.")
    assert sentences(ans)[1:3] == ["1. 집행률이 낮았습니다[1].", "2. 예산을 줄였습니다[2]."]
    got = citation_check(ans, 5, ["다음과 같습니다", "감사합니다"])
    assert got == {"n_sentences": 2, "invalid": [], "uncited": 0, "filler": 2}


def test_metadata_mismatches_checks_cited_doc_only():
    contexts = [ctx(1), ctx(2, "d2", "2021년1월2일(토)", "국방위원회-제1반")]
    ans = ("2020년 3월 5일 국방위원회에서 답했습니다[1]. "
           "2020년 3월 6일 행정안전위원회 회의였습니다[2]. 2019년 1월 1일 회의입니다.")
    got = metadata_mismatches(ans, contexts, {"국방위원회", "행정안전위원회"})
    assert [(m["field"], m["value"]) for m in got] == [("date", "2020-03-06"),
                                                        ("committee", "행정안전위원회")]


def test_metadata_ignores_partial_dates_and_bases_committee():
    contexts = [ctx(1, committee="국방위원회-제1반")]
    assert metadata_mismatches("3월 5일 국방위원회 답변입니다[1].", contexts, {"국방위원회"}) == []


def test_gold_position():
    contexts = [ctx(1, "a"), ctx(2, "b")]
    assert gold_position(contexts, "b") == 2 and gold_position(contexts, "z") is None


def test_sample_keeps_prefix_when_n_grows():
    qids = [f"q{i:03d}" for i in range(50)]
    small, large = sample_qids(qids, 7, 5), sample_qids(list(reversed(qids)), 7, 20)
    assert large[:5] == small and len(set(large)) == 20


def test_done_qids_resumes_and_stops_on_recipe_change(tmp_path, monkeypatch):
    monkeypatch.setattr("rag.gen_eval.common.ROOT", tmp_path)
    path = tmp_path / "run.jsonl"
    assert done_qids(path, {"model": "m"}) == set()
    path.write_text(json.dumps({"qid": "q1", "recipe": {"model": "m", "git_commit": "a"}}) + "\n",
                    encoding="utf-8")
    assert done_qids(path, {"model": "m", "git_commit": "b"}) == {"q1"}
    with pytest.raises(SystemExit):
        done_qids(path, {"model": "other"})


def test_parse_json_and_render():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json("형식 아님") is None and parse_json("[1]") is None
    assert render('질문: {question} 출력: {"x": 1}', question="Q") == '질문: Q 출력: {"x": 1}'


class StubJudge:
    """단계별로 정한 응답을 돌려준다."""

    def __init__(self, replies):
        self.replies = replies

    def ask(self, step, **values):
        return self.replies[step], {"prompt_tokens": 1, "completion_tokens": 1}


def verdicts_reply(statements, verdicts, unclear=None):
    unclear = unclear or [False] * len(statements)
    return {"verdicts": [{"statement": s, "reason": "r", "verdict": v, "speaker_unclear": u}
                         for s, v, u in zip(statements, verdicts, unclear, strict=True)]}


def checks_reply(keys, presents):
    return {"checks": [{"statement": k, "reason": "r", "present": p}
                       for k, p in zip(keys, presents, strict=True)]}


def test_faithfulness_scores_and_format_errors():
    st = {"statements": ["s1", "s2"]}
    ok = StubJudge({"statements": st,
                    "verdicts": verdicts_reply(["s1", "s2"], [1, 0], [True, False])})
    got = faithfulness(ok, "q", "a", [ctx(1)])
    assert got["score"] == 0.5 and [v["speaker_unclear"] for v in got["verdicts"]] == [True, False]
    short = StubJudge({"statements": st, "verdicts": verdicts_reply(["s1"], [1])})
    assert faithfulness(short, "q", "a", [ctx(1)])["error"] == "verdicts 형식 오류"
    # 진술 순서·문구가 입력과 다르면 어느 판정이 어느 진술인지 알 수 없다(P6)
    swapped = StubJudge({"statements": st, "verdicts": verdicts_reply(["s2", "s1"], [1, 0])})
    assert faithfulness(swapped, "q", "a", [ctx(1)])["error"] == "verdicts 형식 오류"
    reworded = StubJudge({"statements": st, "verdicts": verdicts_reply(["s1.", "s2"], [1, 0])})
    assert faithfulness(reworded, "q", "a", [ctx(1)])["error"] == "verdicts 형식 오류"
    no_flag = verdicts_reply(["s1", "s2"], [1, 0])
    del no_flag["verdicts"][0]["speaker_unclear"]
    no_flag = StubJudge({"statements": st, "verdicts": no_flag})
    assert faithfulness(no_flag, "q", "a", [ctx(1)])["error"] == "verdict 값 오류"
    assert faithfulness(StubJudge({"statements": None}), "q", "a", [])["score"] is None


def test_relevance_and_inclusion():
    assert relevance(StubJudge({"relevance": {"label": "일부"}}), "q", "a")["score"] == 0.5
    assert relevance(StubJudge({"relevance": {"label": "?"}}), "q", "a")["score"] is None
    none = StubJudge({"key_statements": {"key_statements": []}})
    ks = key_statements(none, "q", "ref")
    assert inclusion(none, "a", ks)["excluded"] == "reference_unusable"
    assert inclusion(none, "a", None)["excluded"] == "gold_missing"
    two = StubJudge({"key_statements": {"key_statements": ["k1", "k2"]},
                     "key_checks": checks_reply(["k1", "k2"], [1, 1])})
    assert inclusion(two, "a", key_statements(two, "q", "ref"))["score"] == 1.0
    bad = StubJudge({"chunk_checks": checks_reply(["k1"], [1])})
    assert key_presence(bad, "chunk_checks", ["k1", "k2"], excerpt="e")["score"] is None
    swapped = StubJudge({"chunk_checks": checks_reply(["k2", "k1"], [1, 1])})
    assert key_presence(swapped, "chunk_checks", ["k1", "k2"], excerpt="e")["score"] is None


def gen(answer, contexts):
    return {"qid": "q1", "query": "질문", "answer": answer, "contexts": contexts, "usage": {},
            "provider": "p", "first_token_s": 0.1, "total_s": 0.2}


def judge_cfg(item_eval=False):
    from omegaconf import OmegaConf
    return OmegaConf.create({"prompt": {"refusal": REFUSAL},
                             "gen_eval": {"chunk_key_min": 0.5, "filler_phrases": FILLERS,
                                          "item_eval": item_eval}})


def test_judge_record_checks_chunk_with_key_statements_even_for_refusal():
    stub = StubJudge({"key_statements": {"key_statements": ["k1", "k2"]},
                      "chunk_checks": checks_reply(["k1", "k2"], [1, 0])})
    contexts = [ctx(1, "other"), ctx(2, "gold", text="발췌")]
    out = judge_record.__wrapped__(stub, gen(REFUSAL + ".", contexts),
                                   {"doc_id": "gold", "answer_comment": "발언"}, judge_cfg(), set())
    assert out["refusal"] == "full" and out["gold_n"] == 2 and out["answer_in_chunk"] is True
    assert "faithfulness" not in out
    ref = {"doc_id": "none", "answer_comment": "발언"}
    missing = judge_record.__wrapped__(stub, gen(REFUSAL, contexts), ref, judge_cfg(), set())
    assert missing["gold_n"] is None and missing["answer_in_chunk"] is None


class RecordingJudge(StubJudge):
    """단계마다 받은 입력을 남긴다."""

    def __init__(self, replies):
        super().__init__(replies)
        self.seen = {}

    def ask(self, step, **values):
        self.seen[step] = values
        return super().ask(step, **values)


def test_partial_refusal_scores_faithfulness_without_refused_sentence():
    stub = RecordingJudge({
        "key_statements": {"key_statements": ["k1", "k2"]},
        "chunk_checks": checks_reply(["k1", "k2"], [1, 1]),
        "statements": {"statements": ["s1"]}, "verdicts": verdicts_reply(["s1"], [1]),
        "relevance": {"label": "답함"},
        "key_checks": checks_reply(["k1", "k2"], [1, 0])})
    out = judge_record.__wrapped__(stub, gen(PARTIAL, [ctx(1, "gold")]),
                                   {"doc_id": "gold", "answer_comment": "발언"}, judge_cfg(), set())
    assert out["refusal"] == "partial" and out["inclusion"]["score"] == 0.5
    assert stub.seen["statements"]["answer"] == "A 위원은 B를 제안했습니다[1]."
    # 관련성은 거부 문장을 넣은 답변 전체로 채점한다(D-47 결정 4, 기준 문서 R6)
    assert stub.seen["relevance"]["answer"] == PARTIAL
    assert stub.seen["key_checks"]["answer"] == PARTIAL
    assert out["citations"]["n_sentences"] == 1


def items_reply(*states, unclear=False):
    return {"items": [{"item": f"항목{k}", "reason": "r", "state": s, "evidence": [1],
                       "speaker_unclear": unclear} for k, s in enumerate(states, 1)]}


def handling_reply(*handlings):
    return {"handling": [{"n": k, "reason": "r", "handling": h}
                         for k, h in enumerate(handlings, 1)]}


def test_item_outcome_follows_rules():
    # 맞는 처리는 상태마다 하나(D-41 결정 2), 틀린 처리는 유형을 나눈다(결정 사항 2 (a))
    assert item_outcome("있음", "답함") == "맞음"
    assert item_outcome("일부", "부분임을 밝히고 답함") == "맞음"
    assert item_outcome("없음", "거부") == "맞음"
    assert item_outcome("있음", "다루지 않음") == "누락"  # (ㄱ)
    assert item_outcome("없음", "다루지 않음") == "무언 생략"  # (ㄴ)
    assert item_outcome("일부", "거부") == "과잉 거부"  # (ㄷ)
    assert item_outcome("일부", "답함") == "안내 없이 부분 답함"
    assert item_outcome("없음", "답함") == "근거 없이 답함"
    # 모호·회피는 상황을 밝혔는지만 본다(D-41 결정 3, S14c 결정 사항 4)
    for s in ("모호", "회피"):
        assert item_outcome(s, "상황을 밝히고 답함") == "상황 전달"
        rest = [h for h in HANDLINGS if h != "상황을 밝히고 답함"]
        assert {item_outcome(s, h) for h in rest} == {"상황 미전달"}
    # 있음·일부·없음에서 상황을 밝히고 답함은 답함과 같다
    assert all(item_outcome(s, "상황을 밝히고 답함") == item_outcome(s, "답함")
               for s in STATES[:3])
    assert set(OUTCOMES) == {(s, h) for s in STATES[:3] for h in HANDLINGS
                             if h != "상황을 밝히고 답함"}


def test_item_eval_judges_each_item_and_format_errors():
    stub = RecordingJudge({"items": items_reply("있음", "없음", unclear=True),
                           "item_handling": handling_reply("답함", "다루지 않음")})
    out = item_eval(stub, "q", "답변", [ctx(1)])
    assert [i["outcome"] for i in out["items"]] == ["맞음", "무언 생략"]
    assert out["counts"] == {"correct": 1, "judged": 2, "over_refusal": 0, "unsupported": 0}
    assert out["items"][0]["speaker_unclear"] is True
    assert "답변" not in stub.seen["items"].values()  # 정보 상태는 답변 없이 정한다
    assert json.loads(stub.seen["item_handling"]["items"]) == [
        {"n": 1, "item": "항목1"}, {"n": 2, "item": "항목2"}]
    bad_state = StubJudge({"items": items_reply("있음", "애매")})
    assert item_eval(bad_state, "q", "a", [ctx(1)])["error"] == "items 형식 오류"
    assert item_eval(StubJudge({"items": {"items": []}}), "q", "a", [ctx(1)])["error"] == \
        "items 형식 오류"
    for reply in [handling_reply("답함"),  # 항목 수가 다르다
                  {"handling": [{"n": 2, "handling": "답함"}, {"n": 1, "handling": "답함"}]},
                  handling_reply("답함", "모름")]:
        stub = StubJudge({"items": items_reply("있음", "없음"), "item_handling": reply})
        assert item_eval(stub, "q", "a", [ctx(1)])["error"] == "item_handling 형식 오류"


def test_judge_record_runs_item_eval_for_full_refusal():
    stub = StubJudge({"items": items_reply("없음"), "item_handling": handling_reply("거부")})
    ref = {"doc_id": "none", "answer_comment": "발언"}
    out = judge_record.__wrapped__(stub, gen(REFUSAL, [ctx(1)]), ref, judge_cfg(True), set())
    assert out["refusal"] == "full" and out["item_eval"]["items"][0]["outcome"] == "맞음"
    assert "item_eval" not in judge_record.__wrapped__(stub, gen(REFUSAL, [ctx(1)]), ref,
                                                       judge_cfg(False), set())


def test_check_item_steps_stops_without_item_steps():
    check_item_steps(load_cfg(["index.scope=full"]))  # 기본 j_v8에는 두 단계가 있다
    with pytest.raises(SystemExit, match="items, item_handling 단계가 없다"):
        check_item_steps(load_cfg(["index.scope=full", "judge/prompt=j_v5"]))
    check_item_steps(load_cfg(["index.scope=full", "judge/prompt=j_v5",
                               "gen_eval.item_eval=false"]))


def test_item_summary_and_case_agreement():
    def row(*pairs):
        items = [{"state": s, "handling": h, "outcome": item_outcome(s, h),
                  "speaker_unclear": False} for s, h in pairs]
        return {"item_eval": {"items": items, "counts": item_counts(items)}}
    rows = [row(("있음", "답함"), ("모호", "거부")),
            row(("일부", "거부"), ("회피", "상황을 밝히고 답함"), ("없음", "답함")),
            {"item_eval": {"error": "items 형식 오류"}}, {}]
    assert rows[1]["item_eval"]["counts"] == {"correct": 0, "judged": 2, "over_refusal": 1,
                                              "unsupported": 1}
    s = item_summary(rows)
    assert s["accuracy"] == (1, 3) and s["outcomes"]["상황 미전달"] == 1
    assert s["situation"] == (1, 2) and s["ambiguous"] == (2, 5)
    assert s["queries"] == 3 and s["errors"] == 1 and s["wrong_queries"] == 1
    assert s["table"]["모호", "거부"] == 1
    cases = [{"case": "c1", "expected": [{"state": "있음", "handling": "답함"}]},
             {"case": "c2", "expected": [{"state": "없음", "handling": "거부"}] * 2}]
    results = [{"case": "c1", "items": [{"state": "일부", "handling": "답함",
                                         "outcome": "안내 없이 부분 답함"}]},
               {"case": "c2", "items": [{"state": "없음", "handling": "거부", "outcome": "맞음"}]}]
    agree, notes = case_agreement(cases, results)
    assert agree["항목"] == 1 and agree["state"] == 0 and agree["handling"] == 1
    assert agree["항목 수 다른 사례"] == 1 and len(notes) == 3
    # S22 이전 기록은 거부 정확도 0/0이나 KeyError로 읽지 않고 멈춘다
    require_s22([rows[0], {"faithfulness": verdicts_reply(["s1"], [1])}])
    old = row(("있음", "답함"))
    del old["item_eval"]["counts"]
    old_verdicts = {"faithfulness": {"verdicts": [{"statement": "s1", "verdict": 1}]}}
    for bad in (old, old_verdicts):
        with pytest.raises(SystemExit, match="S22 이전 judge 기록"):
            require_s22([bad])


def test_report_criterion_and_refusal_table():
    keys = {"keys": ["k"]}
    rows = [
        {"refusal": None, "gold_n": 1, "answer_in_chunk": True, "key_statements": keys,
         "inclusion": {"score": 0.5}},
        {"refusal": "full", "gold_n": 1, "answer_in_chunk": True, "key_statements": keys},
        {"refusal": "partial", "gold_n": 2, "answer_in_chunk": False, "key_statements": keys,
         "inclusion": {"score": 0.0}},
        {"refusal": None, "gold_n": 3, "answer_in_chunk": None, "key_statements": {"keys": []},
         "inclusion": {"score": None, "excluded": "reference_unusable"}},
        {"refusal": None, "gold_n": 4, "answer_in_chunk": None, "key_statements": keys,
         "inclusion": {"score": 0.5}},  # chunk_checks 형식 오류
        {"refusal": None, "gold_n": None, "answer_in_chunk": None,
         "inclusion": {"score": None, "excluded": "gold_missing"}},
    ]
    scores, excluded, errors = criterion(rows, "inclusion")
    # 전체 거부도 뺀 이유로 센다(기준 문서 K8)
    assert scores == [0.5, 0.0, 0.5] and errors == 0
    assert excluded == {"full_refusal": 1, "reference_unusable": 1, "gold_missing": 1}
    # 판단 불가는 참조 사용 불가와 judge 형식 오류로 나눈다(C2)
    assert refusal_table(rows) == [("정답 문서 있음, 청크에 핵심 답 있음", 2, 1),
                                   ("정답 문서 있음, 청크에 핵심 답 없음", 1, 1),
                                   ("정답 문서 있음, 판단 불가(참조 사용 불가)", 1, 0),
                                   ("정답 문서 있음, 판단 불가(judge 형식 오류)", 1, 0),
                                   ("정답 문서 없음", 1, 0)]


def test_chunk_ratio_table_counts_ratio_and_refusal():
    rows = [{"chunk_keys": {"score": 0.5}, "refusal": False},
            {"chunk_keys": {"score": 0.5}, "refusal": True},
            {"chunk_keys": {"score": 1 / 3}, "refusal": False},
            {"chunk_keys": {"score": None}, "refusal": False},
            {"refusal": False}]
    assert chunk_ratio_table(rows) == [(0.33, 1, 0), (0.5, 2, 1)]


def test_review_score_reads_score_or_exclusion():
    from rag.gen_eval.review import fmt, score
    row = {"faithfulness": {"score": 2 / 3},
           "inclusion": {"score": None, "excluded": "gold_missing"}, "answer_in_chunk": True}
    assert [fmt(score(row, k)) for k in ("faithfulness", "inclusion", "answer_in_chunk",
                                         "relevance")] == ["0.67", "gold_missing", "True", "-"]


def test_judge_step_params_override_request_and_cache(tmp_path):
    import threading
    from types import SimpleNamespace

    from rag.gen_eval.judge import Judge

    sent = []

    def create(**kw):
        sent.append(kw)
        msg = SimpleNamespace(content='{"ok": 1}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=None)

    j = object.__new__(Judge)
    j.j = SimpleNamespace(model="m")
    j.prompt = {s: SimpleNamespace(system="sys", user="{x}") for s in ("verdicts", "relevance")}
    j.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    j.params, j.extra = {"max_tokens": 10}, {"thinking": {"type": "disabled"}}
    j.step = {"verdicts": {"reasoning_effort": "low",
                           "extra_body": {"thinking": {"type": "enabled"}}}}
    j.cache, j.lock, j.calls, j.hits, j.rep = tmp_path, threading.Lock(), 0, 0, 0
    j.ask("verdicts", x="a")
    j.ask("relevance", x="a")
    assert sent[0]["reasoning_effort"] == "low"
    assert sent[0]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "reasoning_effort" not in sent[1] and sent[1]["extra_body"] == j.extra
    assert len(list(tmp_path.iterdir())) == 2


def test_judge_does_not_cache_empty_or_unfinished(tmp_path):
    import threading
    from types import SimpleNamespace

    from rag.gen_eval.judge import Judge

    replies = [("", "stop"), ('{"ok": 1', "length"), ('{"ok": 1}', "stop")]
    sent = []

    def create(**kw):
        content, finish = replies[len(sent)]
        sent.append(kw)
        choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)
        return SimpleNamespace(choices=[choice], usage=None)

    j = object.__new__(Judge)
    j.j = SimpleNamespace(model="m")
    j.prompt = {"relevance": SimpleNamespace(system="sys", user="{x}")}
    j.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    j.params, j.extra, j.step = {}, None, {}
    j.cache, j.lock, j.calls, j.hits, j.rep = tmp_path, threading.Lock(), 0, 0, 0
    assert j.ask("relevance", x="a")[0] is None  # 빈 응답: 저장 안 함
    assert j.ask("relevance", x="a")[0] is None  # 잘린 응답: 저장 안 함
    assert j.ask("relevance", x="a")[0] == {"ok": 1}
    assert j.ask("relevance", x="a")[0] == {"ok": 1}  # 네 번째는 저장 응답
    assert len(sent) == 3 and j.hits == 1 and len(list(tmp_path.iterdir())) == 1


def test_judge_recipe_records_code_checks_and_ignores_gen_commit():
    cfg = load_cfg(["index.scope=full"])
    a = {"git_commit": "A", "git_dirty": False, "model": "m"}
    rec = judge_recipe(cfg, [a, {**a, "git_commit": "B"}])
    assert rec["chunk_key_min"] == cfg.gen_eval.chunk_key_min and rec["refusal"]
    assert rec["gen_commits"] == ["A", "B"] and rec["git_commit"]
    # 커밋만 다른 생성 기록은 같은 레시피로 본다(이어 쓰기 done_qids와 같은 규칙, S15 결정 사항 2)
    assert rec["gen_recipe_sha256"] == judge_recipe(cfg, [{**a, "git_commit": "C"}])[
        "gen_recipe_sha256"]
    assert judge_recipe(cfg, [{**a, "model": "n"}])["gen_recipe_sha256"] != rec["gen_recipe_sha256"]


def test_check_prompt_stops_when_generation_prompt_differs():
    from omegaconf import OmegaConf

    from rag.generate import recipe
    meta = {"names": ["idx"], "n_chunks": 3}
    gen = recipe(load_cfg(["index.scope=full", "prompt=v1"]), meta, stream=False)
    check_prompt(load_cfg(["index.scope=full", "prompt=v1"]), gen)  # 생성과 같은 프롬프트
    changed = OmegaConf.merge(load_cfg(["index.scope=full", "prompt=v1"]),
                              {"prompt": {"refusal": "다른 거부 문구"}})
    with pytest.raises(SystemExit, match="v1"):  # 버전 이름은 같고 거부 문구만 다르다
        check_prompt(changed, gen)


def test_review_stops_when_filled_csv_exists(tmp_path, monkeypatch):
    out = tmp_path / "review"
    out.with_suffix(".csv").write_text("user_choice\n채움\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["rag.gen_eval.review",
                                      f"gen_eval.review.out='{out.as_posix()}'"])
    with pytest.raises(SystemExit, match="search.overwrite"):
        review_main()
    assert "채움" in out.with_suffix(".csv").read_text(encoding="utf-8")


def test_judge_stops_before_calls_when_output_exists(tmp_path, monkeypatch):
    out = tmp_path / "judge.jsonl"
    out.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("rag.gen_eval.judge.read_jsonl", lambda p: pytest.fail("기록을 읽었다"))
    monkeypatch.setattr(sys, "argv", ["rag.gen_eval.judge", f"paths.gen_judge='{out.as_posix()}'"])
    with pytest.raises(SystemExit, match="search.overwrite"):
        judge_main()  # n을 늘려 다시 채점할 때 overwrite를 빼먹으면 호출 전에 멈춘다


def test_j_v8_changes_only_four_steps():
    from omegaconf import OmegaConf
    v7, v8 = (OmegaConf.load(f"configs/judge/prompt/{v}.yaml") for v in ("j_v7", "j_v8"))
    # 바꾸지 않는 단계는 글자까지 같아 저장된 응답을 그대로 쓴다
    for step in ("statements", "key_statements", "key_checks", "chunk_checks"):
        assert v7[step] == v8[step]
    for step in ("verdicts", "relevance", "items", "item_handling"):
        assert v7[step].system != v8[step].system and v7[step].user == v8[step].user
    assert "speaker_unclear" in v8.verdicts.system and "과태료를 두 배로" in v8.verdicts.system
    assert '"검토하겠다"는 발언만 옮긴' not in v8.relevance.system
    assert "실효성 있는 방안을 검토하겠다고 답했습니다[1]" in v8.relevance.system  # R5
    assert "향후 계획은 제공된 회의록에서 답을 찾지 못했습니다" in v8.relevance.system  # R6
    assert "(법, 기관, 사건, 연도)" in v8["items"].system  # G4
    assert "관계 부처와 협의해 정하겠다고 했습니다[1]" in v8.item_handling.system  # I7
    assert load_cfg(["index.scope=full"]).judge.prompt.version == "j_v8"


def test_eval_qids_excludes_dev_queries_only_in_dev_full(monkeypatch):
    import pandas as pd
    from omegaconf import OmegaConf

    from rag.gen_eval.common import dev_queries, eval_qids
    dev = dev_queries(load_cfg(["index.scope=full"]))
    assert len(dev) == 32 and {"035604-0001", "048474-0008"} <= dev  # S14 표본 20 + S25 블라인드 12
    qids = sorted(dev) + [f"q{i:03d}" for i in range(80)]
    monkeypatch.setattr("rag.gen_eval.common.load_gold",
                        lambda cfg, layer: pd.DataFrame(index=qids))
    monkeypatch.setattr("rag.gen_eval.common.dev_queries", lambda cfg: dev)

    def cfg(layer, n):
        return OmegaConf.create({"gen_eval": {"queries": layer, "seed": 7, "n": n}})
    full = eval_qids(cfg("dev-full", 30))
    assert len(full) == 30 and not dev & set(full)
    assert eval_qids(cfg("dev-full", 60))[:30] == full  # 제외 뒤에도 앞 표본이 유지된다
    n = len(qids)
    assert eval_qids(cfg("dev-small", n)) == sample_qids(qids, 7, n)  # 개발 층은 빼지 않는다
    assert sample_qids(qids, 7, n, dev) == [q for q in sample_qids(qids, 7, n) if q not in dev]


def test_print_cases_stops_when_case_file_changed(tmp_path, monkeypatch):
    from hashlib import sha256

    from omegaconf import OmegaConf

    from rag.gen_eval.report import print_cases
    monkeypatch.setattr("rag.gen_eval.report.ROOT", tmp_path)
    src = tmp_path / "cases.jsonl"
    src.write_text(json.dumps({"case": "c1", "expected": [{"state": "없음", "handling": "거부"}]})
                   + "\n", encoding="utf-8")
    result = {"case": "c1", "items": [{"state": "없음", "handling": "거부", "outcome": "맞음"}],
              "judge_recipe": {"item_cases_sha256": sha256(src.read_bytes()).hexdigest()}}
    (tmp_path / "cases.judge.jsonl").write_text(json.dumps(result) + "\n", encoding="utf-8")
    cfg = OmegaConf.create({"gen_eval": {"item_cases": "cases.jsonl"}})
    print_cases(cfg)
    src.write_bytes(src.read_bytes() + b"\n")  # 읽는 내용은 같아도 파일이 바뀌면 멈춘다
    with pytest.raises(SystemExit, match="사례 파일과 다르다"):
        print_cases(cfg)


def test_rep_paths_keep_rep_zero_unchanged():
    small = ["index.scope=full", "+exp=exp017", "gen_eval.queries=dev-small"]
    base = load_cfg(small).paths
    assert base.gen_runs.endswith("-v2-dev-small.jsonl")
    assert base.gen_judge.endswith("-v2-dev-small-deepseek_go_mixed-j_v8.jsonl")
    rep = load_cfg([*small, "gen_eval.gen_rep=1", "judge.rep=2"]).paths
    assert rep.gen_runs.endswith("-v2-dev-small-r1.jsonl")
    assert rep.gen_judge.endswith("-v2-dev-small-r1-deepseek_go_mixed-j_v8-r2.jsonl")


def test_judge_rep_changes_cache_key_and_records_call(tmp_path):
    import threading
    from types import SimpleNamespace

    from rag.gen_eval.judge import Judge, sha

    def create(**kw):
        choice = SimpleNamespace(message=SimpleNamespace(content='{"ok": 1}'), finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=SimpleNamespace(
            model_dump=lambda: {"prompt_tokens": 3, "completion_tokens": 2}))

    j = object.__new__(Judge)
    j.j = SimpleNamespace(model="m")
    j.prompt = {"relevance": SimpleNamespace(system="sys", user="{x}")}
    j.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    j.params, j.extra, j.step = {}, None, {}
    j.cache, j.lock, j.calls, j.hits, j.rep = tmp_path, threading.Lock(), 0, 0, 0
    _, u = j.ask("relevance", x="a")
    body = {"model": "m", "messages": [{"role": "system", "content": "sys"},
                                       {"role": "user", "content": "a"}], "extra": None}
    # 반복 0의 캐시 키는 반복 도입 전과 같다(D-49)
    assert (tmp_path / f"{sha(body)}.json").exists()
    assert u["step"] == "relevance" and u["cached"] is False and u["finish_reason"] == "stop"
    assert u["latency_s"] >= 0 and u["prompt_tokens"] == 3
    _, again = j.ask("relevance", x="a")
    assert again["cached"] is True and again["latency_s"] == u["latency_s"]
    j.rep = 1
    _, rep1 = j.ask("relevance", x="a")
    assert rep1["cached"] is False and len(list(tmp_path.iterdir())) == 2


def test_generate_all_keeps_contexts_and_order_across_concurrency():
    import random
    import time
    from types import SimpleNamespace

    from rag.gen_eval.generate import generate_all

    class StubPipe:
        cfg = SimpleNamespace(generator=SimpleNamespace(context_docs=2))

        def retrieve(self, query, emb, k, qid):
            return [{"n": i, "doc_id": f"{qid}-{i}"} for i in range(1, k + 1)]

        def messages(self, contexts, query):
            return [{"role": "user", "content": query + str(len(contexts))}]

        def generate(self, messages, stream, echo, langsmith_extra=None):
            time.sleep(random.random() * 0.02)  # 끝나는 순서를 섞는다
            return {"answer": messages[0]["content"], "thought": None, "usage": {},
                    "provider": "p", "first_token_s": 0.1, "total_s": 0.2}

    items = [(f"q{i}", f"질의{i}", None) for i in range(12)]
    runs = {}
    for c in (1, 4):
        out = []
        generate_all(StubPipe(), items, {"model": "m"}, c, 0, out.append)
        runs[c] = out
    assert [r["qid"] for r in runs[4]] == [q for q, _, _ in items]  # 표본 순서대로 쓴다
    assert [r["contexts"] for r in runs[1]] == [r["contexts"] for r in runs[4]]
    assert all(r["concurrency"] == 4 and r["retrieve_s"] >= 0 and r["gen_rep"] == 0
               for r in runs[4])


def test_default_eval_set_is_dev_full_330():
    # 판정용 세트(D-50): dev-full, 개발 질의 제외, seed 순서 앞 330개
    g = load_cfg(["index.scope=full"]).gen_eval
    assert (g.queries, g.n, g.concurrency) == ("dev-full", 330, 4)


def test_generate_all_writes_others_when_one_generation_fails():
    from types import SimpleNamespace

    from rag.gen_eval.generate import generate_all

    class FailingPipe:
        cfg = SimpleNamespace(generator=SimpleNamespace(context_docs=1))

        def retrieve(self, query, emb, k, qid):
            return [{"n": 1, "doc_id": qid}]

        def messages(self, contexts, query):
            return [{"role": "user", "content": query}]

        def generate(self, messages, stream, echo, langsmith_extra=None):
            if messages[0]["content"] == "질의2":
                raise RuntimeError("429")
            return {"answer": "a", "thought": None, "usage": {}, "provider": "p",
                    "first_token_s": 0.1, "total_s": 0.2}

    out = []
    items = [(f"q{i}", f"질의{i}", None) for i in range(5)]
    with pytest.raises(SystemExit, match="생성 실패 1건"):
        generate_all(FailingPipe(), items, {"model": "m"}, 4, 0, out.append)
    # 실패한 q2만 빠지고 뒤에 끝난 생성도 쓴다. 다시 실행하면 q2만 남는다
    assert [r["qid"] for r in out] == ["q0", "q1", "q3", "q4"]


def test_http_counts_record_sdk_retries():
    """SDK가 429를 다시 시도하면 요청마다 상태 코드가 남는다(D-51)."""
    import httpx
    from openai import DefaultHttpxClient, OpenAI

    from rag.gen_eval.judge import HttpCounts
    choice = {"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": "{}"}}
    ok = {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [choice]}
    replies = iter([httpx.Response(429, json={"error": "rate"}), httpx.Response(200, json=ok)])
    from langsmith.wrappers import wrap_openai
    counts = HttpCounts()
    # Judge와 같이 LangSmith로 감싸도 훅을 단 HTTP 클라이언트를 쓴다
    client = wrap_openai(OpenAI(base_url="http://test/v1", api_key="k", max_retries=2,
                                http_client=DefaultHttpxClient(
                                    transport=httpx.MockTransport(lambda request: next(replies)),
                                    event_hooks={"request": [counts.on_request],
                                                 "response": [counts.on_response]})))
    r = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "q"}])
    assert r.choices[0].message.content == "{}"
    assert counts.requests == 2 and counts.status == {429: 1, 200: 1}
    assert counts.summary(1) == ("HTTP 요청 2회(응답 상태 200 1, 429 1, 응답 없음 0), "
                                 "성공 호출 밖 요청(재시도·실패) 1회")
    counts.requests += 1  # 타임아웃처럼 응답 없이 끝난 요청
    assert "응답 없음 1" in counts.summary(1)
