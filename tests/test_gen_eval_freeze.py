"""생성 평가 모듈 동결 점검(S23, D-49). 동결한 judge 지시와 판정표, 형식 재요청 절차(D-58), judge
요청 본문 렌더링과 관련성 점수표(S28, 리뷰 G1-3)가 바뀌면 실패한다.

지시를 바꾸려면 새 버전 파일(j_v9 등)을 만들고 여기 기대값과 D-49를 함께 고친다(기준 문서 P1).
실행 설정(사고 과정, max_tokens)은 변동 폭 측정에서 정하므로 따로 점검하지 않는다(S23 결정 사항 2).
다만 요청 본문 sha256은 기본 judge 설정의 model·params·extra_body·step_params를 담아,
이 값이 바뀌어도
실패한다(D-50에서 실행 설정도 고정했다).
"""

import json
import threading
from types import SimpleNamespace

from omegaconf import OmegaConf

from rag.gen_eval.checks import HANDLINGS, OUTCOMES, STATES, item_outcome
from rag.gen_eval.judge import RELEVANCE, Judge, judge_record, sha
from rag.index import load_cfg

FROZEN_PROMPT = "j_v8"
FROZEN_PROMPT_SHA256 = "fc8b56034f35d1809db92f1ce5cdf250f09773c11f407379088a40da86bd4de8"
FROZEN_FORMAT_RETRY = "fr_v1"
FROZEN_FORMAT_RETRY_SHA256 = "95edd01f8bba4b487f7c57044e07f59de161257b5e0af43694b6d7b2a838042c"
FROZEN_FORMAT_RETRY_LIMIT = 1
FROZEN_OUTCOMES = {
    ("있음", "답함"): "맞음",
    ("있음", "부분임을 밝히고 답함"): "불필요한 부분 안내",
    ("있음", "거부"): "과잉 거부",
    ("있음", "다루지 않음"): "누락",
    ("일부", "답함"): "안내 없이 부분 답함",
    ("일부", "부분임을 밝히고 답함"): "맞음",
    ("일부", "거부"): "과잉 거부",
    ("일부", "다루지 않음"): "누락",
    ("없음", "답함"): "근거 없이 답함",
    ("없음", "부분임을 밝히고 답함"): "근거 없이 답함",
    ("없음", "거부"): "맞음",
    ("없음", "다루지 않음"): "무언 생략",
}


def test_default_judge_prompt_is_frozen_j_v8():
    prompt = load_cfg(["index.scope=full"]).judge.prompt
    assert prompt.version == FROZEN_PROMPT
    # judge_recipe의 prompt_sha256과 같은 계산이다
    assert sha(OmegaConf.to_container(prompt, resolve=True)) == FROZEN_PROMPT_SHA256


def test_outcome_table_is_frozen():
    assert OUTCOMES == FROZEN_OUTCOMES
    # 판정표 전체(5 상태 × 5 처리, 기준 문서 I8): 모호·회피는 상황 전달·미전달, 있음·일부·없음의
    # "상황을 밝히고 답함"은 답함과 같다
    for state in STATES:
        for handling in HANDLINGS:
            if state in ("모호", "회피"):
                want = "상황 전달" if handling == "상황을 밝히고 답함" else "상황 미전달"
            else:
                same = "답함" if handling == "상황을 밝히고 답함" else handling
                want = FROZEN_OUTCOMES[state, same]
            assert item_outcome(state, handling) == want, (state, handling)


def test_format_retry_is_frozen():
    retry = load_cfg(["index.scope=full"]).judge.format_retry
    assert retry.version == FROZEN_FORMAT_RETRY and retry.limit == FROZEN_FORMAT_RETRY_LIMIT
    # judge_recipe의 format_retry_sha256과 같은 계산이다
    assert sha(OmegaConf.to_container(retry)) == FROZEN_FORMAT_RETRY_SHA256


def test_relevance_scores_are_frozen():
    assert RELEVANCE == {"답함": 1.0, "일부": 0.5, "답하지 않음": 0.0}


