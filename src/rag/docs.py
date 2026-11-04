"""적재한 문서를 연도 → 회의 → 문서로 찾고 본문을 읽는다(S36, docs/slices/36-doc-browser.md).

시작할 때 메타데이터로 묶음과 파일 위치만 만들고, 본문은 고른 문서만 파일에서 읽는다.
"""

import html
import json
import re
from collections import defaultdict

from rag.index import ROOT, corpus_meta
from rag.speakers import chunk_speakers, render


def doc_name(d: dict) -> str:
    return f"{d['date']} {d['committee_name']} {d['meeting_number']} {d['session_number']}"


def date_key(d: dict) -> tuple[int, ...]:
    """(연, 월, 일). 원천 날짜에 `2018년4월9일(월)`, `2000年6月28日(水)`, 공백이 섞여 있다."""
    return tuple(map(int, re.match(r"(\d{4})\D+(\d+)\D+(\d+)", d["date"]).groups()))


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

    def read(self, doc_id: str) -> dict:
        with self.path.open("rb") as f:
            f.seek(self.offset[doc_id])
            return json.loads(f.readline())


def format_doc(doc: dict, spans: list[dict], mode: str) -> str:
    """문서 화면. 근거와 같은 렌더링으로 발언자 표시를 붙인다. 라벨과 분할 정보는 넣지 않는다."""
    c = {"text": doc["context"]}
    if mode != "off":
        c["speakers"] = chunk_speakers(doc, spans, 0, len(doc["context"]), mode)
    body = html.escape(render(c)).replace("\n", "\n\n")
    return (f"## {html.escape(doc_name(doc))}\n\n{html.escape(doc['agenda'])}\n\n"
            f"[회의록]({doc['original']})\n\n---\n\n{body}")
