import pytest
import yaml

from rag.gen_eval.judge import check_speakers
from rag.index import ROOT, load_cfg
from rag.ingest import make_doc_id
from rag.speakers import check_mode, chunk_speakers, doc_spans, fill_counts, render

TITLES = ("위원", "장관")


def label(context, q, a, qn="홍길동 위원", an="김철수", ap="장관", aa="국토교통부", qno="0001"):
    return ("Validation", {
        "conference_number": "000001", "question_number": qno, "context": context,
        "question": {"comment": q}, "answer": {"comment": a},
        "questioner_name": qn, "questioner_position": "위원", "questioner_affiliation": "",
        "answerer_name": an, "answerer_position": ap, "answerer_affiliation": aa})


def test_doc_spans_finds_every_position_with_qa_speaker():
    ctx = "가나다 질문입니다. 라마 답변입니다. 바사 답변입니다."
    recs = [label(ctx, "질문입니다.", "답변입니다.")]
    spans = doc_spans(recs, TITLES, 0)[make_doc_id("000001", ctx)]
    assert [(s["role"], ctx[s["start"]:s["end"]]) for s in spans] == [
        ("question", "질문입니다."), ("answer", "답변입니다."), ("answer", "답변입니다.")]
    assert spans[0]["name"] == "홍길동"  # ingest와 같은 정규화(직함 토막 제거)
    assert {k: spans[1][k] for k in ("name", "position", "affiliation")} == {
        "name": "김철수", "position": "장관", "affiliation": "국토교통부"}


def test_doc_spans_skips_missing_comment_and_dedupes_same_span():
    ctx = "질문입니다. 답변입니다."
    recs = [label(ctx, "질문입니다.", "본문에 없는 답변"),
            label(ctx, "질문입니다.", "", qno="0002")]
    spans = doc_spans(recs, TITLES, 0)[make_doc_id("000001", ctx)]
    assert [s["role"] for s in spans] == ["question"]


def test_doc_spans_keeps_each_speaker_in_multi_qa_doc():
    ctx = "첫 질문. 첫 답변. 둘째 질문. 둘째 답변."
    recs = [label(ctx, "첫 질문.", "첫 답변.", an="김철수"),
            label(ctx, "둘째 질문.", "둘째 답변.", an="이영희", qno="0002")]
    spans = doc_spans(recs, TITLES, 0)[make_doc_id("000001", ctx)]
    assert [(ctx[s["start"]:s["end"]], s["name"]) for s in spans if s["role"] == "answer"] == [
        ("첫 답변.", "김철수"), ("둘째 답변.", "이영희")]


def test_doc_spans_skips_short_repeated_comment_only():
    """짧은 발언이 여러 번 나오면 표지를 두지 않는다. 한 번 나오거나 길면 둔다(PR #178 리뷰 2)."""
    ctx = "예. 그렇게 보십니까? 예. 앞으로 계획을 세워 추진하겠습니다. 끝."
    recs = [label(ctx, "그렇게 보십니까?", "예."),
            label(ctx, "끝.", "앞으로 계획을 세워 추진하겠습니다.", qno="0002")]
    got = [ctx[s["start"]:s["end"]] for s in doc_spans(recs, TITLES, 5)[make_doc_id("000001", ctx)]]
    assert got == ["그렇게 보십니까?", "앞으로 계획을 세워 추진하겠습니다.", "끝."]
    assert "예." in [ctx[s["start"]:s["end"]] for s in doc_spans(recs, TITLES, 0)[
        make_doc_id("000001", ctx)]]


def test_judge_stops_when_speakers_record_meets_prompt_without_marks():
    """발언자 표시 기록은 speaker_marks 지시(j_v9)로만 채점하고, 표시 없는 기록은 어느 지시로도
    채점한다(PR #178 리뷰 1)."""
    v8 = load_cfg(["index.scope=full"])
    v9 = load_cfg(["index.scope=full", "judge/prompt=j_v9"])
    on = {"speakers": {"mode": "marks", "repeat_min_chars": 21}}
    with pytest.raises(SystemExit):
        check_speakers(v8, on)
    check_speakers(v9, on)
    check_speakers(v8, {})
    check_speakers(v9, {})


