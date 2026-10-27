"""생성 답변의 코드 판정(S14, 초안 "코드로 판정하는 항목"). LLM을 쓰지 않는다."""

import re

from rag.conditions import DATE, DOC_DATE, committee_base, full_year

CITE = re.compile(r"\[(\d+)\]")
SENT_END = re.compile(r"(?<=[.!?])\s+|\n+")
SPACE = re.compile(r"\s+")
LIST_MARK = re.compile(r"^(?:\d+[.)]|[-*•·])$")  # 목록 번호·기호만 남은 조각


def refusal_split(answer: str, phrase: str,
                  fillers: list[str]) -> tuple[str | None, list[str], str]:
    """(거부 종류, 거부 문장, 거부 문장을 뺀 답변). 거부 문장은 프롬프트가 지정한 거부 문구를
    담은 문장이다(공백 차이는 무시). 내용 문장(거부 문장도, fillers 문구가 든 문장도 아닌 문장)이
    없으면 "full", 있으면 "partial", 거부 문장이 없으면 None이고 답변을 그대로 돌려준다(S14b)."""
    key = SPACE.sub("", phrase)
    sents = sentences(answer)
    refused = [s for s in sents if key in SPACE.sub("", s)]
    if not refused:
        return None, [], answer
    rest = [s for s in sents if s not in refused]
    content = [s for s in rest if not any(f in s for f in fillers)]
    return ("partial" if content else "full"), refused, "\n".join(rest)


def unlisted_refusal(answer: str, phrase: str, parts: list[str]) -> bool:
    """지정 거부 문구 없이 거부한 문장이 있는가. 조각(parts)이 모두 들고 거부 문구는 없는
    문장이다(공백 차이는 무시). refusal_split은 이 문장을 내용 문장으로 본다(이슈 #156)."""
    key, parts = SPACE.sub("", phrase), [SPACE.sub("", p) for p in parts]
    flat = (SPACE.sub("", s) for s in sentences(answer))
    return any(key not in s and all(p in s for p in parts) for s in flat)


def sentences(answer: str) -> list[str]:
    """문장 목록. 인용 번호만 남은 조각("[1]")은 앞 문장에, 목록 번호만 남은 조각("1.")은
    뒤 문장에 붙인다."""
    out: list[str] = []
    mark = ""
    for s in (p.strip() for p in SENT_END.split(answer)):
        if not s:
            continue
        if out and not CITE.sub("", s).strip():
            out[-1] += " " + s
        elif LIST_MARK.match(s):
            mark += s + " "
        else:
            out.append(mark + s)
            mark = ""
    return out


def citation_check(answer: str, k: int, fillers: list[str]) -> dict:
    """근거 번호 밖 인용([n], n이 1~k 밖)과 인용 없는 문장 수.

    fillers 문구가 든 문장(인사말, "다음과 같습니다" 같은 도입 문장)은 내용이 없어 문장 수와
    인용 없는 문장에서 빼고 filler로 따로 센다(PR #106 코멘트, 2026-10-20)."""
    sents = sentences(answer)
    filler = [s for s in sents if any(f in s for f in fillers)]
    body = [s for s in sents if s not in filler]
    invalid = sorted({int(n) for n in CITE.findall(answer) if not 1 <= int(n) <= k})
    uncited = sum(1 for s in body if not CITE.search(s))
    return {"n_sentences": len(body), "invalid": invalid, "uncited": uncited,
            "filler": len(filler)}


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


STATES = ("있음", "일부", "없음", "모호", "회피")
HANDLINGS = ("답함", "부분임을 밝히고 답함", "상황을 밝히고 답함", "거부", "다루지 않음")
# (정보 상태, 처리) → 판정. 있음·일부·없음의 맞는 처리는 하나씩이고(D-41 결정 2), 틀린 처리는
# 유형을 나눠 센다(S14c 결정 사항 2 (a)). 모호·회피는 거부 정확도에서 빼고, 예정·검토 중·답을
# 피함 같은 상황을 밝혔으면 상황 전달, 아니면 상황 미전달로 센다(D-41 결정 3, S14c 결정 사항 4).
# 있음·일부·없음에 "상황을 밝히고 답함"이 나오면 "답함"과 같게 본다
SITUATION = ("모호", "회피")
OUTCOMES = {
    ("있음", "답함"): "맞음",
    ("있음", "부분임을 밝히고 답함"): "불필요한 부분 안내",
    ("있음", "거부"): "과잉 거부",
    ("있음", "다루지 않음"): "누락",
    ("일부", "답함"): "안내 없이 부분 답함",
    ("일부", "부분임을 밝히고 답함"): "맞음",
    ("일부", "거부"): "과잉 거부",
    ("일부", "다루지 않음"): "누락",
    ("없음", "답함"): "근거 없이 답함",
    ("없음", "부분임을 밝히고 답함"): "근거 없이 답함",
    ("없음", "거부"): "맞음",
    ("없음", "다루지 않음"): "무언 생략",
}


def item_outcome(state: str, handling: str) -> str:
    """질의 항목 하나의 판정. 값은 STATES·HANDLINGS 안이어야 한다(judge 출력 확인 뒤 부른다)."""
    if state in SITUATION:
        return "상황 전달" if handling == "상황을 밝히고 답함" else "상황 미전달"
    return OUTCOMES[state, "답함" if handling == "상황을 밝히고 답함" else handling]


def item_counts(items: list[dict]) -> dict:
    """질의 하나의 항목 판정 수(기준 문서 I13). 판정 대상은 모호·회피를 뺀 항목이다. 설정 비교는
    회의 단위 paired bootstrap이라 질의 단위 값이 필요하다."""
    outcomes = [i["outcome"] for i in items]
    return {"correct": outcomes.count("맞음"),
            "judged": sum(1 for i in items if i["state"] not in SITUATION),
            "over_refusal": outcomes.count("과잉 거부"),
            "unsupported": outcomes.count("근거 없이 답함")}
