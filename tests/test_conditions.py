import json

import pytest

from rag.conditions import (
    ConditionIndex,
    Extractor,
    agenda_laws,
    committee_base,
    doc_values,
)
from rag.index import ROOT, load_cfg

CFG = load_cfg()
META = {
    "committee_name": {
        "국방위원회": 3, "국방위원회-제1반": 1, "예산결산특별위원회": 2, "국회본회의": 1,
    },
    "meeting_name": dict.fromkeys(
        ["국정감사", "소위원회", "특별위원회", "예산결산특별위원회", "본회의"], 1
    ),
    "name": {"김갑동": 2, "김갑": 1, "이을": 1, "위원": 9, "정부": 9, "000": 1},
}


@pytest.fixture(scope="module")
def ex():
    c = CFG.conditions
    return Extractor(META, CFG.ingest.name_titles, c.name_suffixes, set(c.name_exclude))


@pytest.mark.parametrize("text, want", [
    ("2019년 3월 5일 회의", ["2019-03-05"]),
    ("2019년3월에 열린", ["2019-03"]),
    ("2019년과 2020년 회의", ["2019", "2020"]),
    ("2018년도 예산안을 2017년 11월에 심사", ["2017-11"]),  # 년도는 회계연도
])
def test_date(ex, text, want):
    assert ex.extract(text)["date"] == want


def test_numbers(ex):
    got = ex.extract("제20대 국회 제364회 제2차 회의에서 제1차관이 답했다")
    assert got["generation_number"] == ["20"]
    assert got["meeting_number"] == ["제364회"]
    assert got["session_number"] == ["제2차"]  # 제1차관은 차수가 아니다


def test_numbers_reject(ex):
    got = ex.extract("제1회의실에서 제1차관이 제2회 추가경정예산을 설명했다")
    assert "meeting_number" not in got and "session_number" not in got


def test_committee_longest_and_alias(ex):
    got = ex.extract("국방위 회의와 예산결산특별위원회 회의")
    assert got["committee_name"] == ["국방위원회", "예산결산특별위원회"]
    # 예산결산특별위원회 안의 특별위원회는 버린다
    assert got["meeting_name"] == ["예산결산특별위원회"]


@pytest.mark.parametrize("text, want", [
    ("김갑동 위원이 질의했다", ["김갑동"]),  # 긴 이름 우선
    ("김갑 의원의 질의", ["김갑"]),
    ("(이을) 장관", ["이을"]),
    ("이을이 답했다", ["이을"]),  # 조사
    ("이을", ["이을"]),
])
def test_names(ex, text, want):
    assert ex.extract(text)["names"] == want


@pytest.mark.parametrize("text", [
    "김갑동산 개발",  # 뒤가 이름 경계가 아니다
    "새김갑 위원",  # 앞이 한글이다
    "정부 위원 000 의견",  # 사전 이름 칸의 이름이 아닌 값
])
def test_names_reject(ex, text):
    assert "names" not in ex.extract(text)


def test_empty(ex):
    assert ex.extract("예산 집행 현황은?") == {}


def test_doc_values():
    doc = {"date": "2000年6月28日(水)", "generation_number": "16", "meeting_number": "제212회",
           "session_number": "제1차", "committee_name": "국방위원회-제1반",
           "meeting_name": "국정감사",
           "questioners": [{"name": "김갑", "position": "", "affiliation": ""}], "answerers": []}
    v = doc_values(doc)
    assert v["date"] == {"2000", "2000-06", "2000-06-28"}
    assert v["committee_name"] == {"국방위원회-제1반", "국방위원회"}
    assert v["names"] == {"김갑"}


@pytest.fixture(scope="module")
def ex_alias():
    c = CFG.conditions
    return Extractor(META, CFG.ingest.name_titles, c.name_suffixes, set(c.name_exclude),
                     c.committee_aliases)


@pytest.mark.parametrize("text, date, year_ref", [
    ("2019년도 예산안", None, ["2019"]),
    ("2018회계연도 결산과 2017 회계연도", None, ["2018", "2017"]),
    ("'19년 3월 회의", ["2019-03"], None),
    ("'19년도와 98년도 예산", None, ["2019", "1998"]),
    ("19년 만에 개정, 19년간 유지", None, None),  # 기간 표현
])
def test_year_forms(ex, text, date, year_ref):
    got = ex.extract(text)
    assert got.get("date") == date
    assert got.get("year_ref") == year_ref


