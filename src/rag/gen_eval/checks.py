"""생성 답변의 코드 판정(S14, 초안 "코드로 판정하는 항목"). LLM을 쓰지 않는다."""

import re
from difflib import SequenceMatcher

from rag.conditions import DATE, DOC_DATE, committee_base, full_year

CITE = re.compile(r"\[(\d+)\]")
SENT_END = re.compile(r"(?<=[.!?])\s+|\n+")
SPACE = re.compile(r"\s+")


def is_refusal(answer: str, phrase: str) -> bool:
    """프롬프트가 지정한 거부 문구가 답변에 있는가(공백 차이는 무시)."""
    return SPACE.sub("", phrase) in SPACE.sub("", answer)


def sentences(answer: str) -> list[str]:
    """문장 목록. 인용 번호만 남은 조각("[1]")은 앞 문장에 붙인다."""
    out: list[str] = []
    for s in (p.strip() for p in SENT_END.split(answer)):
        if not s:
            continue
        if out and not CITE.sub("", s).strip():
            out[-1] += " " + s
        else:
            out.append(s)
    return out


def citation_check(answer: str, k: int) -> dict:
    """근거 번호 밖 인용([n], n이 1~k 밖)과 인용 없는 문장 수."""
    sents = sentences(answer)
    invalid = sorted({int(n) for n in CITE.findall(answer) if not 1 <= int(n) <= k})
    uncited = sum(1 for s in sents if not CITE.search(s))
    return {"n_sentences": len(sents), "invalid": invalid, "uncited": uncited}


def doc_date(date: str) -> str | None:
    m = DOC_DATE.match(date or "")
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def metadata_mismatches(answer: str, contexts: list[dict], committees: set[str]) -> list[dict]:
    """인용 문장에 나온 회의 일자(연·월·일을 모두 쓴 것)와 위원회 이름이 그 문장이 인용한 근거의
    date·committee_name과 맞지 않는 경우(S14 결정 3). 인용이 없거나 근거 번호 밖이면 보지 않는다."""
    by_n = {c["n"]: c for c in contexts}
    names = sorted(committees, key=len, reverse=True)
    out = []
    for s in sentences(answer):
        cited = [by_n[int(n)] for n in CITE.findall(s) if int(n) in by_n]
        if not cited:
            continue
        dates = {doc_date(c["date"]) for c in cited}
        for y4, y2, mo, d in DATE.findall(s):
            if mo and d:
                got = f"{full_year(y4, y2)}-{int(mo):02d}-{int(d):02d}"
                if got not in dates:
                    out.append({"field": "date", "value": got, "sentence": s})
        bases = {committee_base(c["committee_name"]) for c in cited}
        rest = s
        for name in names:  # 긴 이름부터 찾고 찾은 자리는 지워 짧은 이름이 겹쳐 잡히지 않게 한다
            if name in rest:
                rest = rest.replace(name, " ")
                if name not in bases:
                    out.append({"field": "committee", "value": name, "sentence": s})
    return out


def gold_position(contexts: list[dict], gold_doc: str) -> int | None:
    """정답 문서가 든 근거 번호. 없으면 None(라벨 doc_id 대조)."""
    return next((c["n"] for c in contexts if c["doc_id"] == gold_doc), None)


def answer_overlap(chunk: str, comment: str) -> float:
    """근거 청크가 answer.comment를 담은 정도: 공백을 지운 뒤 가장 긴 공통 부분 문자열 길이 /
    comment 길이(S14 결정 5)."""
    a, b = SPACE.sub("", chunk), SPACE.sub("", comment)
    if not b:
        return 0.0
    if b in a:
        return 1.0
    m = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size / len(b)
