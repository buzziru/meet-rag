"""공유 `data/`를 지우는 명령을 실행 전에 막거나 사용자 확인을 띄우는 PreToolUse 훅(ADR-0058).

`data/`는 git으로 추적하지 않아 지우면 되돌릴 수 없다. 2026-10-22 S21 하위 세션이 임시 worktree에
`data/` junction을 두고 `git worktree remove --force`로 정리해, 명령이 junction을 따라가 원본
`data/gen_eval`·`data/conditions`를 지웠다(섀도 복사본으로만 되살림).

- 링크(junction·심볼릭 링크)를 만드는 것과 링크만 지우는 비재귀 명령은 그대로 둔다
- 재귀 삭제·`git worktree remove`의 대상이 링크이거나 안에 링크가 있으면 막는다(deny)
- `data/` 아래(링크를 따라간 위치 포함)를 지우는 명령, `git clean -x/-X`, `data/` 경로가 든
  Python 삭제 호출은 사용자 확인을 띄운다(ask)
명령 해석은 낱말 단위 근사다. 놓치는 형태가 있어도 위임 지시 규칙(meet-rag 스킬)이 함께 막는다.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DELETE = re.compile(r"(?:^|[\s;&|(])(?:rm|rmdir|rd|del|erase|Remove-Item|ri)(?=\s)"
                    r"|\bgit\s+worktree\s+remove\b|\bgit\s+clean\b|-delete\b|\.Delete\(\)"
                    r"|\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir)\b|\.unlink\(|\.rmdir\(",
                    re.IGNORECASE)
# rm -r·-rf·-fR, Remove-Item -Recurse, rmdir /s, git worktree remove 등(-Force 같은 긴 플래그 제외)
RECURSIVE = re.compile(r"\bgit\s+worktree\s+remove\b|\bgit\s+clean\b|\brmtree\b|-delete\b"
                       r"|(?:^|\s)-(?=[a-zA-Z]{0,3}[rR])[a-zA-Z]{1,4}(?=\s|$)|--recursive\b"
                       r"|-Recurse\b|(?:^|\s)/[sS](?=\s|$)", re.IGNORECASE)
SEP = re.compile(r"&&|\|\||[;|\n]")
TAIL_VERB = re.compile(r"-delete\b|\.Delete\(\)", re.IGNORECASE)  # 대상이 동사 앞에 오는 형태
CLEAN_IGNORED = re.compile(r"\bgit\s+clean\b[^\n;&|]*\s-[a-zA-Z]*[xX]")
PY_DELETE = re.compile(r"\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir)\b"
                       r"|\.unlink\(|\.rmdir\(")
DATA_TEXT = re.compile(r"(?:^|[\s\"'(=/\\])data[/\\]")
SCAN_LIMIT = 50_000  # 링크를 찾으려고 훑는 항목 수 상한. 넘으면 확인을 띄운다
SAFE = ("링크만 지우려면 PowerShell `(Get-Item <링크>).Delete()`나 cmd `rmdir <링크>`(/s 없이)를 "
        "쓰고, 링크를 모두 지운 뒤 디렉터리를 지운다")


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())


def to_path(token: str, cwd: Path) -> Path:
    """Git Bash 경로(/c/...)와 상대 경로를 Windows 경로로 바꾼다. 링크는 따라가지 않는다."""
    t = token.strip("\"'")
    m = re.match(r"^/([a-zA-Z])(/.*)?$", t)
    if m:
        t = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    p = Path(t)
    return Path(os.path.normpath(p if p.is_absolute() else cwd / p))


def under(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base)
        return True
    except ValueError:
        return False


def links_inside(d: Path) -> tuple[list[Path], bool]:
    """디렉터리 안의 링크(따라가지 않음)와 상한에 닿았는지."""
    found, n = [], 0
    for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
        for name in dirnames + filenames:
            n += 1
            p = Path(dirpath) / name
            if is_link(p):
                found.append(p)
        dirnames[:] = [x for x in dirnames if not is_link(Path(dirpath) / x)]
        if n > SCAN_LIMIT:
            return found, True
    return found, False


def tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def decide(command: str, cwd: Path, root: Path = ROOT) -> tuple[str, str] | None:
    """(permissionDecision, 이유) 또는 None(그대로 둠)."""
    if not DELETE.search(command):
        return None
    data = Path(os.path.normpath(root / "data"))
    ask = []
    for seg in SEP.split(command):
        verb = DELETE.search(seg)
        if not verb:
            continue
        # 대상은 같은 구간의 동사 뒤 낱말이다. `x.Delete()`, `find x -delete`는 앞에 온다
        targets = tokens(seg if TAIL_VERB.search(seg) else seg[verb.end():])
        out = check_targets(targets, bool(RECURSIVE.search(seg)), cwd, data, ask)
        if out:
            return out
    if CLEAN_IGNORED.search(command):
        ask.append("git clean -x/-X: git이 추적하지 않는 data/를 지운다")
    if PY_DELETE.search(command) and DATA_TEXT.search(command):
        ask.append("data/ 경로가 든 Python 삭제 호출")
    if ask:
        return "ask", ("공유 data/를 지울 수 있는 명령이다. data/는 git으로 추적하지 않아 "
                       "되돌릴 수 없다. 대상: " + "; ".join(ask[:5])
                       + ". 사용자가 대상과 이유를 확인한 뒤 실행한다")
    return None


def check_targets(targets: list[str], recursive: bool, cwd: Path, data: Path,
                  ask: list[str]) -> tuple[str, str] | None:
    """삭제 대상 낱말을 본다. 막을 대상이면 ("deny", 이유), 확인할 대상은 ask에 더한다."""
    for tok in targets:
        if tok.startswith(("-", "/")) and not re.match(r"^/[a-zA-Z](/|$)", tok):
            continue  # 플래그(-r, /s). Git Bash 드라이브 경로(/c/...)는 대상이다
        if not re.search(r"[\w.~]", tok):
            continue
        p = to_path(tok, cwd)
        if not (p.exists() or is_link(p)):
            if under(p, data):
                ask.append(str(p))
            continue
        if is_link(p):
            if recursive:
                return "deny", f"`{p}`는 링크다. 재귀 삭제는 링크를 따라가 원본을 지운다. {SAFE}"
            continue  # 링크만 지우는 비재귀 명령
        if under(p, data) or under(Path(os.path.realpath(p)), data):
            ask.append(str(p))
        elif recursive and p.is_dir():
            found, capped = links_inside(p)
            if found:
                shown = ", ".join(str(x) for x in found[:5])
                return "deny", (f"`{p}` 안에 링크가 있다({shown}). 재귀 삭제·git worktree remove는 "
                                f"링크를 따라가 원본(data/ 등)을 지운다. {SAFE}")
            if capped:
                ask.append(f"{p}(항목이 많아 링크를 다 확인하지 못함)")
    return None


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = data.get("tool_input", {}).get("command", "")
    out = decide(command, Path(data.get("cwd") or os.getcwd()))
    if out is None:
        return
    decision, reason = out
    res = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                  "permissionDecisionReason": reason}}
    sys.stdout.buffer.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
