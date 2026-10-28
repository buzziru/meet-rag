"""근거 청크의 발언자 정보(S29, docs/slices/29-speakers.md).

원천 데이터는 회의록 전문이 아니라 질의·답변 2행이라(docs/data.md §5) 본문 전체의 발언별 발언자는
없다. 붙일 수 있는 것은 문서의 화자 목록(corpus의 questioners·answerers)과, 라벨의 질의·답변 발언이
본문에서 차지하는 구간이다. 구간은 실행할 때 원천 라벨에서 만든다(6.9초). 라벨의 질의 텍스트
(summary_q)는 읽지 않는다(사용자 결정 2026-10-28, 결정 사항 2).

uv run python -m rag.speakers [--gen <생성 기록.jsonl>]: 채움 비율과 발언 일치 수, 생성 기록을 주면
그 근거에 붙는 겹침 표지 수를 출력한다. 파일은 쓰지 않는다.
"""

import argparse
import json
from collections import Counter
from collections.abc import Iterable

from rag.index import ROOT, corpus_meta, load_cfg
from rag.ingest import SPEAKER_KEYS, iter_labels, make_doc_id, speaker

ROLES = {"question": "questioner", "answer": "answerer"}  # 라벨 발언 키 → 화자 키 접두사


def doc_spans(records: Iterable[tuple[str, dict]],
              titles: tuple[str, ...]) -> dict[str, list[dict]]:
    """원천 라벨에서 문서별 발언 구간. 구간의 화자는 그 발언이 나온 QA의 화자다(ingest 정규화).

    발언이 본문에 여러 번 나오면 모든 위치를 둔다(어느 위치인지 라벨에 없다). 본문에 그대로 없는
    발언은 구간이 없다. 같은 역할·화자·위치는 한 번만 둔다.
    """
    out = {}
    for _, r in records:
        spans = out.setdefault(make_doc_id(r["conference_number"], r["context"]), [])
        for role, prefix in ROLES.items():
            text = r[role]["comment"]
            person = speaker(r, prefix, titles)
            i = r["context"].find(text) if text else -1
            while i >= 0:
                span = {"role": role, "start": i, "end": i + len(text), **person}
                if span not in spans:
                    spans.append(span)
                i = r["context"].find(text, i + 1)
    for spans in out.values():
        spans.sort(key=lambda s: (s["start"], s["end"], s["role"]))
    return out


def chunk_speakers(doc: dict, spans: list[dict], start: int, end: int, mode: str) -> dict:
    """청크 [start, end)의 speakers 필드. head는 문서 화자 목록만, marks는 청크 안 발언 구간도 둔다.

    구간 위치는 청크 text 안의 문자 위치이고, 청크 경계에 걸린 구간은 청크 안 부분만 남긴다.
    """
    out = {"questioners": doc["questioners"], "answerers": doc["answerers"]}
    if mode == "marks":
        out["spans"] = [{**s, "start": max(s["start"], start) - start,
                         "end": min(s["end"], end) - start}
                        for s in spans if s["start"] < end and s["end"] > start]
    return out


def fill_counts(docs: Iterable[dict]) -> Counter:
    """화자 필드가 채워진 문서 수(역할·키별)와 화자가 둘 이상인 문서 수."""
    c = Counter()
    for d in docs:
        c["docs"] += 1
        for field in ("questioners", "answerers"):
            people = d[field]
            c[f"{field}.any"] += bool(people)
            c[f"{field}.multi"] += len(people) > 1
            for k in SPEAKER_KEYS:
                c[f"{field}.{k}"] += any(p[k] for p in people)
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description="발언자 정보 채움 비율과 겹침 표지 수")
    ap.add_argument("--gen", help="생성 기록(jsonl). 근거마다 겹침 표지가 붙는지 센다")
    args = ap.parse_args()
    cfg = load_cfg()
    docs = corpus_meta(cfg)
    n = len(docs)
    for k, v in sorted(fill_counts(docs).items()):
        print(f"{k}\t{v}\t{v / n:.4f}")

    contexts, found = {}, Counter()

    def counted():
        """발언이 본문에 그대로 있는 QA 수를 세며 라벨을 넘긴다. --gen이면 본문을 남긴다."""
        for split, r in iter_labels(ROOT / cfg.paths.raw_dir):
            for role in ROLES:
                found[f"{role}.qa"] += 1
                found[f"{role}.found"] += r[role]["comment"] in r["context"]
                found[f"{role}.repeat"] += r["context"].count(r[role]["comment"]) > 1
            if args.gen:
                contexts[make_doc_id(r["conference_number"], r["context"])] = r["context"]
            yield split, r

    spans = doc_spans(counted(), tuple(cfg.ingest.name_titles))
    for k, v in sorted(found.items()):
        print(f"{k}\t{v}")
    if not args.gen:
        return

    c = Counter()
    with open(args.gen, encoding="utf-8") as f:
        for g in map(json.loads, f):
            c["queries"] += 1
            for ctx in g["contexts"]:
                start = contexts[ctx["doc_id"]].find(ctx["text"])
                if start < 0:
                    raise SystemExit(f"근거 text가 문서 본문에 없다: {g['qid']} {ctx['doc_id']}")
                got = chunk_speakers({"questioners": [], "answerers": []}, spans[ctx["doc_id"]],
                                     start, start + len(ctx["text"]), "marks")["spans"]
                marked = set()
                for s in got:
                    marked.update(range(s["start"], s["end"]))
                c["contexts"] += 1
                c["contexts_marked"] += bool(got)
                c["chars"] += len(ctx["text"])
                c["chars_marked"] += len(marked)
    print(f"질의 {c['queries']}개, 근거 {c['contexts']}개 중 표지 있음 {c['contexts_marked']}"
          f"({c['contexts_marked'] / c['contexts']:.3f}), "
          f"표지 문자 비율 {c['chars_marked'] / c['chars']:.3f}")


if __name__ == "__main__":
    main()
