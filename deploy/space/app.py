"""Space 진입점(docs/slices/38-hf-space.md). rag.app을 재정렬을 끈 구성으로 시작한다.

ZeroGPU는 @spaces.GPU 함수가 없으면 시작 때 멈춘다. S38은 GPU를 쓰지 않아 부르지 않는 함수만 둔다.
spaces는 torch보다 먼저 불러온다.
"""

import spaces  # isort: skip

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rag.app import main  # noqa: E402

OVERRIDES = ["+exp=current", "retriever.rerank.enabled=false", "deploy.speakers_from_file=true"]
PEAK = Path("/sys/fs/cgroup/memory.peak")


@spaces.GPU
def unused() -> None:
    pass


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
    main()
