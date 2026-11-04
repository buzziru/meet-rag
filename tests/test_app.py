"""채팅 앱(S35). API·인덱스·gradio 없이 합성 스트림과 합성 Pipeline으로 본다."""

import sys
from types import SimpleNamespace

import pytest

from rag import app
from rag.generate import Pipeline
from rag.index import load_cfg

CTX = {"n": 1, "doc_id": "a1", "date": "2020-01-02", "committee_name": "법제사법위원회",
       "original": "http://example/1", "text": "본문 <b>굵게</b>"}
ASKED = ("질의", [{"role": "user", "content": "질의"}])


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


@pytest.fixture(autouse=True)
def no_flush(monkeypatch):
    monkeypatch.setattr(app, "get_cached_client", lambda: SimpleNamespace(flush=lambda: None))


def test_tokens_join_to_generate_answer_and_hide_thought():
    parts = ["<thought>", "생각", "</thought>", "\n답변", "이다"]
    items = list(stream_pipe(parts).tokens([]))
    assert items[:-1] == ["답변", "이다"]
    out = Pipeline.generate.__wrapped__(stream_pipe(parts), [], True, False)
    assert "".join(items[:-1]) == out["answer"] == items[-1]["answer"] == "답변이다"
    assert out["thought"] == "생각" and out["finish_reason"] == "stop"


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


def test_history_does_not_change_search_query(cfg):
    seen = []
    pipe = fake_pipe(["답"], seen)
    list(app.respond(pipe, cfg, {}, *ASKED))
    past = [{"role": "user", "content": "앞 질문"}, {"role": "assistant", "content": "앞 답변"}]
    history, _, message = app.ask("질의", past)
    last = list(app.respond(pipe, cfg, {}, message, history))[-1]
    assert seen == ["질의", "질의"]
    assert last[:3] == history


def test_ask_shows_question_and_clears_input():
    history, box, message = app.ask("질의", [])
    assert history == [{"role": "user", "content": "질의"}]
    assert box == "" and message == "질의"


def test_respond_waits_for_first_token_then_appends_contexts(cfg):
    """첫 조각 전에 내보내면 화면의 대기 표시가 사라진다."""
    chats = list(app.respond(fake_pipe(["답", "변"]), cfg, {}, *ASKED))
    assert [c[1]["content"] for c in chats[:2]] == ["답", "답변"]
    last = chats[-1]
    assert last[1]["content"] == "답변"
    assert last[2]["metadata"] == {"title": cfg.app.contexts_title}
    assert "&lt;b&gt;" in last[2]["content"] and "<b>" not in last[2]["content"]
    assert "(http://example/1)" in last[2]["content"]
    assert '<a href="?doc=a1" target="_blank">' in last[2]["content"]


def test_respond_shows_notice_when_answer_is_empty(cfg):
    last = list(app.respond(fake_pipe([]), cfg, {}, *ASKED))[-1]
    assert last[1]["content"] == cfg.app.no_answer


def test_blank_message_keeps_history_and_skips_search(cfg):
    seen = []
    history, box, message = app.ask("  ", [])
    assert (history, box, message) == ([], "", "")
    assert list(app.respond(fake_pipe(["답"], seen), cfg, {}, message, history)) == [[]]
    assert seen == []


@pytest.mark.parametrize("args, match", [
    (["+exp=current"], "재정렬"),
    (["+exp=current", "retriever.rerank.enabled=false"], "인덱스 읽음"),
])
def test_main_requires_rerank_off_before_loading(monkeypatch, args, match):
    def loaded(cfg):
        raise SystemExit("인덱스 읽음")

    monkeypatch.setattr(app, "Pipeline", loaded)
    monkeypatch.setattr(sys, "argv", ["rag.app", *args])
    with pytest.raises(SystemExit, match=match):
        app.main()


def test_format_contexts_shows_same_speaker_rendering_as_model():
    speakers = {"questioners": [{"name": "홍길동", "position": "위원", "affiliation": ""}],
                "answerers": [{"name": "김철수", "position": "장관", "affiliation": "국토부"}],
                "spans": [{"role": "question", "start": 0, "end": 2, "name": "홍길동",
                           "position": "위원", "affiliation": ""}]}
    out = app.format_contexts([{**CTX, "speakers": speakers}])
    assert "질의자: 홍길동 위원 / 답변자: 김철수 국토부 장관\n\n" in out
    assert "**〈질의 홍길동 위원〉**\n\n본문\n\n**〈/질의〉**\n\n &lt;b&gt;" in out
    assert "<b>" not in out
