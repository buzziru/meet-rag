"""채팅 API(S35, S48). 외부 API·인덱스·gradio 없이 합성 스트림과 합성 Pipeline으로 본다."""

import logging
import sys
from datetime import date
from types import SimpleNamespace

import pytest
from langsmith.run_trees import configure
from langsmith.utils import tracing_is_enabled

import rag.index
from rag import app
from rag.generate import Pipeline
from rag.index import load_cfg

CTX = {"n": 1, "doc_id": "a1", "date": "2020-01-02", "committee_name": "법제사법위원회",
       "original": "http://example/1", "text": "본문 <b>굵게</b>"}
CORPUS = SimpleNamespace(chunk_span=lambda doc_id, text: (3, 3 + len(text)))


def chunk(content=None, finish=None, usage=None):
    choices = [] if usage else [SimpleNamespace(delta=SimpleNamespace(content=content),
                                                finish_reason=finish)]
    return SimpleNamespace(choices=choices, usage=usage, provider="p")


def stream_pipe(parts):
    pipe = object.__new__(Pipeline)
    pipe.cfg = load_cfg(["index.scope=full"])
    pipe.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: iter([chunk(p) for p in parts] + [chunk(finish="stop")]))))
    return pipe


def fake_pipe(parts, seen=None):
    def stream(query, q_emb, langsmith_extra=None):
        if seen is not None:
            seen.append(query)
        yield from parts
        yield {"answer": "".join(parts), "contexts": [CTX]}

    return SimpleNamespace(embed=lambda q: q, stream=stream)


@pytest.fixture
def cfg():
    return load_cfg(["index.scope=full"])


def test_tokens_join_to_generate_answer_and_hide_thought():
    parts = ["<thought>", "생각", "</thought>", "\n답변", "이다"]
    items = list(stream_pipe(parts).tokens([]))
    assert items[:-1] == ["답변", "이다"]
    out = Pipeline.generate.__wrapped__(stream_pipe(parts), [], True, False)
    assert "".join(items[:-1]) == out["answer"] == items[-1]["answer"] == "답변이다"
    assert out["thought"] == "생각" and out["finish_reason"] == "stop"


@pytest.mark.parametrize(("prompt", "text", "answer"), [
    ("v14", "- 장관은 답했다 [1].", "장관은 답했다 [1]."),
    ("v14", "- 장관은 답했다 [1].\n\n나머지는 없다.", "장관은 답했다 [1].\n\n나머지는 없다."),
    ("v14", "- 가 [1].\n- 나 [2].", "- 가 [1].\n- 나 [2]."),
    ("v14", "문단 - 가운데 [1].", "문단 - 가운데 [1]."),
    ("v12", "- 장관은 답했다 [1].", "- 장관은 답했다 [1]."),  # 켜지 않은 프롬프트는 그대로
])
def test_answer_strips_lone_bullet_only_when_prompt_asks(prompt, text, answer):
    """S42. 생성 기록과 앱이 같이 쓰는 결과 dict의 답변을 본다."""
    pipe = stream_pipe([text])
    pipe.cfg = load_cfg(["index.scope=full", f"prompt={prompt}"])
    assert list(pipe.tokens([]))[-1]["answer"] == answer
    assert Pipeline.generate.__wrapped__(pipe, [], True, False)["answer"] == answer


def test_generate_echo_prints_only_answer(capsys):
    Pipeline.generate.__wrapped__(stream_pipe(["<thought>생각</thought>", "답변"]), [], True, True)
    assert capsys.readouterr().out == "답변\n"


def test_stream_ends_with_contexts():
    pipe = stream_pipe(["답", "변"])
    pipe.retrieve = lambda query, q_emb, k: [CTX]
    pipe.messages = lambda contexts, query: []
    items = list(Pipeline.stream.__wrapped__(pipe, "질의", None))
    assert items[:-1] == ["답", "변"]
    assert items[-1]["contexts"] == [CTX] and items[-1]["answer"] == "답변"


