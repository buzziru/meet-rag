"""다른 Orca 세션의 소식을 지시마다 컨텍스트에 넣는 UserPromptSubmit 훅(ADR-0098).

worktree로 나뉜 세션은 상대의 진행을 찾아 읽어야 알 수 있어, 겹친 뒤에야 드러났다(D-84 번호
충돌, PR #225 SPEC 충돌). 지난번 이후의 새 소식만 넣고 없으면 아무것도 넣지 않는다.

- 공유 기록: 메인 체크아웃 `_workspace/00_sessions_log.md`의 상대 세션 줄.
  `python .claude/hooks/sessions_news.py add "내용" "영향"`으로 적는다
- 상대 브랜치 커밋: worktree는 같은 `.git`을 쓰므로 fetch 없이 보인다. 내 브랜치에 이미 있는
  커밋은 뺀다(상대가 main을 병합해도 내 커밋이 소식으로 돌아오지 않는다)

세션 이름은 worktree 폴더 이름이고 메인 체크아웃은 `main`이다. 위치는 `_workspace/`의 세션별
파일에 둔다. 새 Claude 세션은 앞서 받은 소식을 모르므로 기록의 최근 줄을 다시 넣는다.
오류가 나도 지시를 막지 않고 아무것도 넣지 않는다.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path("_workspace/00_sessions_log.md")
REPLAY = 10
MAX_COMMITS = 10
MAX_FILES = 6
HEADER = ("[다른 세션 소식] 지금 작업에 영향이 있으면 사용자에게 먼저 알린다. "
          "상대 세션으로 전달하는 일은 사용자 지시로 한다(.claude/rules/sessions.md).")


def git(cwd: str, *args: str) -> str | None:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=10)
    return r.stdout if r.returncode == 0 else None


def locate(cwd: str) -> tuple[Path, str, dict[str, str]]:
    """(메인 체크아웃, 내 세션 이름, 세션별 HEAD)."""
    top = Path(git(cwd, "rev-parse", "--show-toplevel").strip()).resolve()
    blocks = [b.splitlines() for b in git(cwd, "worktree", "list", "--porcelain").split("\n\n")
              if b.strip()]
    paths = [Path(b[0].removeprefix("worktree ")).resolve() for b in blocks]
    names = ["main", *(p.name for p in paths[1:])]
    heads = {n: b[1].removeprefix("HEAD ") for n, b in zip(names, blocks, strict=True)}
    return paths[0], names[paths.index(top)], heads


def log_news(lines: list[str], start: int, me: str) -> list[str]:
    """start 뒤 줄 중 상대 세션이 적은 줄."""
    news = []
    for line in lines[start:]:
        fields = [f.strip() for f in line.split("|", 2)]
        if line.strip() and not (len(fields) > 1 and fields[1] == me):
            news.append(line.strip())
    return news


def commit_news(cwd: str, last: str, head: str) -> list[str]:
    """last 뒤로 상대 브랜치에 생긴 커밋 중 내 브랜치에 없는 것, 최신순."""
    out = git(cwd, "log", "--no-merges", "--format=%x01%h %s", "--name-only", f"{last}..{head}",
              "^HEAD")
    if out is None:  # 지난 위치를 찾지 못함(gc 등). 다음부터 새 위치로 잰다
        return []
    news = []
    for chunk in out.split("\x01")[1:]:
        title, *files = [x for x in chunk.splitlines() if x.strip()]
        more = f" 외 {len(files) - MAX_FILES}개" if len(files) > MAX_FILES else ""
        news.append(f"- {title} (파일: {', '.join(files[:MAX_FILES])}{more})")
    if len(news) > MAX_COMMITS:
        return [*news[:MAX_COMMITS], f"- 외 커밋 {len(news) - MAX_COMMITS}개"]
    return news


def collect(cwd: str, session_id: str) -> str:
    """새 소식 문구(없으면 빈 문자열). 읽은 위치를 함께 갱신한다."""
    root, me, heads = locate(cwd)
    state_path = root / f"_workspace/.sessions_news_{me}.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    log_path = root / LOG
    lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    same_session = state.get("session_id") == session_id
    start = state.get("lines", 0) if same_session else max(0, len(lines) - REPLAY)
    if start > len(lines):  # 기록을 비웠으면 처음부터
        start = 0

    parts = []
    if news := log_news(lines, start, me):
        parts.append(f"기록({LOG.as_posix()}):\n" + "\n".join(f"- {n}" for n in news))
    others = {n: h for n, h in heads.items() if n != me}
    for name, head in others.items():
        last = state.get("heads", {}).get(name)
        if last and last != head and (news := commit_news(cwd, last, head)):
            parts.append(f"{name} 커밋:\n" + "\n".join(news))

    state_path.parent.mkdir(exist_ok=True)
    with open(state_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"session_id": session_id, "lines": len(lines), "heads": others}, f)
    return "\n".join([HEADER, *parts]) if parts else ""


def add(cwd: str, what: str, effect: str) -> None:
    root, me, _ = locate(cwd)
    with open(root / LOG, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} | {me} | {what} | {effect}\n")


def main() -> None:
    if sys.argv[1:2] == ["add"]:
        add(os.getcwd(), sys.argv[2], sys.argv[3])
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        context = collect(data.get("cwd") or os.getcwd(), data.get("session_id", ""))
    except Exception:  # 소식 때문에 사용자 지시를 막지 않는다
        return
    if context:
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                      "additionalContext": context}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
