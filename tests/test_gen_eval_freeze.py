"""생성 평가 모듈 동결 점검(S23, D-49). 동결한 judge 지시와 판정표가 바뀌면 실패한다.

지시를 바꾸려면 새 버전 파일(j_v9 등)을 만들고 여기 기대값과 D-49를 함께 고친다(기준 문서 P1).
실행 설정(사고 과정, max_tokens)은 변동 폭 측정에서 정하므로 점검하지 않는다(S23 결정 사항 2).
"""

from omegaconf import OmegaConf

from rag.gen_eval.checks import HANDLINGS, OUTCOMES, STATES, item_outcome
from rag.gen_eval.judge import sha
from rag.index import load_cfg

FROZEN_PROMPT = "j_v8"
FROZEN_PROMPT_SHA256 = "fc8b56034f35d1809db92f1ce5cdf250f09773c11f407379088a40da86bd4de8"
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
