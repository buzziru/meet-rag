"""테스트 세션 공통 준비(S30, 테스트 리뷰 T1-3).

같은 override로 Hydra config를 조립하는 테스트가 많다(1회 약 0.3초, 전체 약 100회). config
파일은 테스트 중에 바뀌지 않으므로 override별로 한 번만 조립하고, 복사본을 돌려줘 테스트끼리
섞이지 않게 한다. git_state는 레시피마다 git을 두 번 부른다(0.17초). 세션 동안 HEAD와 작업
트리는 같으므로 한 번만 부른다. 이 파일은 테스트 모듈과 그 모듈이 부르는 rag 모듈보다 먼저
불러와지므로 `from rag.index import load_cfg`도 이것을 받는다.
"""

import copy
from functools import cache

import rag.index

_compose = rag.index.load_cfg


@cache
def _composed(overrides: tuple[str, ...]):
    return _compose(overrides)


def load_cfg(overrides=()):
    return copy.deepcopy(_composed(tuple(overrides)))


rag.index.load_cfg = load_cfg
rag.index.git_state = cache(rag.index.git_state)
