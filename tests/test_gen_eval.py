import json
import sys

import pytest

from rag.gen_eval.checks import (
    HANDLINGS,
    OUTCOMES,
    STATES,
    citation_check,
    gold_position,
    item_outcome,
    metadata_mismatches,
    refusal_split,
    sentences,
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
)
from rag.gen_eval.judge import main as judge_main
from rag.gen_eval.report import (
    case_agreement,
    chunk_ratio_table,
    criterion,
    item_summary,
    refusal_table,
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


def test_faithfulness_scores_and_format_errors():
    ok = StubJudge({"statements": {"statements": ["s1", "s2"]},
                    "verdicts": {"verdicts": [{"verdict": 1}, {"verdict": 0}]}})
    assert faithfulness(ok, "q", "a", [ctx(1)])["score"] == 0.5
    short = StubJudge({"statements": {"statements": ["s1", "s2"]},
                       "verdicts": {"verdicts": [{"verdict": 1}]}})
    assert faithfulness(short, "q", "a", [ctx(1)])["error"] == "verdicts 형식 오류"
    assert faithfulness(StubJudge({"statements": None}), "q", "a", [])["score"] is None


def test_relevance_and_inclusion():
    assert relevance(StubJudge({"relevance": {"label": "일부"}}), "q", "a")["score"] == 0.5
    assert relevance(StubJudge({"relevance": {"label": "?"}}), "q", "a")["score"] is None
    none = StubJudge({"key_statements": {"key_statements": []}})
    ks = key_statements(none, "q", "ref")
    assert inclusion(none, "a", ks)["excluded"] == "reference_unusable"
    assert inclusion(none, "a", None)["excluded"] == "gold_missing"
    two = StubJudge({"key_statements": {"key_statements": ["k1", "k2"]},
                     "key_checks": {"checks": [{"present": 1}, {"present": 1}]}})
    assert inclusion(two, "a", key_statements(two, "q", "ref"))["score"] == 1.0
    bad = StubJudge({"chunk_checks": {"checks": [{"present": 1}]}})
    assert key_presence(bad, "chunk_checks", ["k1", "k2"], excerpt="e")["score"] is None


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
                      "chunk_checks": {"checks": [{"present": 1}, {"present": 0}]}})
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


def test_partial_refusal_scores_content_without_refused_sentence():
    stub = RecordingJudge({
        "key_statements": {"key_statements": ["k1", "k2"]},
        "chunk_checks": {"checks": [{"present": 1}, {"present": 1}]},
        "statements": {"statements": ["s1"]}, "verdicts": {"verdicts": [{"verdict": 1}]},
        "relevance": {"label": "일부"},
        "key_checks": {"checks": [{"present": 1}, {"present": 0}]}})
    out = judge_record.__wrapped__(stub, gen(PARTIAL, [ctx(1, "gold")]),
                                   {"doc_id": "gold", "answer_comment": "발언"}, judge_cfg(), set())
    assert out["refusal"] == "partial" and out["inclusion"]["score"] == 0.5
    assert stub.seen["statements"]["answer"] == "A 위원은 B를 제안했습니다[1]."
    assert stub.seen["relevance"]["answer"] == "A 위원은 B를 제안했습니다[1]."
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
    check_item_steps(load_cfg(["index.scope=full"]))  # 기본 j_v7에는 두 단계가 있다
    with pytest.raises(SystemExit, match="items, item_handling 단계가 없다"):
        check_item_steps(load_cfg(["index.scope=full", "judge/prompt=j_v5"]))
    check_item_steps(load_cfg(["index.scope=full", "judge/prompt=j_v5",
                               "gen_eval.item_eval=false"]))


def test_item_summary_and_case_agreement():
    def row(*pairs):
        return {"item_eval": {"items": [
            {"state": s, "handling": h, "outcome": item_outcome(s, h), "speaker_unclear": False}
            for s, h in pairs]}}
    rows = [row(("있음", "답함"), ("모호", "거부")),
            row(("일부", "거부"), ("회피", "상황을 밝히고 답함")),
            {"item_eval": {"error": "items 형식 오류"}}, {}]
    s = item_summary(rows)
    assert s["accuracy"] == (1, 2) and s["outcomes"]["상황 미전달"] == 1
    assert s["situation"] == (1, 2)
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


def test_report_criterion_and_refusal_table():
    rows = [
        {"refusal": False, "gold_n": 1, "answer_in_chunk": True,
         "inclusion": {"score": 0.5}},
        {"refusal": True, "gold_n": 1, "answer_in_chunk": True},
        {"refusal": True, "gold_n": 2, "answer_in_chunk": False},
        {"refusal": False, "gold_n": 3, "answer_in_chunk": None},
        {"refusal": False, "gold_n": None, "answer_in_chunk": None,
         "inclusion": {"score": None, "excluded": "gold_missing"}},
    ]
    scores, excluded, errors = criterion(rows, "inclusion")
    assert scores == [0.5] and excluded == {"gold_missing": 1} and errors == 0
    assert refusal_table(rows) == [("정답 문서 있음, 청크에 핵심 답 있음", 2, 1),
                                   ("정답 문서 있음, 청크에 핵심 답 없음", 1, 1),
                                   ("정답 문서 있음, 판단 불가", 1, 0),
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
    j.cache, j.lock, j.calls, j.hits = tmp_path, threading.Lock(), 0, 0
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
    j.cache, j.lock, j.calls, j.hits = tmp_path, threading.Lock(), 0, 0
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
