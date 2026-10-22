"""질의 텍스트에서 회의를 지목하는 조건을 규칙·사전으로 뽑는다(S11, D-19).

입력은 질의 텍스트와 값 사전(rag.meta_dict)뿐이다. 정답·qid는 쓰지 않는다(protocol-guard P9).
출력 값은 doc_values와 같은 형식이라 H14가 문서 값과 그대로 비교한다.
규칙은 docs/slices/11-query-conditions.md, 표기 차이는 docs/slices/11b-condition-variants.md.
"""

import json
import re
import sys
from collections import Counter
from functools import cache

from rag.index import ROOT, corpus_meta, load_cfg
from rag.meta_dict import build as build_meta_dict

# `YYYY년도`는 회계연도라 회의 날짜가 아니다(D-21). 두 자리 연도는 `'YY년`만 날짜로 본다(D-22)
DATE = re.compile(
    r"(?<!\d)(?:(\d{4})|'(\d{2}))\s*년(?!도)(?:\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?)?"
)
# 회의 연도와 어긋날 수 있는 연도 언급(`2019년도 예산안`, `2018회계연도`, `'19년도`).
# date와 따로 둔다(D-22)
YEAR_REF = re.compile(r"(?<!\d)(?:(\d{4})|'?(\d{2}))\s*(?:회계\s*)?[년연]도")
DOC_DATE = re.compile(r"(\d{4})[년年](\d{1,2})[월月](\d{1,2})[일日]")
GENERATION = re.compile(r"(?:제\s*)?(\d{1,2})\s*대\s*국회")
# 코퍼스 회기 번호는 세 자리(180~402)다. `제1회 추가경정예산` 같은 다른 `제N회`를 막는다(D-21)
MEETING_NUMBER = re.compile(r"제\s*(\d{3})\s*회(?!의)")
SESSION_NUMBER = re.compile(r"제\s*(\d+)\s*차(?!관)")  # 제1차관(직위)은 차수가 아니다
# 안건 항목의 법률명(EXP-008): `○○법 일부개정법률안`, `○○법안`의 `○○법`. 안건은 회의 단위 필드다
AGENDA_ITEM = re.compile(r"(?:^|\s)\d+\.\s*")
AGENDA_LAW = re.compile(r"([가-힣A-Za-z0-9ㆍ·․‧\s]+?법)\s*(?:일부|전부)?\s*(?:개정)?\s*(?:법률)?안")
SUB_ITEM = re.compile(r"^[가-힣]\.")  # `가.` 같은 하위 항목 번호
LAW_SEP = r"[\sㆍ·․‧]"  # 법률명 안에서 무시하는 공백·가운뎃점


@cache
def agenda_laws(agenda: str, min_chars: int) -> frozenset[str]:
    """안건 문자열의 법률명. 공백·가운뎃점을 지운 형태로, min_chars자 미만은 버린다.

    같은 회의의 문서는 안건이 같아(문서 38,516개, 안건 5,822개) 결과를 기억한다. 조건 색인과
    추출기가 같은 집합을 받으므로 고칠 수 없는 frozenset으로 돌려준다(S20).

    Args:
        agenda: 문서의 `agenda` 필드.
        min_chars: 법률명 최소 글자 수.

    Returns:
        법률명 집합.
    """
    out = set()
    for item in AGENDA_ITEM.split(agenda):
        for m in AGENDA_LAW.finditer(item):
            name = SUB_ITEM.sub("", re.sub(LAW_SEP, "", m.group(1)))
            if len(name) >= min_chars:
                out.add(name)
    return frozenset(out)


def full_year(y4, y2) -> str:
    """두 자리 연도는 30 이하면 20YY, 아니면 19YY다. 코퍼스 회의 연도는 1996~2023이다(D-22)."""
    return y4 or (f"20{y2}" if int(y2) <= 30 else f"19{y2}")


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
    def __init__(self, meta_dict: dict, titles, suffixes, exclude=(), aliases=None, laws=()):
        committees = {committee_base(c) for c in meta_dict["committee_name"]}
        # 약칭: `국방위원회` → `국방위`, 그리고 공식·관용 약칭 표(D-22)
        self.committee_of = {c: [c] for c in committees}
        self.committee_of |= {c[:-2]: [c] for c in committees if c.endswith("위원회")}
        self.committee_of |= {a: list(names) for a, names in (aliases or {}).items()}
        self.committee = alternation(self.committee_of)
        self.meeting = alternation(meta_dict["meeting_name"])
        tail = "|".join(re.escape(t) for t in sorted([*titles, *suffixes], key=len, reverse=True))
        # 사전 이름 칸에 섞인 이름이 아닌 값(`위원`, `통일부장관`, `000` 등)을 뺀다(D-21)
        kept = [n for n in meta_dict["name"]
                if re.fullmatch("[가-힣]+", n) and not n.endswith(tuple(titles))
                and n not in exclude]
        names = "|".join(re.escape(n) for n in sorted(kept, key=len, reverse=True))
        self.name = re.compile(f"(?<![가-힣])({names})(?=$|[^가-힣]|{tail})")
        # 법률명은 글자 사이 공백·가운뎃점을 허용해 찾는다. 긴 이름을 먼저 맞춘다(EXP-008)
        pats = [f"{LAW_SEP}*".join(map(re.escape, n)) for n in sorted(laws, key=len, reverse=True)]
        self.law = re.compile(f"(?<![가-힣])(?:{'|'.join(pats)})") if pats else None

    def extract(self, text: str) -> dict[str, list[str]]:
        found = {
            "date": [date_keys(full_year(y4, y2), mo, d)[-1]
                     for y4, y2, mo, d in DATE.findall(text)],
            "year_ref": [full_year(y4, y2) for y4, y2 in YEAR_REF.findall(text)],
            "generation_number": [m.group(1) for m in GENERATION.finditer(text)],
            "meeting_number": [f"제{m.group(1)}회" for m in MEETING_NUMBER.finditer(text)],
            "session_number": [f"제{m.group(1)}차" for m in SESSION_NUMBER.finditer(text)],
            "committee_name": [c for m in self.committee.finditer(text)
                               for c in self.committee_of[m.group()]],
            "meeting_name": [m.group() for m in self.meeting.finditer(text)],
            "names": [m.group(1) for m in self.name.finditer(text)],
            "law": [re.sub(LAW_SEP, "", m.group()) for m in self.law.finditer(text)]
            if self.law else [],
        }
        return {k: list(dict.fromkeys(v)) for k, v in found.items() if v}


