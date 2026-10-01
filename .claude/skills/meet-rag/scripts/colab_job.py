"""meet-rag Colab 작업 보조 스크립트 (meet-rag 스킬 E절).

로컬 Windows에서 colab CLI를 직접 부를 때 반복해 생긴 함정을 여기서 막는다.
- Git Bash가 `/content/...` 인자를 Windows 경로로 바꾼다
  → Python subprocess로 colab.exe를 직접 부른다
- 로컬 콘솔(cp949)이 VM 출력(진행 막대 등)을 못 써서 실패한다 → UTF-8로 받아 오류 문자는 바꿔 쓴다
- 미push 커밋은 VM에서 체크아웃할 수 없고, config override 오타는 VM에서야 드러난다
  → preflight에서 막는다
- Colab 기본 Python(3.13)이 `requires-python ==3.12`와 맞지 않는다
  → VM에 uv를 깔고 `uv sync`로 lock 그대로 맞춘다
- colab exec는 20분 전후로 끊길 수 있다 → 긴 작업은 VM 안 nohup으로 띄우고 짧은 exec로 로그를 본다
- tar는 `C:` 경로를 원격 호스트로 해석한다 → 압축 해제는 Python tarfile로 한다

사용 (저장소 루트에서):
  uv run python .claude/skills/meet-rag/scripts/colab_job.py preflight [override ...]
  ... setup  -s 세션 --commit SHA
  ... upload -s 세션 로컬파일 VM경로(저장소 기준)      # 큰 파일은 gzip으로 보내 VM에서 푼다
  ... launch -s 세션 -- uv-run-인자...   # 예: -- python -m rag.index index.scope=full
  ... poll   -s 세션 [--interval 180] [--max-polls 40]
  ... fetch  -s 세션 VM경로(저장소 기준) [--to .]
  ... finish -s 세션
"""

import argparse
import gzip
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPO_URL = "https://github.com/buzziru/meet-rag.git"
VM_REPO = "/content/meet-rag"
LOG = "/content/job.log"
DONE, FAIL = "JOB_DONE", "JOB_FAILED"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "MSYS_NO_PATHCONV": "1"}
NOISE = re.compile(
    r"new version of Colab CLI|colab update|pip install --upgrade|silence this check"
)


