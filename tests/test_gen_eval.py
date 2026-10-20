import json

import pytest

from rag.gen_eval.checks import (
    citation_check,
    gold_position,
    is_refusal,
    metadata_mismatches,
    sentences,
)
from rag.gen_eval.common import done_qids, sample_qids
from rag.gen_eval.judge import (
    faithfulness,
    inclusion,
    judge_record,
    key_presence,
    key_statements,
    parse_json,
    relevance,
    render,
)
from rag.gen_eval.report import chunk_ratio_table, criterion, refusal_table

REFUSAL = "제공된 회의록에서 답을 찾지 못했습니다"


def ctx(n, doc_id="d1", date="2020년3월5일(목)", committee="국방위원회", text="본문"):
    return {"n": n, "doc_id": doc_id, "date": date, "committee_name": committee,
            "meeting_number": "제1회", "session_number": "제2차", "text": text}


def test_refusal_ignores_spacing():
    assert is_refusal("제공된 회의록에서  답을 찾지 못했습니다.", REFUSAL)
    assert not is_refusal("집행률이 낮아 줄였습니다[1].", REFUSAL)


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


def judge_cfg():
    from omegaconf import OmegaConf
    return OmegaConf.create({"gen_eval": {"refusal": REFUSAL, "chunk_key_min": 0.5}})


def test_judge_record_checks_chunk_with_key_statements_even_for_refusal():
    stub = StubJudge({"key_statements": {"key_statements": ["k1", "k2"]},
                      "chunk_checks": {"checks": [{"present": 1}, {"present": 0}]}})
    contexts = [ctx(1, "other"), ctx(2, "gold", text="발췌")]
    out = judge_record.__wrapped__(stub, gen(REFUSAL + ".", contexts),
                                   {"doc_id": "gold", "answer_comment": "발언"}, judge_cfg(), set())
    assert out["refusal"] and out["gold_n"] == 2 and out["answer_in_chunk"] is True
    assert "faithfulness" not in out
    ref = {"doc_id": "none", "answer_comment": "발언"}
    missing = judge_record.__wrapped__(stub, gen(REFUSAL, contexts), ref, judge_cfg(), set())
    assert missing["gold_n"] is None and missing["answer_in_chunk"] is None


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
    row = {"faithfulness": {"score": 2 / 3}, "inclusion": {"score": None, "excluded": "gold_missing"},
           "answer_in_chunk": True}
    assert [fmt(score(row, k)) for k in ("faithfulness", "inclusion", "answer_in_chunk",
                                         "relevance")] == ["0.67", "gold_missing", "True", "-"]
