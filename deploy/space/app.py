"""Space 진입점(docs/slices/38-hf-space.md, 39-zerogpu-rerank.md). rag.app을 재정렬과 함께 시작한다.

리랭커는 HF 문서 권장대로 모듈 수준에서 GPU로 올리고, 점수 함수를 @spaces.GPU로 감싼다. 채팅 처리는
Space 시크릿의 소유자 토큰으로 같은 Space의 점수 함수를 불러 소유자 할당량을 쓴다(S39 결정 5).
spaces는 torch보다 먼저 불러온다.
"""

import spaces  # isort: skip

import sys
import threading
import time
from pathlib import Path

BEGIN = time.perf_counter()
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gradio_client import Client  # noqa: E402

from rag.app import main  # noqa: E402
from rag.index import load_cfg, require_env  # noqa: E402
from rag.rerank import load_model  # noqa: E402

OVERRIDES = ["+exp=current", "deploy.speakers_from_file=true", "retriever.rerank.device=cuda",
             "retriever.rerank.dtype=float16"]
PEAK = Path("/sys/fs/cgroup/memory.peak")

CFG = load_cfg(["index.scope=full", *OVERRIDES])
IMPORTED = time.perf_counter()
RERANK = CFG.retriever.rerank
MODEL = load_model(RERANK)
print(f"시작: 모듈 불러오기 {IMPORTED - BEGIN:.1f}초, "
      f"리랭커 {time.perf_counter() - IMPORTED:.1f}초", flush=True)


@spaces.GPU(duration=CFG.deploy.rerank.gpu_seconds)
def score_pairs(pairs: list[list[str]]) -> list[float]:
    """[질의, 청크] 쌍의 점수. rag.rerank의 점수 파일과 같은 호출이다."""
    return MODEL.predict([tuple(p) for p in pairs], batch_size=RERANK.batch_size).tolist()


class OwnerScorer:
    """소유자 토큰으로 점수 함수를 부른다. Space가 뜬 뒤에야 연결되므로 첫 호출 때 연다."""

    client = None

    def __init__(self):
        # 시크릿이 없으면 시작할 때 멈춘다. 호출 때 알면 모든 질의가 재정렬 없이 조용히 나간다
        self.token = require_env(CFG.deploy.rerank.token_env)

    def __call__(self, pairs: list[list[str]]) -> list[float]:
        d = CFG.deploy
        if self.client is None:
            self.client = Client(d.space, token=self.token, verbose=False)
        job = self.client.submit(pairs, api_name=f"/{d.rerank.api_name}")
        return job.result(timeout=d.rerank.timeout_s)


def log_memory() -> None:
    """최고 메모리를 1분마다 로그에 남긴다."""
    begin = time.perf_counter()
    while True:
        time.sleep(60)
        print(f"메모리 최고 {int(PEAK.read_text()) / 1e9:.2f}GB, "
              f"{time.perf_counter() - begin:.0f}초 경과", flush=True)


if __name__ == "__main__":
    threading.Thread(target=log_memory, daemon=True).start()
    sys.argv = [sys.argv[0], *OVERRIDES]
    main(endpoint=score_pairs, scorer=OwnerScorer())
