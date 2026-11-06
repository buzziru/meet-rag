"""채팅 API(S35, S48). 외부 API·인덱스·gradio 없이 합성 스트림과 합성 Pipeline으로 본다."""

import logging
import sys
from datetime import date
from types import SimpleNamespace

import pytest
from langsmith.run_trees import configure
from langsmith.utils import tracing_is_enabled
from omegaconf import open_dict

import rag.index
from rag import app
from rag.generate import Pipeline, build_messages
from rag.index import load_cfg

CTX = {"n": 1, "doc_id": "a1", "date": "2020-01-02", "committee_name": "법제사법위원회",
       "original": "http://example/1", "text": "본문 <b>굵게</b>", "index": "idx", "chunk_id": 0}
STORE = SimpleNamespace(names=["idx"], bounds=[0, 10])  # 인용한 근거의 청크 번호(S51)
CORPUS = SimpleNamespace(chunk_span=lambda doc_id, text: (3, 3 + len(text)),
                         meta={"a1": {**CTX, "meeting_name": "국정감사"}})


def chunk(content=None, finish=None, usage=None):
    choices = [] if usage else [SimpleNamespace(delta=SimpleNamespace(content=content),
                                                finish_reason=finish)]
    return SimpleNamespace(choices=choices, usage=usage, provider="p")


def stream_pipe(parts):
    pipe = object.__new__(Pipeline)
    pipe.cfg = load_cfg(["index.scope=full"])
    pipe.block = None
    pipe.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: iter([chunk(p) for p in parts] + [chunk(finish="stop")]))))
    return pipe


def fake_pipe(parts, seen=None):
    def stream(query, q_emb, history=(), search=None, prev=(), langsmith_extra=None):
        if seen is not None:
            seen.append(query)
        yield from parts
        yield {"answer": "".join(parts), "contexts": [CTX]}

    return SimpleNamespace(embed=lambda q: q, stream=stream, store=STORE,
                           index_meta={"n_chunks": 10})


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
    pipe.retrieve = lambda query, q_emb, k, prev=(): [CTX]
    pipe.messages = lambda contexts, query, history: []
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

    def stream(query, q_emb, history=(), search=None, prev=(), langsmith_extra=None):
        yield "답"
        yield "변"
        yield {"answer": "답변", "contexts": [ctx]}

    pipe = SimpleNamespace(embed=lambda q: q, stream=stream)
    events = list(app.chat_events(pipe, cfg, {}, CORPUS, "질의"))
    assert [e["text"] for e in events] == ["답", "답변", "답변"]
    assert [e["done"] for e in events] == [False, False, True]
    c = events[-1]["contexts"][0]
    assert set(c) == {"n", "date", "committee_name", "name", "original", "doc_id", "start", "end",
                      "body"}
    assert c["name"] == "2020년 1월 2일(목) 법제사법위원회 국정감사"
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
    assert items == [{"answer": raw, "raw": raw}]
    assert capsys.readouterr().out.count("첫 글자 지연:") == 1


def test_shown_keeps_raw_answer_for_pipeline(cfg):
    """Pipeline이 넘긴 결과 dict를 고치지 않는다. 추적·생성 기록은 원문이다."""
    result = {"answer": "".join(MOVED_RAW), "contexts": []}
    list(app.shown(iter([*MOVED_RAW, result]), cfg.app.meeting_info_max_name))
    assert result["answer"] == "".join(MOVED_RAW)


def test_chat_events_show_no_answer_notice_when_empty(cfg):
    def stream(query, q_emb, history=(), search=None, prev=(), langsmith_extra=None):
        yield {"answer": "", "contexts": [CTX]}

    pipe = SimpleNamespace(embed=lambda q: q, stream=stream)
    assert list(app.chat_events(pipe, cfg, {}, CORPUS, "질의"))[-1]["text"] == cfg.app.no_answer