@pytest.mark.parametrize("args, match", [
    (["+exp=current"], "재정렬"),
    (["+exp=current", "retriever.rerank.enabled=false"], "인덱스 읽음"),
    (["+exp=current", "retriever.rerank.enabled=false", "app.concurrency=2"], "concurrency"),
])
def test_main_requires_rerank_off_before_loading(monkeypatch, args, match):
    def loaded(cfg, scorer=None, embedder=None):
        raise SystemExit("인덱스 읽음")

    monkeypatch.setattr(app, "Pipeline", loaded)
    monkeypatch.setattr(sys, "argv", ["rag.app", *args])
    with pytest.raises(SystemExit, match=match):
        app.main()


def test_context_body_shows_speakers_as_readable_paragraphs():
    speakers = {"questioners": [{"name": "홍길동", "position": "위원", "affiliation": ""}],
                "answerers": [{"name": "김철수", "position": "장관", "affiliation": "국토부"}],
                "spans": [{"role": "question", "start": 0, "end": 2, "name": "홍길동",
                           "position": "위원", "affiliation": ""}]}
    out = app.context_payload({**CTX, "speakers": speakers}, CORPUS)["body"]
    assert "질의자: 홍길동 위원 / 답변자: 김철수 국토부 장관\n\n" in out
    assert "**〈질의 홍길동 위원〉**\n\n본문\n\n <b>" in out
    assert "〈/" not in out


@pytest.fixture
def clean_tracing():
    # 환경 변수는 langsmith가 캐시해 뒤 테스트까지 추적이 켜지므로 전역 설정으로 켠다
    configure(enabled=True)
    yield
    configure(enabled=None)


def test_tracing_turns_off_on_limit_and_back_on_next_month(clean_tracing, cfg, monkeypatch):
    now = [date(2026, 11, 20)]
    switch = app.TracingSwitch(today=lambda: now[0])
    monkeypatch.setattr(app, "TRACING", switch)
    log = logging.getLogger("langsmith.client")
    log.addHandler(switch)
    try:
        log.warning("Failed to send compressed multipart ingest: connection reset")
        assert tracing_is_enabled() is True  # 다른 전송 실패로는 끄지 않는다
        log.warning("Failed to multipart ingest runs: Rate limit exceeded for https://x")
        assert tracing_is_enabled() is False
        now[0] = date(2026, 11, 30)
        list(app.chat_events(fake_pipe(["답"]), cfg, {}, CORPUS, "질의"))
        assert tracing_is_enabled() is False  # 같은 달에는 켜지 않는다
        now[0] = date(2026, 12, 1)
        list(app.chat_events(fake_pipe(["답"]), cfg, {}, CORPUS, "질의"))
        assert tracing_is_enabled() is True
        log.warning("Failed to multipart ingest runs: Rate limit exceeded for https://x")
        assert tracing_is_enabled() is False  # 다음 달에도 넘으면 다시 끈다
    finally:
        log.removeHandler(switch)


def test_tracing_switch_leaves_tracing_alone_without_limit(cfg, clean_tracing, monkeypatch):
    switch = app.TracingSwitch(today=lambda: date(2026, 12, 1))
    monkeypatch.setattr(app, "TRACING", switch)
    list(app.chat_events(fake_pipe(["답"]), cfg, {}, CORPUS, "질의"))
    assert tracing_is_enabled() is True


def test_chat_events_send_growing_text_then_contexts_without_labels(cfg):
    ctx = {**CTX, "splits": "test", "n_qa": 3, "summary_q": "질의", "summary_a": "답"}

    def stream(query, q_emb, langsmith_extra=None):
        yield "답"
        yield "변"
        yield {"answer": "답변", "contexts": [ctx]}

    pipe = SimpleNamespace(embed=lambda q: q, stream=stream)
    events = list(app.chat_events(pipe, cfg, {}, CORPUS, "질의"))
    assert [e["text"] for e in events] == ["답", "답변", "답변"]
    assert [e["done"] for e in events] == [False, False, True]
    c = events[-1]["contexts"][0]
    assert set(c) == {"n", "date", "committee_name", "original", "doc_id", "start", "end", "body"}
    assert (c["start"], c["end"]) == (3, 3 + len(CTX["text"]))
    assert "<b>굵게</b>" in c["body"]  # 이스케이프를 풀어 보내고 페이지가 글자로 넣는다


MOVED_RAW = ["2018년 10월 10일 국방", "위원회 회의에서 A는 ", "답했습니다", " [1]."]
MOVED = "A는 답했습니다(2018년 10월 10일 국방위원회) [1]."