def colab(*args, stdin=None, check=True) -> str:
    r = subprocess.run(["colab", *args], input=stdin, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    out = "\n".join(line for line in (r.stdout + r.stderr).splitlines() if not NOISE.search(line))
    if check and r.returncode != 0:
        sys.exit(f"colab {' '.join(args[:2])} 실패 (코드 {r.returncode}):\n{out}")
    return out.strip()


def vm_sh(session: str, cmd: str, check=True) -> str:
    """VM에서 셸 명령을 실행하고 출력을 돌려준다. 짧은 명령에만 쓴다."""
    code = ("import subprocess\n"
            f"r = subprocess.run({cmd!r}, shell=True, capture_output=True, text=True)\n"
            "print(r.stdout + r.stderr)\n"
            "print('EXIT', r.returncode)\n")
    out = colab("exec", "-s", session, stdin=code)
    m = re.search(r"EXIT (\d+)\s*$", out)
    if check and (not m or m.group(1) != "0"):
        sys.exit(f"VM 명령 실패: {cmd}\n{out}")
    return re.sub(r"\nEXIT \d+\s*$", "", out)


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def preflight(overrides: list[str]) -> None:
    """HEAD가 push됐는지, config override가 compose되는지 VM을 쓰기 전에 확인한다."""
    head = git("rev-parse", "HEAD")
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("커밋하지 않은 변경이 있다. VM은 커밋된 코드만 받는다")
    git("fetch", "-q", "origin")
    if not git("branch", "-r", "--contains", head):
        sys.exit(f"HEAD {head[:7]}가 원격에 없다. push한 뒤 다시 실행한다")
    sys.path.insert(0, str(ROOT / "src"))
    from rag.index import load_cfg

    load_cfg(overrides)  # 키 오타는 여기서 ConfigCompositionException으로 멈춘다
    print(f"ok: HEAD {head[:7]} 원격에 있음, override {overrides or '없음'} compose 통과")


def start_bg(session: str, cmd: str) -> None:
    """VM 안에서 nohup으로 띄운다. exec 연결이 끊겨도 작업은 계속된다."""
    wrapped = f"({cmd}) && echo {DONE} || echo {FAIL}"
    vm_sh(session, f"nohup bash -c {shlex.quote(wrapped)} > {LOG} 2>&1 &")


def setup(session: str, commit: str) -> None:
    """커밋 clone과 uv sync(Python 3.12, uv.lock)를 VM 안에서 띄우고 끝날 때까지 본다."""
    print(vm_sh(session, "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"))
    start_bg(session, (
        f"rm -rf {VM_REPO} && git clone -q {REPO_URL} {VM_REPO} && cd {VM_REPO} "
        f"&& git checkout -q {commit} && git log --oneline -1 "
        "&& pip install -q uv && uv sync -q --extra cu126 "
        "&& .venv/bin/python -c 'import sys, torch, transformers, sentence_transformers as s;"
        " print(sys.version.split()[0], torch.__version__, torch.cuda.is_available(),"
        " transformers.__version__, s.__version__)'"
    ))
    poll(session, interval=30, max_polls=40)


def blocked(path: str) -> bool:
    """평가 질의(queries_*), 분할(queries.csv), 자격증명(.env)은 VM에 올리지 않는다.

    질의 임베딩은 로컬에서 한다(SPEC 누수 방지). dev_small_docs.txt 같은 문서 목록은 허용한다.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name in (".env", "queries.csv") or name.startswith("queries_")


def upload(session: str, local: str, remote: str) -> None:
    src = Path(local)
    if blocked(local) or blocked(remote):
        sys.exit(f"올리지 않는 파일이다(질의·분할·.env): {local}")
    target = f"{VM_REPO}/{remote}"
    vm_sh(session, f"mkdir -p {shlex.quote(str(Path(target).parent.as_posix()))}")
    if src.stat().st_size > 20_000_000:  # 큰 파일은 압축해 보낸다(159MB 코퍼스 → 73MB)
        with tempfile.TemporaryDirectory() as tmp:
            gz = Path(tmp) / (src.name + ".gz")
            with src.open("rb") as f, gzip.open(gz, "wb") as g:
                shutil.copyfileobj(f, g)
            print(colab("upload", "-s", session, str(gz), target + ".gz"))
        vm_sh(session, f"gunzip -f {shlex.quote(target)}.gz")
    else:
        print(colab("upload", "-s", session, str(src), target))
    print(vm_sh(session, f"wc -lc {shlex.quote(target)}"))


def launch(session: str, uv_args: list[str]) -> None:
    start_bg(session, f"cd {VM_REPO} && date && uv run --extra cu126 {shlex.join(uv_args)}")
    print(f"launched: {shlex.join(uv_args)}  (로그 {LOG})")


def poll(session: str, interval: int, max_polls: int) -> None:
    for _ in range(max_polls):
        tail = vm_sh(session, f"tail -c 2000 {LOG} | tr '\\r' '\\n' | tail -5", check=False)
        print(time.strftime("[%H:%M:%S]"), tail.splitlines()[-1] if tail else "", flush=True)
        if DONE in tail or FAIL in tail:
            print(tail)
            if FAIL in tail:
                sys.exit("작업 실패. 로그를 확인한다")
            return
        time.sleep(interval)
    sys.exit("최대 확인 횟수를 넘었다. 작업은 VM에서 계속될 수 있다")


def fetch(session: str, remote: str, dest: Path) -> None:
    if not remote.startswith("data/"):
        sys.exit("산출물은 data/ 아래 경로만 받는다. 추적 파일을 VM 결과로 덮어쓰지 않기 위해서다")
    tgz = "/content/fetch.tgz"
    vm_sh(session, f"cd {VM_REPO} && tar czf {tgz} {shlex.quote(remote)} && ls -l {tgz}")
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "fetch.tgz"
        print(colab("download", "-s", session, tgz, str(local)))
        with tarfile.open(local) as t:
            t.extractall(dest, filter="data")
    print(f"extracted {remote} -> {dest / remote}")


def finish(session: str) -> None:
    out_dir = ROOT / "outputs" / "notebooks"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(colab("log", "-s", session, "-o", str(out_dir / f"{session}.md"), check=False))
    print(colab("stop", "-s", session, check=False))
    left = colab("sessions", check=False)
    print(left)
    if "No active sessions" not in left:
        sys.exit("남은 세션이 있다. colab stop으로 정리한다")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").add_argument("overrides", nargs="*")
    for name in ("setup", "upload", "launch", "poll", "fetch", "finish"):
        sp = sub.add_parser(name)
        sp.add_argument("-s", "--session", required=True)
        if name == "setup":
            sp.add_argument("--commit", required=True)
        elif name == "upload":
            sp.add_argument("local")
            sp.add_argument("remote")
        elif name == "launch":
            sp.add_argument("uv_args", nargs=argparse.REMAINDER)
        elif name == "poll":
            sp.add_argument("--interval", type=int, default=180)
            sp.add_argument("--max-polls", type=int, default=40)
        elif name == "fetch":
            sp.add_argument("remote")
            sp.add_argument("--to", type=Path, default=ROOT)
    a = p.parse_args()

    if a.cmd == "preflight":
        preflight(a.overrides)
    elif a.cmd == "setup":
        setup(a.session, a.commit)
    elif a.cmd == "upload":
        upload(a.session, a.local, a.remote)
    elif a.cmd == "launch":
        launch(a.session, [x for x in a.uv_args if x != "--"])
    elif a.cmd == "poll":
        poll(a.session, a.interval, a.max_polls)
    elif a.cmd == "fetch":
        fetch(a.session, a.remote, a.to)
    else:
        finish(a.session)


if __name__ == "__main__":
    main()
