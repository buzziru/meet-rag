"""적재한 문서를 연도 → 회의 → 문서로 찾고 본문을 읽는다(S36, docs/slices/36-doc-browser.md).

시작할 때 메타데이터로 묶음과 파일 위치만 만들고, 본문은 고른 문서만 파일에서 읽는다.
"""

import html
import json
import re
from collections import defaultdict

from rag.index import ROOT, corpus_meta
from rag.speakers import chunk_speakers, render

# 근거 청크 자리를 본문에 잠시 표시하는 사용자 영역 문자. 회의록 본문에는 나오지 않는다
CHUNK_START, CHUNK_END = "", ""


def doc_name(d: dict) -> str:
    return f"{d['date']} {d['committee_name']} {d['meeting_number']} {d['session_number']}"


def date_key(d: dict) -> tuple[int, ...]:
    """(연, 월, 일). 원천 날짜에 `2018년4월9일(월)`, `2000年6月28日(水)`, 공백이 섞여 있다."""
    return tuple(map(int, re.match(r"(\d{4})\D+(\d+)\D+(\d+)", d["date"]).groups()))


def readable(rendered: str) -> str:
    """render 결과를 화면용 문단으로 나눈다. 본문에 줄바꿈과 화자 구분이 없어, 발언 표지와 원천의
    연속 공백에서만 나눌 수 있다. HTML로 해석되지 않게 한다. 모델 입력은 render 그대로다."""
    text = re.sub(r"〈/(?:질의|답변)〉", "\n\n", html.escape(rendered))
    text = re.sub(r"〈(?:질의|답변)[^〉]*〉", lambda m: f"\n\n**{m.group(0)}**\n\n", text)
    text = re.sub(r" {2,}", "\n\n", text).replace("\n", "\n\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class Corpus:
    def __init__(self, cfg):
        self.path = ROOT / cfg.paths.corpus
        meta = corpus_meta(cfg)
        with self.path.open("rb") as f:
            offsets = [f.tell()]
            while f.readline():
                offsets.append(f.tell())
        self.offset = {d["doc_id"]: o for d, o in zip(meta, offsets, strict=False)}
        self.docs: dict[str, list[dict]] = defaultdict(list)
        for d in meta:
            self.docs[d["conference_number"]].append(d)
        by_year = defaultdict(list)
        for conf, docs in self.docs.items():
            by_year[date_key(docs[0])[0]].append(conf)
        self.meetings_by_year = {
            y: sorted(confs, key=lambda c: (date_key(self.docs[c][0]), c), reverse=True)
            for y, confs in by_year.items()}

    def years(self) -> list[int]:
        return sorted(self.meetings_by_year, reverse=True)

    def meetings(self, year: int) -> list[tuple[str, str]]:
        """(이름, 회의 번호). 날짜·위원회·회차·차수까지 같은 회의는 번호를 붙여 구별한다."""
        confs = self.meetings_by_year[year]
        names = [doc_name(self.docs[c][0]) for c in confs]
        return [(f"{n} ({c})" if names.count(n) > 1 else n, c) for n, c in zip(names, confs,
                                                                             strict=True)]

    def documents(self, conf: str) -> list[tuple[str, str]]:
        """(이름, 문서 번호). 같은 회의의 문서는 이름이 같아 순번으로 구별한다."""
        docs = self.docs[conf]
        return [(doc_name(d) if len(docs) == 1 else f"{doc_name(d)} #{i}", d["doc_id"])
                for i, d in enumerate(docs, 1)]

    def chunk_span(self, doc_id: str, text: str) -> tuple[int, int] | None:
        """근거 청크의 문서 안 위치. 근거 탭에서 그 자리를 표시한다. 찾지 못하면 None."""
        start = self.read(doc_id)["context"].find(text)
        return (start, start + len(text)) if start >= 0 else None

    def read(self, doc_id: str) -> dict:
        with self.path.open("rb") as f:
            f.seek(self.offset[doc_id])
            return json.loads(f.readline())


def format_doc(doc: dict, spans: list[dict], mode: str,
               chunk: tuple[int, int] | None = None, marks: tuple[str, str] = ("", "")) -> str:
    """문서 화면. 근거와 같은 렌더링으로 발언자 표시를 붙인다. 라벨과 분할 정보는 넣지 않는다.
    chunk를 주면 그 구간의 앞뒤에 marks를 보인다(근거 탭). 발언 구간도 그만큼 밀어 위치를 맞춘다."""
    text = doc["context"]
    if chunk:
        start, end = chunk
        text = f"{text[:start]}{CHUNK_START}{text[start:end]}{CHUNK_END}{text[end:]}"
        shift = lambda at: at + (at >= start) + (at >= end)  # noqa: E731
        spans = [{**s, "start": shift(s["start"]), "end": shift(s["end"])} for s in spans]
    c = {"text": text}
    if mode != "off":
        c["speakers"] = chunk_speakers(doc, spans, 0, len(text), mode)
    body = readable(render(c)).replace(CHUNK_START, f"\n\n**{marks[0]}**\n\n")
    body = body.replace(CHUNK_END, f"\n\n**{marks[1]}**\n\n")
    return (f"## {html.escape(doc_name(doc))}\n\n{html.escape(doc['agenda'])}\n\n"
            f"[회의록]({doc['original']})\n\n---\n\n{body}")
