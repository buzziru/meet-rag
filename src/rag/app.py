"""채팅 화면. 자유 질의를 검색해 답변을 스트리밍으로 보여 주고 끝나면 근거를 붙인다.

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

from langsmith.run_trees import configure, get_cached_client

from rag.docs import Corpus, doc_body, doc_name, format_doc, readable
from rag.generate import Pipeline, recipe
from rag.index import load_cfg
from rag.speakers import render

SCROLL_TO_QUESTION = """() => { setTimeout(() => {
  const rows = document.querySelectorAll("#chat .user-row");
  rows[rows.length - 1]?.scrollIntoView({block: "start"});
}, 200); }"""

EVIDENCE_PREFIX = "#evidence:"
# 근거 머리를 누르면 페이지를 다시 불러오지 않고 숨긴 버튼으로 서버에 알린다. 다시 불러오면 대화가
# 지워진다. 스크립트로 칸에 넣은 값은 Gradio 이벤트를 일으키지 않아 값은 READ_EVIDENCE로 넘긴다
BIND_EVIDENCE_LINKS = f"""() => {{ document.addEventListener("click", (e) => {{
  const a = e.target.closest('a[href^="{EVIDENCE_PREFIX}"]');
  if (!a) return;
  e.preventDefault();
  e.stopPropagation();
  window.evidenceKey = a.getAttribute("href").slice({len(EVIDENCE_PREFIX)});
  document.getElementById("evidence-open").click();
}}, true); }}"""
READ_EVIDENCE = "() => [window.evidenceKey]"
SCROLL_TO_CHUNK = """() => { setTimeout(() => {
  const all = document.querySelectorAll("#evidence-view strong");
  [...all].find((s) => s.textContent === "MARK")?.scrollIntoView({block: "start"});
}, 200); }"""
# 선택 칸의 긴 이름이 화살표와 겹치지 않게 오른쪽을 비운다
CSS = ".browse input { padding-right: 2rem !important; text-overflow: ellipsis; }"


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


def evidence_link(c: dict, corpus) -> str:
    """근거 머리 링크. 페이지를 다시 불러오지 않도록 BIND_EVIDENCE_LINKS가 눌림을 받는다."""
    span = corpus.chunk_span(c["doc_id"], c["text"])
    start, end = span if span else (-1, -1)
    return f"{EVIDENCE_PREFIX}{c['doc_id']}:{start}:{end}"


def parse_evidence(value: str) -> tuple[str, tuple[int, int] | None]:
    """링크 값(문서 번호:시작:끝)을 (문서 번호, 청크 위치)로 읽는다."""
    doc_id, start, end = value.split(":")
    return doc_id, (int(start), int(end)) if int(start) >= 0 else None


def format_contexts(contexts: list[dict], corpus) -> str:
    """근거를 번호, 회의 정보, 원문 링크, 본문으로 보여 준다. 본문은 생성·judge가 받는 발언자
    표시(머리 줄과 시작 표지)를 화면용 문단으로 나눈 것이다. 머리를 누르면 근거 탭에서
    그 문서를 연다."""
    return "\n\n---\n\n".join(
        f'<a href="{evidence_link(c, corpus)}"><strong>[{c["n"]}] {c["date"]} '
        f'{c["committee_name"]}</strong></a> ([회의록]({c["original"]}))\n\n'
        + readable(render(c))
        for c in contexts)


def ask(message: str, history: list[dict]) -> tuple[list[dict], str, str]:
    """질문을 대화에 바로 보이고 입력창을 비운다. 답변은 respond가 만든다. 빈 입력은 무시한다."""
    if not message.strip():
        return history, "", ""
    return [*history, {"role": "user", "content": message}], "", message


def respond(pipe, cfg, rec: dict, corpus, message: str,
            history: list[dict]) -> Iterator[list[dict]]:
    """history는 ask가 질문을 더한 대화다. 첫 조각이 오기 전에는 아무것도 내보내지 않는다. 내보내면
    화면의 대기 표시가 사라진다."""
    if not message:
        yield history
        return
    TRACING.refresh()
    query = search_query(message, history[:-1])
    answer = {"role": "assistant", "content": ""}
    chat = [*history, answer]
    for item in pipe.stream(query, pipe.embed(query), langsmith_extra={"metadata": rec}):
        if isinstance(item, dict):
            answer["content"] = item["answer"] or cfg.app.no_answer
            chat.append({"role": "assistant",
                         "content": format_contexts(item["contexts"], corpus),
                         "metadata": {"title": cfg.app.contexts_title}})
        else:
            answer["content"] += item
        yield [dict(m) for m in chat]
    get_cached_client().flush()


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
    TRACING.refresh()
    query = search_query(message, [])
    text = ""
    for item in pipe.stream(query, pipe.embed(query), langsmith_extra={"metadata": rec}):
        if isinstance(item, dict):
            yield {"text": item["answer"] or cfg.app.no_answer, "done": True,
                   "contexts": [context_payload(c, corpus) for c in item["contexts"]]}
        else:
            text += item
            yield {"text": text, "done": False}
    get_cached_client().flush()


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
    """화면을 만든다. 평가·실험 환경에는 gradio가 없어 여기서 불러온다(pyproject의 app). endpoint는
    Space의 GPU 점수 함수로, 토큰 호출에 쓰도록 API 문서에 보이지 않는 경로로 연다(S39, D-74)."""
    import gradio as gr

    rec = recipe(cfg, pipe.index_meta, True)
    labels = cfg.app.labels

    def answer(message: str, history: list[dict]) -> Iterator[list[dict]]:
        yield from respond(pipe, cfg, rec, corpus, message, history)

    def pick_year(year: int):
        return (gr.Dropdown(choices=corpus.meetings(year), value=None, interactive=True),
                gr.Dropdown(choices=[], value=None, interactive=False))

    def pick_meeting(conf: str):
        return gr.Dropdown(choices=corpus.documents(conf), value=None, interactive=True)

    def show_doc(doc_id: str, chunk: tuple[int, int] | None = None) -> str:
        spans = pipe.spans.get(doc_id, []) if pipe.speakers != "off" else []
        return format_doc(corpus.read(doc_id), spans, pipe.speakers, chunk,
                          (labels.chunk_start, labels.chunk_end))

    def pick_doc(doc_id: str):
        return show_doc(doc_id), gr.Tabs(selected="doc")

    def pick_evidence(value: str):
        return show_doc(*parse_evidence(value)), gr.Tabs(selected="evidence")

    def reset():
        return (gr.Dropdown(value=None),
                gr.Dropdown(choices=[], value=None, interactive=False),
                gr.Dropdown(choices=[], value=None, interactive=False))

    with gr.Blocks(title=cfg.app.title) as demo:
        with gr.Sidebar(width=cfg.app.sidebar_width):
            gr.Markdown(cfg.app.browse_notice)
            year = gr.Dropdown(corpus.years(), value=None, label=labels.year,
                               elem_classes="browse")
            # 앞 칸을 고르기 전에는 선택지가 없어 입력하면 오류가 나므로 막아 둔다
            meeting = gr.Dropdown([], label=labels.meeting, filterable=True, interactive=False,
                                  elem_classes="browse")
            documents = gr.Dropdown([], label=labels.document, filterable=True, interactive=False,
                                    elem_classes="browse")
            clear = gr.Button(labels.reset)
        gr.Markdown(f"# {cfg.app.title}\n\n{cfg.app.notice}")
        with gr.Tabs() as tabs:
            with gr.Tab(labels.chat_tab, id="chat"):
                # 답변을 처음부터 읽도록 맨 아래로 따라가지 않고, 새 질문을 위로 올린다
                chatbot = gr.Chatbot(show_label=False, height="70vh", autoscroll=False,
                                     elem_id="chat")
                box = gr.Textbox(placeholder=cfg.app.placeholder, show_label=False,
                                 submit_btn=True)
            with gr.Tab(labels.doc_tab, id="doc"):
                viewer = gr.Markdown(cfg.app.doc_placeholder)
            with gr.Tab(labels.evidence_tab, id="evidence"):
                evidence = gr.Markdown(cfg.app.evidence_placeholder, elem_id="evidence-view")
        evidence_key = gr.Textbox(visible="hidden")
        evidence_open = gr.Button(visible="hidden", elem_id="evidence-open")
        question = gr.State("")
        asked = box.submit(ask, [box, chatbot], [chatbot, box, question], queue=False,
                           api_name=False)
        asked.then(None, js=SCROLL_TO_QUESTION, api_name=False)
        asked.then(answer, [question, chatbot], chatbot, api_name=False)
        # 답변 생성이 큐를 잡고 있어도 문서를 볼 수 있게 큐를 거치지 않는다
        year.input(pick_year, year, [meeting, documents], queue=False, api_name=False)
        meeting.input(pick_meeting, meeting, documents, queue=False, api_name=False)
        documents.input(pick_doc, documents, [viewer, tabs], queue=False, api_name=False)
        clear.click(reset, None, [year, meeting, documents], queue=False, api_name=False)
        opened = evidence_open.click(pick_evidence, evidence_key, [evidence, tabs], queue=False,
                                     js=READ_EVIDENCE, api_name=False)
        opened.then(None, js=SCROLL_TO_CHUNK.replace("MARK", labels.chunk_start), api_name=False)
        demo.load(None, js=BIND_EVIDENCE_LINKS, api_name=False)
        if endpoint is not None:
            gr.api(endpoint, api_name=cfg.deploy.rerank.api_name,
                   api_visibility="undocumented")
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

        # 답변 생성이 큐를 잡고 있어도 문서를 볼 수 있게 문서 함수는 큐를 거치지 않는다
        gr.api(chat, api_name="chat", **api)
        for fn in (years, meetings, documents, document):
            gr.api(fn, api_name=fn.__name__, queue=False, **api)
    return demo


def main(endpoint: Callable | None = None, scorer: Callable | None = None,
         embedder: Callable | None = None) -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.retriever.get("rerank") and cfg.retriever.rerank.enabled and scorer is None:
        raise SystemExit("실시간 재정렬은 Space의 GPU 점수 함수가 있어야 한다(S39). 로컬은 "
                         "retriever.rerank.enabled=false로 실행한다")
    logging.getLogger("langsmith.client").addHandler(TRACING)
    start = time.perf_counter()
    pipe = Pipeline(cfg, scorer=scorer, embedder=embedder)
    loaded = time.perf_counter()
    pipe.embed(cfg.app.title)  # 임베딩 모델을 먼저 불러 첫 질의가 기다리지 않게 한다
    parts = ", ".join(f"{k} {v:.1f}초" for k, v in pipe.retriever.timings.items())
    print(f"시작: 인덱스·코퍼스 {loaded - start:.1f}초({parts}), 임베딩 모델 "
          f"{time.perf_counter() - loaded:.1f}초", flush=True)
    demo = build(cfg, pipe, Corpus(cfg), endpoint)
    demo.queue(default_concurrency_limit=cfg.app.concurrency).launch(css=CSS)


if __name__ == "__main__":
    main()
