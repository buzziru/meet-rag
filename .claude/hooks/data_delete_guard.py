"""공유 `data/`를 지우는 명령을 실행 전에 막거나 사용자 확인을 띄우는 PreToolUse 훅(ADR-0058).

`data/`는 git으로 추적하지 않아 지우면 되돌릴 수 없다. 2026-10-22 S21 하위 세션이 임시 worktree에
`data/` junction을 두고 `git worktree remove --force`로 정리해, 명령이 junction을 따라가 원본
`data/gen_eval`·`data/conditions`를 지웠다(섀도 복사본으로만 되살림).

- 링크(junction·심볼릭 링크)를 만드는 것과 링크만 지우는 비재귀 명령은 그대로 둔다
- 재귀 삭제·`git worktree remove`·`orca worktree rm`의 대상이 링크이거나 안에 링크가 있으면
  막는다(deny). 링크를 따라가 원본을 지우는 경우만 막고, 링크를 먼저 지우면 통과한다. 세션과
  관계없이 건다
- worktree에서 도는 세션(`.git`이 파일)이 `data/`(원본 포함, 링크를 따라간 위치 포함)를 지우는
  명령, `git clean -x/-X`, `data/` 경로가 든 Python 삭제 호출은 사용자 확인을 띄운다(ask).
  메인 체크아웃의 `data/` 삭제는 그대로 둔다. 막으려는 것은 분리된 세션의 임의 삭제다(사용자
  결정 2026-10-22)
- worktree(`.git`이 파일인 디렉터리)를 재귀 삭제·`git worktree remove`·`orca worktree rm`할 때
  그 `_workspace/`에 파일이 있으면 막는다(deny). `_workspace/`는 세션 사이에 작업 기록을 넘기는 곳인데 .gitignore
  대상이라 git이 경고 없이 지운다. 2026-10-26 하위 세션 진행 기록을 옮기기 전에 지웠다(ADR-0062)
따옴표 안의 공백이 든 문자열(커밋 메시지 등)과 heredoc 본문은 명령으로 보지 않는다. 명령 해석은
낱말 단위 근사다. 놓치는 형태가 있어도 위임 지시 규칙(meet-rag 스킬)이 함께 막는다.
"""

import glob
import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKTREE_REMOVE = r"\bgit\s+(?:-C\s+(\S+)\s+)?worktree\s+remove\b"  # git -C <경로>도 같다
# Orca의 worktree 삭제도 git worktree remove라 같게 본다. --force는 링크를 따라가 원본을
# 지운다(2026-10-27 실험, ADR-0064). 대상은 --worktree path:<경로> 선택자다
ORCA_RM = r"\borca(?:\.exe|\.cmd)?\s+worktree\s+rm\b"
DELETE = re.compile(r"(?:^|[\s;&|(])(?:rm|rmdir|rd|del|erase|Remove-Item|ri)(?=\s)"
                    rf"|{WORKTREE_REMOVE}|{ORCA_RM}|\bgit\s+clean\b|-delete\b|\.Delete\("
                    r"|\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir)\b|\.unlink\(|\.rmdir\(",
                    re.IGNORECASE)
# rm -r·-rf·-fR, Remove-Item -Recurse, rmdir /s, git worktree remove, .Delete($true) 등
# (-Force 같은 긴 플래그 제외)
RECURSIVE = re.compile(rf"{WORKTREE_REMOVE}|{ORCA_RM}|\bgit\s+clean\b|\brmtree\b|-delete\b"
                       r"|(?:^|\s)-(?=[a-zA-Z]{0,3}[rR])[a-zA-Z]{1,4}(?=\s|$)|--recursive\b"
                       r"|-Recurse\b|(?:^|\s)/[sS](?=\s|$)|\.Delete\(\s*\$true\s*\)", re.IGNORECASE)