def doc_values(doc: dict, law_min_chars: int | None = None) -> dict[str, set[str] | frozenset[str]]:
    """문서 하나에서 조건 필드마다 맞는 값의 집합. 날짜는 연·연-월·연-월-일을 모두 담는다.

    law_min_chars가 있으면 안건 항목의 법률명을 `law` 필드로 더한다(EXP-008).
    """
    m = DOC_DATE.match(doc.get("date", ""))
    names = {p["name"] for f in ("questioners", "answerers") for p in doc[f]} - {""}
    committee = doc.get("committee_name", "")
    values = {
        "date": set(date_keys(*m.groups())) if m else set(),
        "generation_number": {doc.get("generation_number", "")},
        "meeting_number": {doc.get("meeting_number", "")},
        "session_number": {doc.get("session_number", "")},
        "committee_name": {committee, committee_base(committee)},
        "meeting_name": {doc.get("meeting_name", "")},
        "names": names,
    }
    if law_min_chars is not None:
        values["law"] = agenda_laws(doc.get("agenda", ""), law_min_chars)
    return values


class ConditionIndex:
    """문서 값의 역색인. 질의 조건에 맞는 필드 수를 문서마다 센다(H14, EXP-003)."""

    def __init__(self, docs: list[dict], year_ref_offsets, law_min_chars: int | None = None):
        self.offsets = year_ref_offsets
        self.index: dict[str, dict[str, set[int]]] = {}  # 필드 → 값 → 문서 번호
        for i, doc in enumerate(docs):
            for field, values in doc_values(doc, law_min_chars).items():
                for v in values - {""}:
                    self.index.setdefault(field, {}).setdefault(v, set()).add(i)

    def match_counts(self, conditions: dict[str, list[str]]) -> Counter:
        """필드 안에서는 질의 값 중 하나라도 맞으면 그 필드가 맞는다.

        `year_ref` Y는 회의 연도 Y+offset(예산안 Y-1, 집행 Y, 결산 Y+1)과 맞춘다.
        """
        counts = Counter()
        for field, values in conditions.items():
            if field == "year_ref":
                field = "date"
                values = [str(int(y) + o) for y in values for o in self.offsets]
            by_value = self.index.get(field, {})
            counts.update(set().union(*(by_value.get(v, set()) for v in values)))
        return counts


def read_queries(cfg) -> list[dict]:
    """세트의 qid·query만 읽는다. summary_q는 dev 질의 파일이다(test는 읽지 않는다)."""
    path = cfg.paths.multidoc_frozen if cfg.search.queries == "multidoc" else cfg.paths.queries_dev
    with (ROOT / path).open(encoding="utf-8") as f:
        return [{"qid": q["qid"], "query": q["query"]} for q in map(json.loads, f)]


def build_extractor(cfg) -> Extractor:
    """config와 코퍼스로 추출기를 만든다. rag.conditions·rag.search·rag.generate가 같이 쓴다.

    값 사전(rag.meta_dict와 같은 규칙)과 법률명은 실행할 때 코퍼스를 한 번 읽어 만든다.
    미리 만든 파일(paths.meta_dict)을 읽으면 코퍼스를 다시 적재한 뒤 옛 사전이 조용히 쓰인다(S12).
    """
    c = cfg.conditions
    laws = set()
    # 문서마다 OmegaConf 값을 읽으면 그것만 수 초가 걸려 반복문 전에 한 번 읽는다(S20)
    law_min = c.law_min_chars if c.get("agenda_law") else None

    def docs():
        for doc in corpus_meta(cfg):  # 조건 색인과 같이 한 번만 읽는다(S17)
            if law_min is not None:  # 법률명 사전은 코퍼스 안건에서만 만든다(EXP-008)
                laws.update(agenda_laws(doc.get("agenda", ""), law_min))
            yield doc

    meta_dict = build_meta_dict(docs())
    return Extractor(meta_dict, cfg.ingest.name_titles, c.name_suffixes, set(c.name_exclude),
                     c.committee_aliases, laws)


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    ex = build_extractor(cfg)
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
