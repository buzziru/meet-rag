"""후속 질문 재작성(S40). 외부 API 없이 합성 클라이언트로 생성자부터 지나 본다."""

from types import SimpleNamespace

import openai
import pytest

from rag.index import load_cfg
from rag.rewrite import FollowUpRewriter

TURNS = [{"question": "2019년 국토위에서 광역버스 얘기가 나왔나요?",
          "answer": "차관은 단계적으로 도입하겠다고 답했습니다."}]


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API", "test")
    return load_cfg(["index.scope=full", "+exp=current"])


def rewriter_with(cfg, reply):
    """reply가 예외면 호출에서 던지고, 글자면 그 응답을 돌려주는 재작성기와 받은 요청."""
    rw = FollowUpRewriter(cfg)
    sent = []

    def create(**kw):
        sent.append(kw)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    rw.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return rw, sent


def test_rewrite_uses_generator_model_and_turns(cfg):
    rw, sent = rewriter_with(cfg, "2019년 국토교통위원회 광역버스 예산\n설명")
    query, meta = rw("예산은?", TURNS)
    assert query == "2019년 국토교통위원회 광역버스 예산"
    assert meta["rewrite_status"] == "ok" and meta["rewrite_prompt"] == "rwmt_v1"
    g = cfg.generator
    kw = sent[0]
    assert kw["model"] == g.model and kw["extra_body"]["provider"] == dict(g.extra_body.provider)
    assert kw["max_tokens"] == cfg.app.multiturn.rewrite.max_tokens
    user = kw["messages"][1]["content"]
    assert TURNS[0]["question"] in user and TURNS[0]["answer"] in user
    assert user.rstrip().endswith("후속 질문: 예산은?\n검색 질의:")


@pytest.mark.parametrize(("reply", "status"), [
    (openai.APITimeoutError(request=None), "APITimeoutError"),
    (RuntimeError("연결 끊김"), "RuntimeError"),
    ("", "invalid"),
    ("가" * 1000, "invalid"),  # 재작성 질의 길이 상한을 넘는다
])
def test_rewrite_failure_searches_question_as_is(cfg, reply, status):
    rw, _ = rewriter_with(cfg, reply)
    query, meta = rw("예산은?", TURNS)
    assert query == "예산은?" and meta["rewrite_status"] == status
