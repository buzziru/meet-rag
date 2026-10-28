import yaml

from rag.index import ROOT
from rag.ingest import make_doc_id
from rag.speakers import chunk_speakers, doc_spans, fill_counts

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
    spans = doc_spans(recs, TITLES)[make_doc_id("000001", ctx)]
    assert [(s["role"], ctx[s["start"]:s["end"]]) for s in spans] == [
        ("question", "질문입니다."), ("answer", "답변입니다."), ("answer", "답변입니다.")]
    assert spans[0]["name"] == "홍길동"  # ingest와 같은 정규화(직함 토막 제거)
    assert {k: spans[1][k] for k in ("name", "position", "affiliation")} == {
        "name": "김철수", "position": "장관", "affiliation": "국토교통부"}


def test_doc_spans_skips_missing_comment_and_dedupes_same_span():
    ctx = "질문입니다. 답변입니다."
    recs = [label(ctx, "질문입니다.", "본문에 없는 답변"),
            label(ctx, "질문입니다.", "", qno="0002")]
    spans = doc_spans(recs, TITLES)[make_doc_id("000001", ctx)]
    assert [s["role"] for s in spans] == ["question"]


def test_doc_spans_keeps_each_speaker_in_multi_qa_doc():
    ctx = "첫 질문. 첫 답변. 둘째 질문. 둘째 답변."
    recs = [label(ctx, "첫 질문.", "첫 답변.", an="김철수"),
            label(ctx, "둘째 질문.", "둘째 답변.", an="이영희", qno="0002")]
    spans = doc_spans(recs, TITLES)[make_doc_id("000001", ctx)]
    assert [(ctx[s["start"]:s["end"]], s["name"]) for s in spans if s["role"] == "answer"] == [
        ("첫 답변.", "김철수"), ("둘째 답변.", "이영희")]


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
