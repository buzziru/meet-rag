"""채팅 화면. 자유 질의를 검색해 답변을 스트리밍으로 보여 주고 끝나면 근거를 붙인다.

명세는 docs/slices/35-chat-app.md. 실시간 재정렬이 없어 재정렬을 끈 구성으로만 시작한다(S38에서
만든다). 방문자 질의는 data/에 저장하지 않고 LangSmith 추적으로만 남는다.
"""

import sys
from collections.abc import Iterator

from langsmith.run_trees import get_cached_client

from rag.docs import Corpus, format_doc, readable
from rag.generate import Pipeline, recipe
from rag.index import load_cfg
from rag.speakers import render

SCROLL_TO_QUESTION = """() => { setTimeout(() => {
  const rows = document.querySelectorAll("#chat .user-row");
  rows[rows.length - 1]?.scrollIntoView({block: "start"});
}, 200); }"""


def search_query(message: str, history: list[dict]) -> str:
    """검색에 쓸 질의. 지금은 싱글턴이라 이력을 쓰지 않는다. 멀티턴은 여기서 이력으로 재작성한다."""
    return message


def format_contexts(contexts: list[dict]) -> str:
    """근거를 번호, 회의 정보, 원문 링크, 본문으로 보여 준다. 본문은 생성·judge가 받는 것과 같은
    렌더링(발언자 머리 줄과 표지)이다. 머리를 누르면 새 탭에서 그 문서를 연다. 같은 탭으로 열면
    대화가 지워진다."""
    return "\n\n---\n\n".join(
        f'<a href="?doc={c["doc_id"]}" target="_blank"><strong>[{c["n"]}] {c["date"]} '
        f'{c["committee_name"]}</strong></a> ([회의록]({c["original"]}))\n\n'
        + readable(render(c))
        for c in contexts)


def ask(message: str, history: list[dict]) -> tuple[list[dict], str, str]:
    """질문을 대화에 바로 보이고 입력창을 비운다. 답변은 respond가 만든다. 빈 입력은 무시한다."""
    if not message.strip():
        return history, "", ""
    return [*history, {"role": "user", "content": message}], "", message


def respond(pipe, cfg, rec: dict, message: str, history: list[dict]) -> Iterator[list[dict]]:
    """history는 ask가 질문을 더한 대화다. 첫 조각이 오기 전에는 아무것도 내보내지 않는다. 내보내면
    화면의 대기 표시가 사라진다."""
    if not message:
        yield history
        return
    query = search_query(message, history[:-1])
    answer = {"role": "assistant", "content": ""}
    chat = [*history, answer]
    for item in pipe.stream(query, pipe.embed(query), langsmith_extra={"metadata": rec}):
        if isinstance(item, dict):
            answer["content"] = item["answer"] or cfg.app.no_answer
            chat.append({"role": "assistant", "content": format_contexts(item["contexts"]),
                         "metadata": {"title": cfg.app.contexts_title}})
        else:
            answer["content"] += item
        yield [dict(m) for m in chat]
    get_cached_client().flush()


def build(cfg, pipe, corpus):
    """화면을 만든다. 평가·실험 환경에는 gradio가 없어 여기서 불러온다(pyproject의 app)."""
    import gradio as gr

    rec = recipe(cfg, pipe.index_meta, True)
    labels = cfg.app.labels

    def answer(message: str, history: list[dict]) -> Iterator[list[dict]]:
        yield from respond(pipe, cfg, rec, message, history)

    def pick_year(year: int):
        return (gr.Dropdown(choices=corpus.meetings(year), value=None),
                gr.Dropdown(choices=[], value=None))

    def pick_meeting(conf: str):
        return gr.Dropdown(choices=corpus.documents(conf), value=None)

    def show_doc(doc_id: str) -> str:
        spans = pipe.spans.get(doc_id, []) if pipe.speakers != "off" else []
        return format_doc(corpus.read(doc_id), spans, pipe.speakers)

    def pick_doc(doc_id: str):
        return show_doc(doc_id), gr.Tabs(selected="doc")

    def reset():
        return (gr.Dropdown(value=None), gr.Dropdown(choices=[], value=None),
                gr.Dropdown(choices=[], value=None))

    def open_linked(request: gr.Request):
        """주소의 ?doc=로 연 문서를 보여 주고 목록을 맞춘다. 없거나 모르는 번호면 그대로 둔다."""
        doc_id = request.query_params.get("doc")
        found = corpus.locate(doc_id) if doc_id else None
        if found is None:
            return gr.skip()
        y, conf = found
        return (gr.Dropdown(value=y), gr.Dropdown(choices=corpus.meetings(y), value=conf),
                gr.Dropdown(choices=corpus.documents(conf), value=doc_id), show_doc(doc_id),
                gr.Tabs(selected="doc"))

    with gr.Blocks(title=cfg.app.title) as demo:
        with gr.Sidebar():
            gr.Markdown(cfg.app.browse_notice)
            year = gr.Dropdown(corpus.years(), value=None, label=labels.year)
            meeting = gr.Dropdown([], label=labels.meeting, filterable=True)
            documents = gr.Dropdown([], label=labels.document, filterable=True)
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
        demo.load(open_linked, None, [year, meeting, documents, viewer, tabs], queue=False,
                  api_name=False)
    return demo


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.retriever.get("rerank") and cfg.retriever.rerank.enabled:
        raise SystemExit("앱에는 실시간 재정렬이 없다(S38). retriever.rerank.enabled=false로 "
                         "실행한다")
    pipe = Pipeline(cfg)
    pipe.embed(cfg.app.title)  # 임베딩 모델을 먼저 불러 첫 질의가 기다리지 않게 한다
    demo = build(cfg, pipe, Corpus(cfg))
    demo.queue(default_concurrency_limit=cfg.app.concurrency).launch()


if __name__ == "__main__":
    main()