@pytest.mark.parametrize(("finish", "expected"), [("length", True), ("stop", False), (None, False)])
def test_chat_events_notice_only_when_cut_by_length(cfg, finish, expected):
    """S41. 길이 제한으로 끝난 답변만 페이지가 알릴 글을 받는다."""
    def stream(query, q_emb, history=(), search=None, prev=(), langsmith_extra=None):
        yield "답변"
        yield {"answer": "답변", "contexts": [CTX], "finish_reason": finish}

    pipe = SimpleNamespace(embed=lambda q: q, stream=stream)
    last = list(app.chat_events(pipe, cfg, {}, CORPUS, "질의"))[-1]
    assert last["notice"] == (cfg.app.cut_notice if expected else "")
    assert last["text"] == "답변"  # 답변 글에는 붙이지 않는다


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
    assert "2020년 1월 2일(목) 법제사법위원회 제1회 제2차" == out["name"]
    assert f"**{labels.chunk_start}**" in out["body"] and "<b>근거</b>" in out["body"]
    assert labels.chunk_start not in app.doc_payload(pipe, cfg, corpus, "a1", -1, -1)["body"]


def test_chat_events_refuse_too_long_message_without_search(cfg):
    """S49. 상한까지는 처리하고, 넘으면 검색과 생성을 부르지 않고 안내만 보낸다."""
    seen = []
    limit = cfg.app.max_query_chars
    events = list(app.chat_events(fake_pipe(["답"], seen), cfg, {}, CORPUS, "가" * (limit + 1)))
    assert events == [{"text": cfg.app.query_too_long, "done": True, "contexts": [], "raw": "",
                       "rows": []}]
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


# 대화 이어 가기(S40) ---------------------------------------------------------------

FULL_CTX = {**CTX, "meeting_number": "제1회", "session_number": "제2차"}


def recording_pipe(cfg):
    """Pipeline.stream을 그대로 지나며 검색 질의, 임베딩한 질의, 생성 메시지를 기록한다."""
    seen = {}
    pipe = stream_pipe(["답", "변 [1]."])
    pipe.cfg = cfg

    def create(**kw):
        seen["messages"] = kw["messages"]
        return iter([chunk("답"), chunk("변 [1]."), chunk(finish="stop")])

    pipe.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    pipe.embed = lambda q: seen.setdefault("embedded", q)
    pipe.retrieve = lambda query, q_emb, k, prev=(): seen.setdefault("search", query) and [FULL_CTX]
    pipe.store, pipe.index_meta = STORE, {"n_chunks": 10}
    return pipe, seen


def no_rewrite(message, turns):
    raise AssertionError("앞 대화가 없으면 재작성을 부르지 않는다")


TURN = {"question": "2019년 국토위에서 광역버스 얘기가 나왔나요?",
        "answer": "차관은 단계적으로 도입하겠다고 답했습니다 [1][3]. "
                  "예산은 언급하지 않았습니다 [2]."}


@pytest.mark.parametrize("history", [None, [], "문자열", [{"question": "질문만"}]])
def test_first_question_keeps_messages_and_search_without_rewrite(cfg, history):
    pipe, seen = recording_pipe(cfg)
    events = list(app.chat_events(pipe, cfg, {}, CORPUS, "질의", history, no_rewrite))
    assert seen["search"] == seen["embedded"] == "질의"
    assert seen["messages"] == build_messages(cfg.prompt, [FULL_CTX], "질의")
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]
    assert events[-1]["raw"] == "답변 [1]."  # 페이지가 앞 대화로 들고 있을 생성 원문


