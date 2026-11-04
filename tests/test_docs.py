"""문서 탐색(S36). data/를 읽지 않고 합성 코퍼스 파일을 쓴다."""

import json

import pytest
from omegaconf import OmegaConf

from rag.docs import Corpus, format_doc, readable
from rag.index import _read_corpus_meta


def row(doc_id, conf, date, context="본문", **kw):
    return {"doc_id": doc_id, "context": context, "conference_number": conf, "date": date,
            "committee_name": kw.get("committee", "법제사법위원회"), "meeting_number": "제1회",
            "session_number": kw.get("session", "제1차"), "agenda": "안건 <i>1</i>",
            "original": "http://example/1", "splits": ["training"], "n_qa": "3",
            "questioners": [{"name": "홍길동", "position": "위원", "affiliation": ""}],
            "answerers": [{"name": "김철수", "position": "장관", "affiliation": "국토부"}]}


@pytest.fixture
def corpus(tmp_path):
    _read_corpus_meta.cache_clear()
    rows = [row("a1", "A", "2018년4월9일(월)", "첫 문서 <b>굵게</b>"),
            row("a2", "A", "2018년4월9일(월)", "둘째 문서"),
            row("b1", "B", "2018년11월7일(수)", "다른 회의"),
            row("c1", "C", "2017년1월2일(월)", "앞선 해"),
            row("d1", "D", "2017년1월2일(월)", "같은 이름 회의"),
            row("e1", "E", "2000年6月28日(水)", "한자 날짜"),
            row("f1", "F", "2000년 7월 2일(일)", "공백 날짜")]
    path = tmp_path / "corpus.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")
    return Corpus(OmegaConf.create({"paths": {"corpus": str(path)}}))


def test_years_and_meetings_are_latest_first(corpus):
    assert corpus.years() == [2018, 2017, 2000]
    assert [c for _, c in corpus.meetings(2000)] == ["F", "E"]
    assert [c for _, c in corpus.meetings(2018)] == ["B", "A"]
    assert corpus.meetings(2018)[1][0] == "2018년4월9일(월) 법제사법위원회 제1회 제1차"


def test_same_named_meetings_are_told_apart(corpus):
    names = [n for n, _ in corpus.meetings(2017)]
    assert len(set(names)) == 2 and all(n.endswith((" (C)", " (D)")) for n in names)


def test_documents_are_named_by_meeting_and_numbered_only_when_needed(corpus):
    assert corpus.documents("A") == [
        ("2018년4월9일(월) 법제사법위원회 제1회 제1차 #1", "a1"),
        ("2018년4월9일(월) 법제사법위원회 제1회 제1차 #2", "a2")]
    assert corpus.documents("B") == [("2018년11월7일(수) 법제사법위원회 제1회 제1차", "b1")]


def test_read_returns_the_chosen_document_from_file(corpus):
    assert corpus.read("a2")["context"] == "둘째 문서"
    assert corpus.read("c1")["context"] == "앞선 해"


def test_format_doc_hides_split_info_and_escapes_html(corpus):
    out = format_doc(corpus.read("a1"), [], "off")
    assert "첫 문서 &lt;b&gt;" in out and "<b>" not in out and "<i>" not in out
    assert "training" not in out and "n_qa" not in out
    assert "(http://example/1)" in out
    assert "질의자" not in out


def test_readable_breaks_at_marks_and_double_spaces_only():
    text = "질의자: 갑 / 답변자: 을\n〈질의 갑〉물음.  다음 말〈/질의〉예, 그렇습니다. <b>끝</b>"
    out = readable(text)
    assert out.split("\n\n") == ["질의자: 갑 / 답변자: 을", "**〈질의 갑〉**", "물음.", "다음 말",
                                 "**〈/질의〉**", "예, 그렇습니다. &lt;b&gt;끝&lt;/b&gt;"]


def test_locate_finds_year_and_meeting_or_nothing(corpus):
    assert corpus.locate("a2") == (2018, "A")
    assert corpus.locate("없는 번호") is None


def test_format_doc_adds_speakers_when_on(corpus):
    spans = [{"role": "answer", "start": 0, "end": 2, "name": "김철수", "position": "장관",
              "affiliation": "국토부"}]
    out = format_doc(corpus.read("a2"), spans, "marks")
    assert "질의자: 홍길동 위원 / 답변자: 김철수 국토부 장관" in out
    assert "**〈답변 김철수 장관〉**\n\n둘째\n\n**〈/답변〉**\n\n 문서" in out
    head = format_doc(corpus.read("a2"), spans, "head")
    assert "질의자: 홍길동 위원" in head and "〈답변" not in head
