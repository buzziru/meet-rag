"""채팅 API. 자유 질의를 검색해 답변을 스트리밍으로 보내고 끝나면 근거를 붙인다. 화면은 Vercel
페이지가 맡고 여기에는 화면이 없다(S48, D-88 결정 2).

명세는 docs/slices/35-chat-app.md. 실시간 재정렬은 Space 진입점이 GPU 점수 함수를 넘길 때만 켠다
(S39). 로컬에는 GPU가 없어 재정렬을 끈 구성으로 시작한다. 방문자 질의는 data/에 저장하지 않고
LangSmith 추적으로만 남는다.
"""

import html
import logging
import sys
import time
from collections.abc import Callable, Iterator
from datetime import date

from langsmith.run_trees import configure

from rag.display import MeetingInfoMover, move_meeting_info
from rag.docs import Corpus, doc_body, doc_name, readable
from rag.generate import Pipeline, recipe
from rag.index import load_cfg
from rag.speakers import render


class TracingSwitch(logging.Handler):
    """LangSmith 월 한도를 넘으면 추적을 끄고 다음 달에 다시 켠다(D-71 자동화). 전송 실패는
    클라이언트 경고 로그로만 알 수 있어 로그를 본다. 끈 상태는 저장하지 않는다. 재시작하면 켠
    상태로 시작하고, 아직 한도를 넘었으면 첫 전송 실패로 다시 꺼진다."""

    LIMIT = "Rate limit exceeded"

    def __init__(self, today: Callable[[], date] = date.today):
        super().__init__(logging.WARNING)
        self.today = today
        self.off_month = None

    def month(self) -> tuple[int, int]:
        d = self.today()
        return d.year, d.month

    def emit(self, record: logging.LogRecord) -> None:
        if self.off_month is None and self.LIMIT in record.getMessage():
            self.off_month = self.month()
            configure(enabled=False)
            print("LangSmith 한도 초과로 추적을 끈다. 다음 달에 다시 켠다", flush=True)

    def refresh(self) -> None:
        if self.off_month is not None and self.off_month != self.month():
            self.off_month = None
            configure(enabled=True)
            print("달이 바뀌어 LangSmith 추적을 다시 켠다", flush=True)


TRACING = TracingSwitch()


def search_query(message: str, history: list[dict]) -> str:
    """검색에 쓸 질의. 지금은 싱글턴이라 이력을 쓰지 않는다. 멀티턴은 여기서 이력으로 재작성한다."""
    return message


def shown(stream: Iterator[str | dict], max_name: int) -> Iterator[str | dict]:
    """pipe.stream의 답변을 화면 글로 바꾼다(S45). 생성 결과와 추적에는 원문이 남는다. 잡아 둔
    동안은 내보내지 않고, 첫 원문 조각과 첫 표시 글자 사이의 시간을 로그에 남긴다."""
    mover = MeetingInfoMover(max_name)
    raw_at = None
    logged = False
    for item in stream:
        if isinstance(item, dict):
            out = {**item, "answer": move_meeting_info(item["answer"], max_name)}
        else:
            raw_at = raw_at or time.perf_counter()
            out = mover.feed(item)
        if out:
            if raw_at and not logged:
                print(f"첫 글자 지연: {time.perf_counter() - raw_at:.3f}초", flush=True)
                logged = True
            yield out


def context_payload(c: dict, corpus) -> dict:
    """정적 페이지(S39b)에 주는 근거 하나. 값을 골라 내 라벨·분할 정보가 나가지 않는다. 본문은
    페이지가 글자로 넣으므로 이스케이프를 푼다."""
    start, end = corpus.chunk_span(c["doc_id"], c["text"]) or (-1, -1)
    return {"n": c["n"], "date": c["date"], "committee_name": c["committee_name"],
            "original": c["original"], "doc_id": c["doc_id"], "start": start, "end": end,
            "body": html.unescape(readable(render(c)))}