def test_chunk_speakers_clips_spans_to_chunk_and_head_has_no_spans():
    doc = {"questioners": [{"name": "홍길동"}], "answerers": [{"name": "김철수"}]}
    spans = [{"role": "question", "start": 0, "end": 10, "name": "홍길동"},
             {"role": "answer", "start": 10, "end": 30, "name": "김철수"},
             {"role": "answer", "start": 40, "end": 50, "name": "김철수"}]
    got = chunk_speakers(doc, spans, 5, 20, "marks")
    assert got["questioners"] == doc["questioners"] and got["answerers"] == doc["answerers"]
    assert [(s["role"], s["start"], s["end"]) for s in got["spans"]] == [
        ("question", 0, 5), ("answer", 5, 15)]
    assert "spans" not in chunk_speakers(doc, spans, 5, 20, "head")


def test_render_without_field_is_text_and_marks_nest_at_boundaries():
    assert render({"text": "본문"}) == "본문"
    q = {"name": "홍길동", "position": "위원", "affiliation": ""}
    a = {"name": "김철수", "position": "장관", "affiliation": "국토교통부"}
    head = {"questioners": [q], "answerers": [a]}
    assert render({"text": "본문", "speakers": head}) == (
        "질의자: 홍길동 위원 / 답변자: 김철수 국토교통부 장관\n본문")
    # 닿아 있는 두 구간은 닫는 표지가 먼저, 청크 끝까지 가는 구간도 닫는다
    spans = [{"role": "question", "start": 0, "end": 2, **q},
             {"role": "answer", "start": 2, "end": 4, **a}]
    assert render({"text": "가나다라마", "speakers": {**head, "spans": spans}}).split("\n")[1] == (
        "〈질의 홍길동 위원〉가나〈/질의〉〈답변 김철수 장관〉다라〈/답변〉마")
    empty = {"questioners": [], "answerers": []}
    got = render({"text": "x", "speakers": empty})
    assert got.startswith("질의자: 알 수 없음 / 답변자: 알 수 없음")


def test_check_mode_rejects_unquoted_yaml_off():
    assert check_mode("marks") == "marks"
    with pytest.raises(SystemExit):
        check_mode(False)  # YAML의 따옴표 없는 off


def test_fill_counts():
    docs = [{"questioners": [{"name": "a", "position": "위원", "affiliation": ""}],
             "answerers": [{"name": "b", "position": "", "affiliation": "부"},
                           {"name": "c", "position": "장관", "affiliation": ""}]},
            {"questioners": [], "answerers": []}]
    c = fill_counts(docs)
    assert (c["docs"], c["questioners.name"], c["questioners.affiliation"]) == (2, 1, 0)
    assert (c["answerers.position"], c["answerers.affiliation"], c["answerers.multi"]) == (1, 1, 1)


def test_j_v9_differs_from_j_v8_only_in_speaker_sentence():
    """j_v9는 verdicts 규칙 5와 items 규칙 3의 첫 문장만 바꾼다(S29 결정 사항 1)."""
    d = ROOT / "configs/judge/prompt"
    v8, v9 = (yaml.safe_load((d / f"{v}.yaml").read_text(encoding="utf-8"))
              for v in ("j_v8", "j_v9"))
    assert (v8.pop("version"), v9.pop("version")) == ("j_v8", "j_v9")
    assert v9.pop("speaker_marks") is True and "speaker_marks" not in v8
    old = "근거에는 발언자 표기가 없다."
    changed = {k for k in v8 if v8[k] != v9[k]}
    assert changed == {"verdicts", "items"}
    for k in changed:
        assert v8[k]["user"] == v9[k]["user"]
        a, b = v8[k]["system"], v9[k]["system"]
        assert a.count(old) == 1 and old not in b
        head, tail = a.split(old)
        assert b.startswith(head) and b.endswith(tail)
        assert "〈질의 …〉" in b[len(head):len(b) - len(tail)]
