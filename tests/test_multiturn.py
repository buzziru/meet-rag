"""후속 질문 답변 다듬기와 앞 근거 다시 쓰기(S51). 외부 API·인덱스 없이 합성 값으로 본다."""

import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from omegaconf import OmegaConf

from rag import app, multiturn_check
from rag.generate import Pipeline, build_messages
from rag.index import ROOT, load_cfg
from rag.retrieve import chunks_by_doc
from rag.rewrite import FollowUpRewriter, PrevDecider

META = {"date": "2020-01-02", "committee_name": "위원회", "meeting_number": "제1회",
        "session_number": "제2차", "original": "http://example/1"}
CTX = {"n": 1, "doc_id": "a", "text": "본문", **META}
TURNS = [{"question": "앞 질문", "answer": "앞 답변."}]
# 청크 번호 0~5의 문서: a a b c d e
DOCS = np.array(["a", "a", "b", "c", "d", "e"])


def cfg_with(*args):
    return load_cfg(["index.scope=full", *args])


@pytest.fixture
def cfg():
    return cfg_with()


def test_block_format_keeps_first_question_and_wraps_follow_up(cfg):
    block = OmegaConf.load(ROOT / cfg.app.multiturn.block)
    first = build_messages(cfg.prompt, [CTX], "질문")
    assert build_messages(cfg.prompt, [CTX], "질문", (), block) == first
    msgs = build_messages(cfg.prompt, [CTX], "질문", TURNS, block)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0] == first[0]
    user = msgs[1]["content"]
    assert user.startswith("[앞 대화]") and "질문: 앞 질문\n답변: 앞 답변." in user
    assert user.endswith(first[1]["content"])  # 근거와 질문은 첫 질문과 같은 글이다


def test_pipeline_reads_block_only_when_chosen(cfg):
    assert OmegaConf.load(ROOT / cfg.app.multiturn.block).version
    bad = cfg_with("app.multiturn.format=chat")
    with pytest.raises(SystemExit, match="format"):
        Pipeline(bad)


@pytest.mark.parametrize(("rows", "want"), [
    ([3, 1], [3, 1]),
    ([3, 3, 1], [3, 1]),
    ([5, 4, 3, 2], [5, 4, 3]),  # max_chunks 3
    ([-1, 6, "2", 2.0, True, 2], [2]),  # 범위 밖·글자·실수·불리언은 버린다
    ("3", []), (None, []),
])
def test_last_rows_trusts_only_valid_chunk_numbers(cfg, rows, want):
    history = [{"question": "q", "answer": "a", "rows": [0]}, {"question": "q", "answer": "a",
                                                            "rows": rows}]
    assert app.last_rows(history, cfg, n_chunks=6) == want


@pytest.mark.parametrize("history", [None, [], "글", [1], [{"question": "q", "answer": "a"}]])
def test_last_rows_empty_without_rows(cfg, history):
    assert app.last_rows(history, cfg, n_chunks=6) == []


def reuse_pipe(mode):
    pipe = object.__new__(Pipeline)
    pipe.cfg = cfg_with(f"app.multiturn.reuse.mode={mode}")
    pipe.retriever = SimpleNamespace(dense_ids=DOCS)
    pipe.doc_chunks = chunks_by_doc(DOCS)
    pipe.store = SimpleNamespace(window=lambda i, n: {"doc_id": str(DOCS[i]), "index": "idx",
                                                      "chunk_id": i, "text": f"t{i}",
                                                      "start": 0, "end": 1})
    pipe.expand = SimpleNamespace(top=0, chunks=0)
    pipe.speakers = "off"
    pipe.doc_meta = {d: META for d in DOCS}
    scores = np.array([0.1, 0.9, 0.5, 0.4, 0.3, 0.2])
    stages = [{"rrf_score": 1.0 - k / 10} for k in range(4)]
    pipe.rank = lambda query, q_emb, qid=None: (scores, ["c", "a", "d", "e"], stages)
    return pipe