SEP = re.compile(r"&&|\|\||[;|\n]")
TAIL_VERB = re.compile(r"-delete\b|\.Delete\(", re.IGNORECASE)  # 대상이 동사 앞에 오는 형태
# (Get-Item <대상>).Delete(…)의 대상
ITEM_DELETE = re.compile(r"\(\s*(?:Get-Item|gi)\s+(?:-(?:Literal)?Path\s+)?(\S+?)\s*\)"
                         r"\s*\.Delete\(", re.IGNORECASE)
CLEAN_IGNORED = re.compile(r"\bgit\s+clean\b[^\n;&|]*\s-[a-zA-Z]*[xX]")
PY_DELETE = re.compile(r"\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir)\b"
                       r"|\.unlink\(|\.rmdir\(")
DATA_TEXT = re.compile(r"(?:^|[\s\"'(=/\\])data[/\\]")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.DOTALL)
SPACED_QUOTE = re.compile(r"\"[^\"]*\s[^\"]*\"|'[^']*\s[^']*'")  # 공백이 든 따옴표 문자열
# 다른 셸에 넘긴 문자열(bash -c "…", powershell -Command "…", cmd /c "…")은 명령이다
SHELL_ARG = re.compile(r"(?:\b(?:bash|sh)(?:\.exe)?\s+-c"
                       r"|\bpowershell(?:\.exe)?(?:\s+-\w+)*?\s+-Command|\bpwsh(?:\.exe)?\s+-(?:c|Command)|\bcmd(?:\.exe)?\s+/[cCkK])\s+([\"'])(.*?)\1",
                       re.IGNORECASE | re.DOTALL)
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


def data_dirs(root: Path) -> list[Path]:
    """보호할 data/ 목록. worktree에서 돌면 원본 저장소의 data/도 넣는다. worktree의 `.git`은
    `gitdir: <원본>/.git/worktrees/<이름>` 파일이라 원본을 거기서 찾는다(하위 세션은
    `.claude/worktrees/<이름>`에서 돌고, 원본 data/를 절대 경로로 지울 수 있다)."""
    dirs = [Path(os.path.normpath(root / "data"))]
    git = root / ".git"
    if git.is_file():
        m = re.match(r"gitdir:\s*(.+)", git.read_text(encoding="utf-8").strip())
        if m:
            common = Path(m.group(1).strip()).parents[1]  # <원본>/.git
            dirs.append(Path(os.path.normpath(common.parent / "data")))
    return dirs


def expand(tok: str, cwd: Path) -> list[str]:
    """셸 와일드카드(`wt/*`)를 펼친다. 셸이 펼친 뒤 실행하므로 대상은 펼친 경로들이다."""
    if not re.search(r"[*?]", tok):
        return [tok]
    pattern = str(to_path(tok, cwd))
    return glob.glob(pattern, include_hidden=True) or [tok]


