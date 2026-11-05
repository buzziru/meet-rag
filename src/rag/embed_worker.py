"""질의 임베딩 전용 프로세스(S39). Space 앱이 띄우고 표준 입출력으로 주고받는다.

ZeroGPU의 GPU 작업자는 메인 프로세스에서 포크된다. 메인에서 torch로 임베딩을 계산하면 작업자가
"No CUDA GPUs are available"로 멈춰서(S39 결과 절) 계산을 다른 프로세스로 옮긴다. 모델과 계산은
rag.index 그대로라 값이 같다.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import numpy as np


def serve(encode, lines: TextIO, out: TextIO) -> None:
    """한 줄에 질의 하나(JSON 문자열)를 받아 float32 벡터를 base64 한 줄로 돌려준다."""
    for line in lines:
        vec = encode([json.loads(line)])[0]
        out.write(base64.b64encode(vec.astype(np.float32).tobytes()).decode("ascii") + "\n")
        out.flush()


class EmbedProcess:
    """임베딩 프로세스를 띄워 질의를 벡터로 바꾼다. 앱은 질의를 하나씩 처리한다(app.concurrency).
    프로세스가 죽으면 오류를 낸다. 답변이 조용히 달라지지 않게 대체 경로를 두지 않는다."""

    def __init__(self, overrides: list[str], command: list[str] | None = None):
        src = str(Path(__file__).parents[1])
        self.process = subprocess.Popen(
            command or [sys.executable, "-m", "rag.embed_worker", *overrides],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONPATH": src})

    def __call__(self, query: str) -> np.ndarray:
        self.process.stdin.write(json.dumps(query, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"임베딩 프로세스가 끝났다(코드 {self.process.poll()})")
        return np.frombuffer(base64.b64decode(line), dtype=np.float32)


def main() -> None:
    from rag.index import encoder, load_cfg, load_model

    # 라이브러리 출력이 응답 줄에 섞이지 않게 표준 출력을 응답 전용으로 떼어 낸다
    out = os.fdopen(os.dup(1), "w", encoding="ascii")
    os.dup2(2, 1)
    cfg = load_cfg(sys.argv[1:])
    model = load_model(cfg, cfg.embedding.query_max_tokens)
    serve(encoder(model, cfg, cfg.embedding.get("query_prompt")), sys.stdin, out)


if __name__ == "__main__":
    main()