@pytest.mark.parametrize(("mode", "prev", "docs", "chunks", "reused"), [
    # 앞 근거를 앞자리에 넣고 같은 문서의 이번 근거는 빼고 남은 칸을 채운다. 근거 수는 3 그대로다
    ("decision", [2], ["b", "c", "a"], [2, 3, 1], [True, False, False]),
    ("decision", [0], ["a", "c", "d"], [0, 3, 4], [True, False, False]),
    # rule은 그 문서가 이번 후보에 다시 나올 때만 넣는다(b는 후보 밖)
    ("rule", [2, 0], ["a", "c", "d"], [0, 3, 4], [True, False, False]),
    ("rule", [2], ["c", "a", "d"], [3, 1, 4], [False, False, False]),
])
def test_retrieve_puts_previous_chunks_first_and_renumbers(mode, prev, docs, chunks, reused):
    out = Pipeline.retrieve(reuse_pipe(mode), "q", None, 3, prev=prev)
    assert [c["doc_id"] for c in out] == docs
    assert [c["chunk_id"] for c in out] == chunks
    assert [c["n"] for c in out] == [1, 2, 3]
    assert [c["stages"].get("reused", False) for c in out] == reused


def test_retrieve_without_prev_is_unchanged():
    pipe = reuse_pipe("decision")
    assert Pipeline.retrieve(pipe, "q", None, 3) == Pipeline.retrieve(pipe, "q", None, 3, prev=())
    assert [c["doc_id"] for c in Pipeline.retrieve(pipe, "q", None, 3)] == ["c", "a", "d"]


def fake_pipe(seen):
    def stream(query, q_emb, history=(), search=None, prev=(), langsmith_extra=None):
        seen["prev"] = prev
        ctx = [{**CTX, "n": 1, "index": "idx", "chunk_id": 4}, {**CTX, "n": 2, "doc_id": "b",
                                                                 "index": "idx", "chunk_id": 1}]
        yield {"answer": "답 [2].", "contexts": ctx}

    store = SimpleNamespace(names=["idx"], bounds=np.array([10, 20]))
    return SimpleNamespace(embed=lambda q: q, stream=stream, store=store,
                           index_meta={"n_chunks": 30})


HISTORY = [{"question": "앞 질문", "answer": "앞 답변 [1].", "rows": [12, 99]}]
CORPUS = SimpleNamespace(chunk_span=lambda doc_id, text: (0, 1))


@pytest.mark.parametrize(("mode", "needs", "prev"), [
    ("off", True, []), ("rule", None, [12]), ("rewrite", True, [12]),
    ("rewrite", False, []), ("rewrite", None, []), ("decision", True, [12]),
    ("decision", False, []),
])
def test_chat_events_pass_previous_chunks_by_mode(mode, needs, prev):
    cfg = cfg_with(f"app.multiturn.reuse.mode={mode}")
    seen = {}

    def follow(message, turns):
        return "검색 질의", {"rewrite_status": "ok", "rewrite_s": 0.1, "needs_prev": needs}

    final = list(app.chat_events(fake_pipe(seen), cfg, {}, CORPUS, "후속", HISTORY, follow))[-1]
    assert seen["prev"] == prev  # 99는 n_chunks 밖이라 버린다
    # 이번 답변이 인용한 [2]의 청크 번호(10 + 1)만 페이지에 돌려준다. 끄면 보내지 않는다
    assert final["rows"] == ([] if mode == "off" else [11])


def test_first_question_never_passes_previous_chunks():
    cfg = cfg_with("app.multiturn.reuse.mode=rule")
    seen = {}
    rows_only = [{"question": " ", "answer": "a", "rows": [12]}]  # 질문이 비어 턴이 없다
    list(app.chat_events(fake_pipe(seen), cfg, {}, CORPUS, "첫 질문", rows_only, None))
    assert seen["prev"] == []


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API", "test")


def test_follow_up_checks_mode_and_flag_prompt(env):
    with pytest.raises(SystemExit, match="mode"):
        app.follow_up(cfg_with("app.multiturn.reuse.mode=always"))
    with pytest.raises(SystemExit, match="flag"):
        app.follow_up(cfg_with("app.multiturn.reuse.mode=rewrite"))
    app.follow_up(cfg_with("app.multiturn.reuse.mode=rewrite",
                           "app.multiturn.rewrite.prompt=configs/rewriter/prompt/rwmt_v2.yaml"))