def decide(command: str, cwd: Path, root: Path = ROOT) -> tuple[str, str] | None:
    """(permissionDecision, 이유) 또는 None(그대로 둠)."""
    body = HEREDOC.sub(" ", command)
    # 커밋 메시지·문서 본문은 명령이 아니다. 다른 셸에 넘긴 문자열은 명령으로 다시 붙인다
    text = "\n".join([SPACED_QUOTE.sub(" ", body)] + [m.group(2) for m in SHELL_ARG.finditer(body)])
    if not DELETE.search(text) and not PY_DELETE.search(command):  # Python 코드는 따옴표 안에 있다
        return None
    worktree = (root / ".git").is_file()
    data = data_dirs(root)
    ask = []
    for seg in SEP.split(text):
        verb = DELETE.search(seg)
        if not verb:
            continue
        # 대상은 같은 구간의 동사 뒤 낱말이다. `x.Delete()`, `find x -delete`는 앞에 온다
        item = ITEM_DELETE.findall(seg)
        targets = item or tokens(seg if TAIL_VERB.search(seg) else seg[verb.end():])
        if re.search(ORCA_RM, seg, re.IGNORECASE):
            # Orca는 --worktree=<선택자> 붙임 형태도 받는다(2026-10-27 확인)
            targets = [t.split("=", 1)[1] if t.startswith("--worktree=") else t for t in targets]
            # id:·name: 같은 선택자는 경로를 알 수 없어 링크·_workspace/를 확인하지 못한다
            other = [t for t in targets if re.match(r"^[a-zA-Z]{2,}:", t.strip("\"'"))
                     and not t.strip("\"'").startswith("path:")]
            if other:
                return "ask", (f"`orca worktree rm`의 대상 {other[0]}은 경로가 아니라 링크와 "
                               "`_workspace/`를 확인하지 못했다. "
                               "`--worktree path:<경로>`로 지정한다")
            targets = [t.strip("\"'").removeprefix("path:") for t in targets]
        # git -C <경로> worktree remove <대상>의 상대 경로는 <경로> 기준이다
        base = to_path(verb.group(1), cwd) if verb.lastindex and verb.group(1) else cwd
        out = check_targets(targets, bool(RECURSIVE.search(seg)), base, data, ask)
        if out:
            return out
    if not worktree:  # 메인 체크아웃의 data/ 삭제는 확인하지 않는다
        return None
    if CLEAN_IGNORED.search(text):
        ask.append("git clean -x/-X: git이 추적하지 않는 data/를 지운다")
    if PY_DELETE.search(command) and DATA_TEXT.search(command):  # 코드는 따옴표 안에 있다
        ask.append("data/ 경로가 든 Python 삭제 호출")
    if ask:
        return "ask", ("worktree 세션이 공유 data/를 지우려 한다. data/는 git으로 추적하지 않아 "
                       "되돌릴 수 없다. 대상: " + "; ".join(ask[:5])
                       + ". 사용자가 대상과 이유를 확인한 뒤 실행한다")
    return None


def check_targets(targets: list[str], recursive: bool, cwd: Path, data: list[Path],
                  ask: list[str]) -> tuple[str, str] | None:
    """삭제 대상 낱말을 본다. 막을 대상이면 ("deny", 이유), 확인할 대상은 ask에 더한다."""
    for tok in [x for t in targets for x in expand(t, cwd)]:
        if tok.startswith(("-", "/")) and not re.match(r"^/[a-zA-Z](/|$)", tok):
            continue  # 플래그(-r, /s). Git Bash 드라이브 경로(/c/...)는 대상이다
        if not re.search(r"[\w.~]", tok):
            continue
        p = to_path(tok, cwd)
        if not (p.exists() or is_link(p)):
            if any(under(p, d) for d in data):
                ask.append(str(p))
            continue
        if is_link(p):
            if recursive:
                return "deny", f"`{p}`는 링크다. 재귀 삭제는 링크를 따라가 원본을 지운다. {SAFE}"
            continue  # 링크만 지우는 비재귀 명령
        real = Path(os.path.realpath(p))
        if any(under(p, d) or under(real, d) for d in data):
            ask.append(str(p))
        elif recursive and p.is_dir():
            found, capped = links_inside(p)
            if found:
                shown = ", ".join(str(x) for x in found[:5])
                return "deny", (f"`{p}` 안에 링크가 있다({shown}). 재귀 삭제·git worktree remove는 "
                                f"링크를 따라가 원본(data/ 등)을 지운다. {SAFE}")
            if capped:
                ask.append(f"{p}(항목이 많아 링크를 다 확인하지 못함)")
            if (p / ".git").is_file() and (notes := workspace_files(p)):
                return "deny", (f"worktree `{p}`의 `_workspace/`에 파일 {len(notes)}개가 있다"
                                f"({', '.join(notes[:5])}). `_workspace/`는 .gitignore 대상이라 "
                                "git worktree remove·재귀 삭제가 경고 없이 지운다. 메인 체크아웃의 "
                                "`_workspace/`로 옮긴 뒤 지운다(git.md main 맞추기 6, ADR-0062)")
    return None


def workspace_files(worktree: Path) -> list[str]:
    """worktree `_workspace/` 안의 파일(하위 폴더 포함). 세션 사이 작업 기록이라 옮긴 뒤 지운다."""
    ws = worktree / "_workspace"
    if not ws.is_dir():
        return []
    return sorted(str(f.relative_to(ws)) for f in ws.rglob("*") if f.is_file())


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