# 고정한 합성 입력(지어낸 것, AI Hub 데이터 아님)의 judge 단계별 요청 본문 sha256. format_contexts·
# json.dumps 같은 judge 입력 렌더링이나 기본 judge 설정이 바뀌면 실패한다(리뷰 G1-3)
FROZEN_REQUEST_SHA256 = {
    "chunk_checks": "f74635e5afc2130426d25c44f42718d97d3e7aff562c9845048e07490d6a01dd",
    "item_handling": "d9c188f5c403d4881988b0d20a24ee223a799aa07c4b41d66cca05e5119ada99",
    "items": "a29ef41b149c69138b96b553218e392069a9457521fc615a343cf4964f63f530",
    "key_checks": "c61459768eb725966482ff2fe12be27ae99defc489fc935e02f3f3d3aa199309",
    "key_statements": "36e1161b74910f7aac4cdbc357e967f580098748445de787ba08e83cc8a72a3a",
    "relevance": "e773dab6a93abdcc732eae2a1a2e612cb8437f7fddfa4ec12982a76e26996ef7",
    "statements": "fec6d9fcdcc6a70aa4e3455ba2179ed1bb612fb26a87535b6ada48dd118876e4",
    "verdicts": "9c6f0a5b28ea24a7648899cd4b958a0d00f9c8e08d14214b26892d32a1a1f012",
}
CONTEXTS = [{"n": 1, "doc_id": "d1", "date": "2020년1월2일", "committee_name": "가위원회",
             "meeting_number": "제1회", "session_number": "제2차",
             "text": "장관은 내년에 예산을 늘리겠다고 답했다."},
            {"n": 2, "doc_id": "d2", "date": "2021년3월4일", "committee_name": "나위원회",
             "meeting_number": "제3회", "session_number": "제1차",
             "text": "위원은 지원 대상을 물었다."}]
REPLIES = {
    "statements": {"statements": ["장관은 내년에 예산을 늘리겠다고 답했다."]},
    "verdicts": {"verdicts": [{"statement": "장관은 내년에 예산을 늘리겠다고 답했다.",
                               "reason": "r", "verdict": 1, "speaker_unclear": False}]},
    "relevance": {"label": "답함", "reason": "r"},
    "key_statements": {"key_statements": ["예산을 늘린다."]},
    "key_checks": {"checks": [{"statement": "예산을 늘린다.", "reason": "r", "present": 1}]},
    "chunk_checks": {"checks": [{"statement": "예산을 늘린다.", "reason": "r", "present": 1}]},
    "items": {"items": [{"item": "예산 계획", "state": "있음", "speaker_unclear": False}]},
    "item_handling": {"handling": [{"n": 1, "handling": "답함", "reason": "r"}]},
}


def request_shas(tmp_path) -> dict[str, str]:
    """기본 설정의 Judge로 합성 기록 하나를 채점하며 단계별로 보낸 요청 본문의 sha256을 모은다.
    API 대신 단계마다 정한 응답을 돌려준다."""
    cfg = load_cfg(["index.scope=full"])
    systems = {cfg.judge.prompt[s].system: s for s in REPLIES}
    sent = {}

    def create(**kw):
        step = systems[kw["messages"][0]["content"]]
        sent[step] = sha(kw)
        msg = SimpleNamespace(content=json.dumps(REPLIES[step], ensure_ascii=False))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=None)

    j = object.__new__(Judge)
    j.j, j.prompt, j.rep, j.retry = cfg.judge, cfg.judge.prompt, 0, cfg.judge.format_retry
    j.params = OmegaConf.to_container(cfg.judge.params)
    j.extra = OmegaConf.to_container(cfg.judge.extra_body) if cfg.judge.extra_body else None
    j.step = OmegaConf.to_container(cfg.judge.step_params)
    j.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    j.cache, j.lock, j.calls, j.hits = tmp_path, threading.Lock(), 0, 0
    gen = {"qid": "q1", "query": "내년 예산 계획은?",
           "answer": "장관은 내년에 예산을 늘리겠다고 답했다[1].", "contexts": CONTEXTS,
           "usage": None, "provider": "p", "first_token_s": 1.0, "total_s": 2.0}
    ref = {"doc_id": "d1", "answer_comment": "예산을 늘리겠습니다."}
    out = judge_record.__wrapped__(j, gen, ref, cfg, {"가위원회", "나위원회"})
    assert out["faithfulness"]["score"] == 1.0 and out["answer_in_chunk"] is True
    return sent


def test_judge_request_bodies_are_frozen(tmp_path):
    assert request_shas(tmp_path) == FROZEN_REQUEST_SHA256