def rewriter_with(reply):
    cfg = cfg_with("app.multiturn.rewrite.prompt=configs/rewriter/prompt/rwmt_v2.yaml")
    rw = FollowUpRewriter(cfg)
    rw.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=reply))]))))
    return rw


@pytest.mark.parametrize(("reply", "query", "needs"), [
    ("검색 질의\n앞 근거: 필요", "검색 질의", True),
    ("검색 질의\n앞 근거: 불필요", "검색 질의", False),
    ("검색 질의", "검색 질의", None),
    ("앞 근거: 필요", "후속", True),  # 표시만 오면 질문 그대로 검색한다
])
def test_rewrite_flag_parses_query_and_needs_prev(env, reply, query, needs):
    got, meta = rewriter_with(reply)("후속", TURNS)
    assert got == query and meta["needs_prev"] is needs


@pytest.mark.parametrize(("reply", "status", "needs"), [
    ({"answers": {"prev": {"noul": 0.8}}}, "ok", True),
    ({"answers": {"prev": {"noul": 0.2}}}, "ok", False),
    (TimeoutError("시간 초과"), "TimeoutError", False),
    ({"error": "모델 없음"}, "KeyError", False),
])
def test_decider_failure_does_not_reuse(env, monkeypatch, reply, status, needs):
    sent = []

    def urlopen(req, timeout):
        sent.append((json.loads(req.data), timeout))
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(json.dumps(reply).encode("utf-8"))

    monkeypatch.setattr("rag.rewrite.urllib.request.urlopen", urlopen)
    cfg = cfg_with("app.multiturn.reuse.mode=decision")
    meta = PrevDecider(cfg)("후속", TURNS)
    assert meta["decision_status"] == status and meta["needs_prev"] is needs
    body, timeout = sent[0]
    d = cfg.app.multiturn.reuse.decision
    assert body["model"] == d.model and timeout == d.timeout_s
    assert body["state"]["후속 질문"] == "후속" and "앞 답변." in body["state"]["앞 대화"]


def test_decision_runs_alongside_rewrite(env, monkeypatch):
    cfg = cfg_with("app.multiturn.reuse.mode=decision")
    monkeypatch.setattr(FollowUpRewriter, "__call__",
                        lambda self, m, t: ("검색", {"rewrite_status": "ok", "rewrite_s": 0.1}))
    monkeypatch.setattr(PrevDecider, "__call__",
                        lambda self, m, t: {"decision_status": "ok", "decision_s": 0.2,
                                            "decision_prob": 0.9, "needs_prev": True})
    search, meta = app.follow_up(cfg)("후속", TURNS)
    assert search == "검색" and meta["needs_prev"] is True and meta["rewrite_status"] == "ok"


@pytest.mark.parametrize(("raw", "prev", "uncited", "repeat"), [
    ("A는 답했습니다 [1].", None, False, None),
    ("A는 답했습니다.", None, True, None),
    ("A는 답했습니다 [1].", "A는 답했습니다 [3].", False, True),
    ("A는 답했습니다 [1]. 자세한 내용은 제공된 회의록에서 답을 찾지 못했습니다.",
     "A는 답했습니다 [3].", False, False),  # 되풀이여도 거부 문장이 있으면 위반이 아니다
    ("B는 다른 말을 길게 했습니다 [2].", "A는 답했습니다 [3].", False, False),
])
def test_checks_find_uncited_and_repeated_answers(cfg, raw, prev, uncited, repeat):
    out = multiturn_check.checks(cfg, raw, prev, 5)
    assert out["uncited"] is uncited
    assert out.get("repeat") is repeat


def test_reading_doc_has_only_questions_and_shown_answers():
    rows = [{"cid": "c01", "turn": 1, "q": "질문", "shown": "답변(회의)", "raw": "원문 [1]",
             "contexts": [{"doc_id": "a"}], "checks": {}}]
    doc = multiturn_check.reading_doc(rows)
    assert "질문" in doc and "답변(회의)" in doc
    assert "원문" not in doc and "doc_id" not in doc