def chat_events(pipe, cfg, rec: dict, corpus, message: str) -> Iterator[dict]:
    """정적 페이지의 채팅. 지금까지의 답변을 조각마다 보내고 마지막에 근거를 붙인다. API를 직접
    불러 빈 질문을 보내면 생성을 부르지 않는다."""
    if not message.strip():
        return
    if len(message) > cfg.app.max_query_chars:  # 검색과 유료 생성을 부르지 않는다(S49)
        yield {"text": cfg.app.query_too_long, "done": True, "contexts": []}
        return
    TRACING.refresh()
    query = search_query(message, [])
    text = ""
    stream = pipe.stream(query, pipe.embed(query), langsmith_extra={"metadata": rec})
    for item in shown(stream, cfg.app.meeting_info_max_name):
        if isinstance(item, dict):
            yield {"text": item["answer"] or cfg.app.no_answer, "done": True,
                   "contexts": [context_payload(c, corpus) for c in item["contexts"]]}
        else:
            text += item
            yield {"text": text, "done": False}


def doc_payload(pipe, cfg, corpus, doc_id: str, start: int, end: int) -> dict:
    """정적 페이지의 문서 한 건. start가 음수면 근거 위치 표시를 하지 않는다."""
    doc = corpus.read(doc_id)
    labels = cfg.app.labels
    spans = pipe.spans.get(doc_id, []) if pipe.speakers != "off" else []
    body = doc_body(doc, spans, pipe.speakers, (start, end) if start >= 0 else None,
                    (labels.chunk_start, labels.chunk_end))
    return {"name": doc_name(doc), "agenda": doc["agenda"], "original": doc["original"],
            "body": html.unescape(body)}


def build(cfg, pipe, corpus, endpoint: Callable | None = None):
    """API만 여는 Blocks를 만든다. 평가·실험 환경에는 gradio가 없어 여기서 불러온다(pyproject의
    app). endpoint는 Space의 GPU 점수 함수로, 토큰 호출에 쓰도록 API 문서에 보이지 않는 경로로
    연다(S39, D-74)."""
    import gradio as gr

    rec = recipe(cfg, pipe.index_meta, True)
    api = {"api_visibility": "undocumented"}

    def chat(message: str) -> Iterator[dict]:
        yield from chat_events(pipe, cfg, rec, corpus, message)

    def years() -> list[int]:
        return corpus.years()

    def meetings(year: int) -> list[list[str]]:
        return [list(m) for m in corpus.meetings(year)]

    def documents(conference: str) -> list[list[str]]:
        return [list(d) for d in corpus.documents(conference)]

    def document(doc_id: str, start: int, end: int) -> dict:
        return doc_payload(pipe, cfg, corpus, doc_id, start, end)

    with gr.Blocks(title=cfg.app.title) as demo:
        if endpoint is not None:
            gr.api(endpoint, api_name=cfg.deploy.rerank.api_name, **api)
        # 동시 처리 수(app.concurrency)를 chat 그룹에 건다
        gr.api(chat, api_name="chat", concurrency_id="answer", **api)
        # 답변 생성이 큐를 잡고 있어도 문서를 볼 수 있게 문서 함수는 큐를 거치지 않는다
        for fn in (years, meetings, documents, document):
            gr.api(fn, api_name=fn.__name__, queue=False, **api)
    return demo


def main(endpoint: Callable | None = None, scorer: Callable | None = None,
         embedder: Callable | None = None) -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.retriever.get("rerank") and cfg.retriever.rerank.enabled and scorer is None:
        raise SystemExit("실시간 재정렬은 Space의 GPU 점수 함수가 있어야 한다(S39). 로컬은 "
                         "retriever.rerank.enabled=false로 실행한다")
    if cfg.app.concurrency != 1:
        # 임베딩 프로세스 파이프와 재정렬 멈춤 상태가 질의 하나씩을 전제한다. 둘이 겹치면 오류 없이
        # 서로의 질의 벡터를 받는다(이슈 #239)
        raise SystemExit(f"app.concurrency는 1만 지원한다: {cfg.app.concurrency}")
    logging.getLogger("langsmith.client").addHandler(TRACING)
    start = time.perf_counter()
    pipe = Pipeline(cfg, scorer=scorer, embedder=embedder)
    loaded = time.perf_counter()
    pipe.embed(cfg.app.title)  # 임베딩 모델을 먼저 불러 첫 질의가 기다리지 않게 한다
    parts = ", ".join(f"{k} {v:.1f}초" for k, v in pipe.retriever.timings.items())
    print(f"시작: 인덱스·코퍼스 {loaded - start:.1f}초({parts}), 임베딩 모델 "
          f"{time.perf_counter() - loaded:.1f}초", flush=True)
    demo = build(cfg, pipe, Corpus(cfg), endpoint)
    demo.queue(default_concurrency_limit=cfg.app.concurrency).launch()


if __name__ == "__main__":
    main()
