"""Space 진입점(docs/slices/38-hf-space.md, 39-zerogpu-rerank.md). rag.app을 재정렬과 함께 시작한다.

리랭커는 HF 문서 권장대로 모듈 수준에서 GPU로 올리고, 점수 함수를 @spaces.GPU로 감싼다. 채팅 처리는
Space 시크릿의 소유자 토큰으로 같은 Space의 점수 함수를 불러 소유자 할당량을 쓴다(S39 결정 5).
질의 임베딩은 별도 프로세스에서 한다(rag.embed_worker).
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
from huggingface_hub import snapshot_download  # noqa: E402

from rag.app import main  # noqa: E402
from rag.embed_worker import EmbedProcess  # noqa: E402
from rag.index import COMMIT, ROOT, load_cfg, require_env  # noqa: E402
from rag.rerank import load_model  # noqa: E402

OVERRIDES = ["+exp=current", "deploy.speakers_from_file=true", "retriever.rerank.device=cuda",
             "retriever.rerank.dtype=float16"]
PEAK = Path("/sys/fs/cgroup/memory.peak")

CFG = load_cfg(["index.scope=full", *OVERRIDES])
if not COMMIT.fullmatch(CFG.deploy.dataset_revision):
    raise SystemExit(f"deploy.dataset_revision은 커밋 해시여야 한다: {CFG.deploy.dataset_revision}")
if not CFG.deploy.rerank.enabled:
    OVERRIDES.append("retriever.rerank.enabled=false")
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
        self.token = require_env(CFG.deploy.token_env)

    def __call__(self, pairs: list[list[str]]) -> list[float]:
        d = CFG.deploy
        if self.client is None:
            self.client = Client(d.space, token=self.token, verbose=False)
            # Gradio 이벤트 안에서 부르면 클라이언트가 방문자 요청의 x-ip-token을 자기 헤더에
            # 복사해 둔다. 그러면 소유자 토큰이 있어도 방문자(공개 뒤 익명) 할당량으로 매겨져
            # 몇 번 뒤 "runs limit"으로 막혔다(S41 공개 직후). 소유자 할당량을 쓰려고(D-84
            # 결정 2) 복사하지 않는다
            self.client.add_zero_gpu_headers = lambda headers: headers
        job = self.client.submit(pairs, api_name=f"/{d.rerank.api_name}")
        return job.result(timeout=d.rerank.timeout_s)


def download_data() -> None:
    """비공개 Dataset을 앱이 읽는 data/로 내려받는다. 볼륨보다 빨라 콜드 스타트가 짧다(S39 결과 절).
    디스크는 재시작하면 지워져 시작할 때마다 받는다."""
    start = time.perf_counter()
    d = CFG.deploy
    snapshot_download(d.dataset, repo_type="dataset", revision=d.dataset_revision,
                      local_dir=ROOT / "data", token=require_env(d.token_env))
    print(f"시작: 데이터 내려받기 {time.perf_counter() - start:.1f}초", flush=True)


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
    # 모델 적재는 인덱스 적재와 함께 진행된다. 메인에서 임베딩하면 GPU 작업자가 멈춘다(embed_worker)
    embedder = EmbedProcess(["index.scope=full", *OVERRIDES])
    download_data()
    scorer = OwnerScorer() if CFG.deploy.rerank.enabled else None
    main(endpoint=score_pairs, scorer=scorer, embedder=embedder)
