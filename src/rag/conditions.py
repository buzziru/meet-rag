"""질의 텍스트에서 회의를 지목하는 조건을 규칙·사전으로 뽑는다(S11, D-19).

입력은 질의 텍스트와 값 사전(rag.meta_dict)뿐이다. 정답·qid는 쓰지 않는다(protocol-guard P9).
출력 값은 doc_values와 같은 형식이라 H14가 문서 값과 그대로 비교한다.
규칙은 docs/slices/11-query-conditions.md.
"""

import json
import re
import sys

from rag.index import ROOT, load_cfg

DATE = re.compile(r"(\d{4})\s*년(?:\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?)?")
DOC_DATE = re.compile(r"(\d{4})[년年](\d{1,2})[월月](\d{1,2})[일日]")
GENERATION = re.compile(r"(?:제\s*)?(\d{1,2})\s*대\s*국회")
MEETING_NUMBER = re.compile(r"제\s*(\d+)\s*회(?!의)")
SESSION_NUMBER = re.compile(r"제\s*(\d+)\s*차(?!관)")  # 제1차관(직위)은 차수가 아니다


def date_keys(year, month=None, day=None) -> list[str]:
    """연, 연-월, 연-월-일 중 주어진 정밀도까지의 키. 질의는 가장 정밀한 키 하나를 쓴다."""
    keys = [year]
    if month:
        keys.append(f"{year}-{int(month):02d}")
        if day:
            keys.append(f"{year}-{int(month):02d}-{int(day):02d}")
    return keys


def committee_base(name: str) -> str:
    """국정감사 반 표기(`국방위원회-제1반`)를 뗀 위원회 이름."""
    return name.split("-")[0]


def alternation(values) -> re.Pattern:
    """긴 값부터 시도하는 정규식. 같은 위치에서 긴 값이 이기고 겹친 짧은 값은 버려진다."""
    return re.compile("|".join(re.escape(v) for v in sorted(values, key=len, reverse=True)))


class Extractor:
    def __init__(self, meta_dict: dict, titles, suffixes):
        committees = {committee_base(c) for c in meta_dict["committee_name"]}
        # 약칭: `국방위원회` → `국방위`
        self.committee_of = {c: c for c in committees}
        self.committee_of |= {c[:-2]: c for c in committees if c.endswith("위원회")}
        self.committee = alternation(self.committee_of)
        self.meeting = alternation(meta_dict["meeting_name"])
        tail = "|".join(re.escape(t) for t in sorted([*titles, *suffixes], key=len, reverse=True))
        names = "|".join(re.escape(n) for n in sorted(meta_dict["name"], key=len, reverse=True))
        self.name = re.compile(f"(?<![가-힣])({names})(?=$|[^가-힣]|{tail})")

    def extract(self, text: str) -> dict[str, list[str]]:
        found = {
            "date": [date_keys(*m.groups())[-1] for m in DATE.finditer(text)],
            "generation_number": [m.group(1) for m in GENERATION.finditer(text)],
            "meeting_number": [f"제{m.group(1)}회" for m in MEETING_NUMBER.finditer(text)],
            "session_number": [f"제{m.group(1)}차" for m in SESSION_NUMBER.finditer(text)],
            "committee_name": [self.committee_of[m.group()] for m in self.committee.finditer(text)],
            "meeting_name": [m.group() for m in self.meeting.finditer(text)],
            "names": [m.group(1) for m in self.name.finditer(text)],
        }
        return {k: list(dict.fromkeys(v)) for k, v in found.items() if v}


def doc_values(doc: dict) -> dict[str, set[str]]:
    """문서 하나에서 조건 필드마다 맞는 값의 집합. 날짜는 연·연-월·연-월-일을 모두 담는다."""
    m = DOC_DATE.match(doc.get("date", ""))
    names = {p["name"] for f in ("questioners", "answerers") for p in doc[f]} - {""}
    committee = doc.get("committee_name", "")
    return {
        "date": set(date_keys(*m.groups())) if m else set(),
        "generation_number": {doc.get("generation_number", "")},
        "meeting_number": {doc.get("meeting_number", "")},
        "session_number": {doc.get("session_number", "")},
        "committee_name": {committee, committee_base(committee)},
        "meeting_name": {doc.get("meeting_name", "")},
        "names": names,
    }


def read_queries(cfg) -> list[dict]:
    """세트의 qid·query만 읽는다. summary_q는 dev 질의 파일이다(test는 읽지 않는다)."""
    path = cfg.paths.multidoc_frozen if cfg.search.queries == "multidoc" else cfg.paths.queries_dev
    with (ROOT / path).open(encoding="utf-8") as f:
        return [{"qid": q["qid"], "query": q["query"]} for q in map(json.loads, f)]


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    meta_dict = json.loads((ROOT / cfg.paths.meta_dict).read_text(encoding="utf-8"))
    ex = Extractor(meta_dict, cfg.ingest.name_titles, cfg.conditions.name_suffixes)
    out = ROOT / cfg.paths.conditions
    out.parent.mkdir(parents=True, exist_ok=True)
    queries = read_queries(cfg)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for q in queries:
            row = {"qid": q["qid"], "conditions": ex.extract(q["query"])}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(queries):,} queries -> {cfg.paths.conditions}")


if __name__ == "__main__":
    main()