def test_follow_up_searches_rewritten_query_and_puts_turns_before_contexts(capsys):
    # S40의 turns 형식을 본다. 기본값(S51 block, rule)의 형식은 tests/test_multiturn.py가 본다
    cfg = load_cfg(["index.scope=full", "app.multiturn.format=turns",
                    "app.multiturn.reuse.mode=off"])
    pipe, seen = recording_pipe(cfg)
    calls = []

    def rewriter(message, turns):
        calls.append((message, turns))
        return "2019년 국토교통위원회 광역버스 예산", {"rewrite_status": "ok", "rewrite_s": 0.5}

    list(app.chat_events(pipe, cfg, {}, CORPUS, "예산은?", [TURN], rewriter))
    clean = {"question": TURN["question"],
             "answer": "차관은 단계적으로 도입하겠다고 답했습니다. 예산은 언급하지 않았습니다."}
    assert calls == [("예산은?", [clean])]
    assert seen["search"] == seen["embedded"] == "2019년 국토교통위원회 광역버스 예산"
    msgs = seen["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == clean["question"] and msgs[2]["content"] == clean["answer"]
    # 질문은 원문, 근거는 이번 검색 결과
    assert msgs[3] == build_messages(cfg.prompt, [FULL_CTX], "예산은?")[1]
    log = capsys.readouterr().out
    assert "턴 2: 재작성 0.500초(ok)" in log and "턴 2: 첫 토큰" in log
    assert "예산" not in log and "광역버스" not in log  # 로그에 질의 원문이 없다


def test_clean_history_strips_citations_and_caps_turns_and_length(cfg):
    m = cfg.app.multiturn
    turns = [{"question": f"질문{i}", "answer": f"답{i} [1]."} for i in range(m.max_turns + 2)]
    out = app.clean_history(turns, cfg)
    assert out == [{"question": f"질문{i}", "answer": f"답{i}."}
                   for i in range(2, m.max_turns + 2)]
    long = [{"question": "가" * (cfg.app.max_query_chars + 5),
             "answer": "나 [2]" * m.max_answer_chars}]
    out = app.clean_history(long, cfg)[0]
    assert len(out["question"]) == cfg.app.max_query_chars
    assert len(out["answer"]) == m.max_answer_chars and "[" not in out["answer"]


@pytest.mark.parametrize("history", [
    None, "질문", {"question": "q", "answer": "a"}, [1, None, "턴"],
    [{"question": "q"}, {"answer": "a"}, {"question": 1, "answer": "a"},
     {"question": "q", "answer": ["a"]}, {"question": " ", "answer": "a"}],
])
def test_clean_history_drops_malformed_turns(cfg, history):
    assert app.clean_history(history, cfg) == []


def test_clean_history_keeps_valid_turns_among_malformed(cfg):
    history = [{"question": "q"}, {"question": "앞", "answer": "답", "extra": "x"}, 3]
    assert app.clean_history(history, cfg) == [{"question": "앞", "answer": "답"}]


def test_shown_replaces_refusal_words_only_on_screen(cfg):
    """S52. 화면 글만 바꾸고 생성 원문(raw)과 Pipeline 결과 dict는 그대로 둔다. S45 회의 정보 변환과
    함께 써도 글자가 사라지지 않는다."""
    words = dict(cfg.app.shown_words)
    raw = MOVED_RAW + [" 나머지는 제공", "된 회의록에서 답을 찾지 못했습니다."]
    result = {"answer": "".join(raw), "contexts": []}
    items = list(app.shown(iter([*raw, result]), cfg.app.meeting_info_max_name, words))
    want = MOVED + " 나머지는 검색된 회의록에서 답을 찾지 못했습니다."
    assert "".join(i for i in items if isinstance(i, str)) == want
    assert items[-1]["answer"] == want and items[-1]["raw"] == "".join(raw)
    assert result["answer"] == "".join(raw)


def test_shown_words_refuses_empty_word():
    """S52. 빈 말을 바꾸면 모든 글자 사이에 새 말이 들어가므로 읽을 때 멈춘다."""
    assert app.shown_words(load_cfg(["index.scope=full"])) == {"제공된 회의록": "검색된 회의록"}
    cfg = load_cfg(["index.scope=full"])
    with open_dict(cfg):
        cfg.app.shown_words = {"": "x"}
    with pytest.raises(SystemExit, match="shown_words"):
        app.shown_words(cfg)
    with open_dict(cfg):
        cfg.app.shown_words = {"제공된 회의록": None}  # 새 말을 비우면 None이 된다
    with pytest.raises(SystemExit, match="shown_words"):
        app.shown_words(cfg)


def test_packed_round_trips_korean_json():
    """S41. 페이지가 gzip을 풀어 같은 값을 얻는다(base64 → gzip → UTF-8 JSON)."""
    import base64
    import gzip
    import json

    value = [["2019년 10월 25일(금) 정무위원회 제371회 제1차", "049488"]]
    raw = gzip.decompress(base64.b64decode(app.packed(value))).decode("utf-8")
    assert json.loads(raw) == value