def test_committee_alias_table(ex_alias):
    assert ex_alias.extract("법사위 회의")["committee_name"] == ["법제사법위원회"]
    assert ex_alias.extract("국회 본회의에서")["committee_name"] == ["국회본회의"]
    # 시기별로 여러 위원회를 가리키는 약칭은 모두 낸다
    assert ex_alias.extract("외통위")["committee_name"] == ["외교통일위원회", "외교통상통일위원회"]


META_DICT = ROOT / CFG.paths.meta_dict


@pytest.mark.skipif(not META_DICT.exists(), reason="값 사전은 data/에 있어 저장소에 없다")
def test_alias_names_in_dictionary():
    committees = {committee_base(c) for c in json.loads(META_DICT.read_text(encoding="utf-8"))
                  ["committee_name"]}
    names = {n for v in CFG.conditions.committee_aliases.values() for n in v}
    assert names <= committees


def _doc(date, committee, names=()):
    return {"date": date, "generation_number": "21", "meeting_number": "제382회",
            "session_number": "제1차", "committee_name": committee, "meeting_name": "소위원회",
            "questioners": [{"name": n, "position": "", "affiliation": ""} for n in names],
            "answerers": []}


def test_condition_index_counts_fields():
    docs = [_doc("2020년12월30일(수)", "법제사법위원회", ["박주민"]),
            _doc("2020년12월30일(수)", "정무위원회"),
            _doc("2019년3월5일(화)", "법제사법위원회")]
    idx = ConditionIndex(docs, [-1, 0, 1])
    got = idx.match_counts({"date": ["2020-12-30"], "committee_name": ["법제사법위원회"],
                            "names": ["박주민", "없는이름"]})
    assert got == {0: 3, 1: 1, 2: 1}
    # 여러 값을 내는 약칭은 하나만 맞아도 그 필드가 맞는다
    both = {"committee_name": ["정무위원회", "법제사법위원회"]}
    assert idx.match_counts(both) == {0: 1, 1: 1, 2: 1}
    assert idx.match_counts({}) == {}


def test_condition_index_year_ref_window():
    docs = [_doc(f"{y}년1월1일(월)", "정무위원회") for y in (2017, 2018, 2019, 2020, 2021)]
    idx = ConditionIndex(docs, [-1, 0, 1])
    assert set(idx.match_counts({"year_ref": ["2019"]})) == {1, 2, 3}


def test_agenda_laws():
    agenda = ("1. 은행법 일부개정법률안(민병덕 의원 대표발의)(의안번호 2114299) "
              "2. 인터넷전문은행 설립 및 운영에 관한 특례법 일부개정법률안(김병욱 의원 대표발의) "
              "3. 4ㆍ16세월호참사 피해구제 특별법안(계속) 4. 2002년도예산안")
    assert agenda_laws(agenda, 3) == {
        "은행법", "인터넷전문은행설립및운영에관한특례법", "416세월호참사피해구제특별법"}
    assert agenda_laws("1. 업무보고가. 보건복지부", 3) == set()


def test_law_extract_allows_spaces_and_blocks_longer_names():
    c = CFG.conditions
    ex = Extractor(META, CFG.ingest.name_titles, c.name_suffixes, set(c.name_exclude),
                   laws={"은행법", "인터넷전문은행설립및운영에관한특례법"})
    got = ex.extract("인터넷전문은행 설립 및 운영에 관한 특례법과 은행법 개정안 논의")
    assert got["law"] == ["인터넷전문은행설립및운영에관한특례법", "은행법"]
    assert "law" not in ex.extract("한국은행법 개정")  # 앞에 한글이 붙은 더 긴 이름


def test_doc_values_law_only_when_enabled():
    doc = {"date": "", "questioners": [], "answerers": [],
           "agenda": "1. 소득세법 일부개정법률안(정부 제출)"}
    assert "law" not in doc_values(doc)
    assert doc_values(doc, 3)["law"] == {"소득세법"}
