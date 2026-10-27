"""노트북 셀을 지속 커널에서 실행한다. 실패하면 고친 셀부터 이어서 실행한다(ADR-0013).

nbclient는 실행마다 커널을 새로 띄워, 한 셀이 실패하면 처음부터 다시 돌려야 했다
(S6 노트북은 API 호출 셀이 있어 일곱 번 다시 실행했다). 여기서는 커널을 백그라운드에
띄워 두고 셀을 하나씩 실행하므로 앞 셀의 상태가 남는다.

사용 (저장소 루트에서):
  doppler run -- uv run python .claude/skills/meet-rag/scripts/nb_kernel.py start
  ... run notebooks/X.ipynb [--from N] [--to M]   # N·M은 0부터 센 셀 번호(마크다운 포함)
  ... stop
  (start만 `doppler run --`으로 띄운다. 커널이 그 환경의 API 키와 HF_HOME을 물려받는다)

- 커널 작업 디렉터리는 notebooks/다(노트북 규약 ROOT = Path.cwd().parent)
- run은 먼저 `ruff check --fix`를 노트북에 적용하고 남은 지적을 출력한다(PR 전 ruff 오류를
  따로 고치지 않게). 줄 길이와 `ruff format`은 노트북에 적용하지 않는다. 사람이 읽는 기록이라
  기계적 줄 나눔이 가독성을 낮춰, 노트북 규약 §2.3이 맡는다(ADR-0063)
- run은 셀마다 출력을 노트북 파일에 LF로 쓰고, 오류가 난 셀에서 멈추며 그 셀 번호와 traceback
  끝 TB_LINES줄을 알려 준다(전체 traceback은 노트북 출력에 남는다)
- 끝나면 stop으로 커널을 내린다
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from jupyter_client import BlockingKernelClient

ROOT = Path(__file__).resolve().parents[4]
CONN = ROOT / "_workspace" / "nb_kernel.json"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TB_LINES = 15


def client() -> BlockingKernelClient:
    if not CONN.exists():
        sys.exit("커널이 없다. 먼저 start")
    kc = BlockingKernelClient(connection_file=str(CONN))
    kc.load_connection_file()
    kc.start_channels()
    kc.wait_for_ready(timeout=60)
    return kc


def start() -> None:
    if CONN.exists():
        sys.exit(f"이미 커널이 있다({CONN}). 쓰지 않는 커널이면 stop")
    CONN.parent.mkdir(exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    log = (CONN.parent / "nb_kernel.log").open("w", encoding="utf-8")
    subprocess.Popen([sys.executable, "-m", "ipykernel_launcher", "-f", str(CONN)],
                     cwd=ROOT / "notebooks", stdout=log, stderr=log, creationflags=flags)
    for _ in range(60):
        if CONN.exists() and CONN.stat().st_size:
            break
        time.sleep(1)
    client().stop_channels()
    print(f"kernel ready ({CONN.relative_to(ROOT)})")


def execute(kc: BlockingKernelClient, code: str) -> tuple[list[dict], int | None, bool]:
    """셀 하나를 실행해 (nbformat 출력 목록, 실행 번호, 오류 여부)를 돌려준다."""
    msg_id = kc.execute(code)
    outputs = []
    while True:
        msg = kc.get_iopub_msg()
        if msg["parent_header"].get("msg_id") != msg_id:
            continue
        kind, c = msg["msg_type"], msg["content"]
        if kind == "status" and c["execution_state"] == "idle":
            break
        if kind == "stream":
            if outputs and outputs[-1]["output_type"] == "stream" \
                    and outputs[-1]["name"] == c["name"]:
                outputs[-1]["text"] += c["text"]
            else:
                outputs.append({"output_type": "stream", "name": c["name"], "text": c["text"]})
        elif kind in ("execute_result", "display_data"):
            out = {"output_type": kind, "data": c["data"], "metadata": c.get("metadata", {})}
            if kind == "execute_result":
                out["execution_count"] = c["execution_count"]
            outputs.append(out)
        elif kind == "error":
            outputs.append({"output_type": "error", "ename": c["ename"],
                            "evalue": c["evalue"], "traceback": c["traceback"]})
        elif kind == "clear_output":
            outputs = []
    reply = kc.get_shell_msg(timeout=60)["content"]
    return outputs, reply.get("execution_count"), reply["status"] == "error"


def lint(path: Path) -> None:
    out = subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", "--quiet", str(path)],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        print(out.stdout + out.stderr)


def error_tail(outputs: list[dict]) -> str:
    """오류 출력의 traceback 끝 TB_LINES줄(ANSI 제거). 오류 출력이 없으면 그렇다고 적는다."""
    err = next((o for o in outputs if o["output_type"] == "error"), None)
    if err is None:
        return "오류 출력이 없다(커널이 응답만 error로 보냄)"
    lines = ANSI.sub("", "\n".join(err["traceback"])).splitlines()
    return "\n".join(lines[-TB_LINES:])


def run(path: Path, first: int, last: int | None) -> None:
    lint(path)
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = nb["cells"]
    last = len(cells) - 1 if last is None else last
    kc = client()
    try:
        for i in range(first, last + 1):
            cell = cells[i]
            if cell["cell_type"] != "code":
                continue
            src = cell["source"]
            outputs, count, failed = execute(kc, "".join(src) if isinstance(src, list) else src)
            cell["outputs"], cell["execution_count"] = outputs, count
            path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
            if failed:
                print(error_tail(outputs))
                sys.exit(f"셀 {i}에서 오류. 고친 뒤 run {path} --from {i}")
            print(f"[{i}] ok")
    finally:
        kc.stop_channels()


def stop() -> None:
    if not CONN.exists():
        print("커널이 없다")
        return
    try:
        client().shutdown()
    finally:
        CONN.unlink(missing_ok=True)
    print("kernel stopped")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    r = sub.add_parser("run")
    r.add_argument("notebook", type=Path)
    r.add_argument("--from", dest="first", type=int, default=0)
    r.add_argument("--to", dest="last", type=int)
    a = p.parse_args()
    if a.cmd == "run":
        run(a.notebook.resolve(), a.first, a.last)
    else:
        {"start": start, "stop": stop}[a.cmd]()


if __name__ == "__main__":
    main()