def test_chat_events_show_meeting_info_at_sentence_end(cfg, capsys):
    """S45. 잡아 둔 동안은 보내지 않고, 조각과 마지막 답변이 같은 글이고, 로그에 원문이 없다."""
    events = list(app.chat_events(fake_pipe(MOVED_RAW), cfg, {}, CORPUS, "질의"))
    assert [e["text"] for e in events] == ["A는", "A는 답했습니다", MOVED, MOVED]
    log = capsys.readouterr().out
    assert log.count("첫 글자 지연:") == 1 and "국방" not in log and "질의" not in log


def test_shown_logs_delay_at_final_answer_when_nothing_was_released(capsys):
    """전부 잡아 둔 채 끝나면 마지막 답변이 첫 글자다."""
    raw = "2018년 10월 10일 국방"
    items = list(app.shown(iter([raw, {"answer": raw}]), 40))
    assert items == [{"answer": raw}]
    assert capsys.readouterr().out.count("첫 글자 지연:") == 1


def test_shown_keeps_raw_answer_for_pipeline(cfg):
    """Pipeline이 넘긴 결과 dict를 고치지 않는다. 추적·생성 기록은 원문이다."""
    result = {"answer": "".join(MOVED_RAW), "contexts": []}
    list(app.shown(iter([*MOVED_RAW, result]), cfg.app.meeting_info_max_name))
    assert result["answer"] == "".join(MOVED_RAW)


def test_chat_events_show_no_answer_notice_when_empty(cfg):
    def stream(query, q_emb, langsmith_extra=None):
        yield {"answer": "", "contexts": [CTX]}

    pipe = SimpleNamespace(embed=lambda q: q, stream=stream)
    assert list(app.chat_events(pipe, cfg, {}, CORPUS, "질의"))[-1]["text"] == cfg.app.no_answer


def test_doc_payload_returns_one_document_with_chunk_marks_and_no_labels(cfg):
    doc = {"doc_id": "a1", "date": "2020-01-02", "committee_name": "법제사법위원회",
           "meeting_number": "제1회", "session_number": "제2차", "agenda": "1. 안건",
           "original": "http://example/1", "context": "앞 <b>근거</b> 뒤", "splits": "test",
           "n_qa": 3, "summary_q": "질의", "summary_a": "답"}
    pipe = SimpleNamespace(spans={}, speakers="off")
    corpus = SimpleNamespace(read=lambda doc_id: doc)
    labels = cfg.app.labels
    out = app.doc_payload(pipe, cfg, corpus, "a1", 2, 12)
    assert set(out) == {"name", "agenda", "original", "body"}
    assert "2020-01-02 법제사법위원회 제1회 제2차" == out["name"]
    assert f"**{labels.chunk_start}**" in out["body"] and "<b>근거</b>" in out["body"]
    assert labels.chunk_start not in app.doc_payload(pipe, cfg, corpus, "a1", -1, -1)["body"]


def test_chat_events_refuse_too_long_message_without_search(cfg):
    """S49. 상한까지는 처리하고, 넘으면 검색과 생성을 부르지 않고 안내만 보낸다."""
    seen = []
    limit = cfg.app.max_query_chars
    events = list(app.chat_events(fake_pipe(["답"], seen), cfg, {}, CORPUS, "가" * (limit + 1)))
    assert events == [{"text": cfg.app.query_too_long, "done": True, "contexts": []}]
    assert seen == []
    assert list(app.chat_events(fake_pipe(["답"], seen), cfg, {}, CORPUS, "가" * limit))
    assert len(seen) == 1


def test_git_state_reads_commit_file_when_uploaded(tmp_path, monkeypatch):
    """S49. Space의 git은 Hub 커밋이라 올릴 때 넣은 커밋을 먼저 쓴다."""
    git_state = rag.index.git_state.__wrapped__
    monkeypatch.setattr(rag.index, "ROOT", tmp_path)
    (tmp_path / "COMMIT").write_text("abc123\n", encoding="utf-8")
    assert git_state() == ("abc123", False)


def test_chat_events_skip_blank_message(cfg):
    seen = []
    assert list(app.chat_events(fake_pipe(["답"], seen), cfg, {}, CORPUS, "  ")) == []
    assert seen == []
