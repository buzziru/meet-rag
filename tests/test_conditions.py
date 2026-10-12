import pytest

from rag.conditions import Extractor, doc_values
from rag.index import load_cfg

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
