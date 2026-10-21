"""Bash로 파일을 고친 직후 깨진 파일이 있는지 보는 PostToolUse 훅(ADR-0055).

heredoc 안 Python으로 파일을 고치다 `\\n`이 실제 줄바꿈으로 들어가 테스트 파일이 깨지거나(S17),
`Path.write_text`가 줄바꿈을 CRLF로 바꾼 일(S16)이 규칙(ADR-0053)이 있는데도 반복됐다. 명령을 미리
막으면 정상 명령까지 막혀(`f.write(... + "\\n")` 같은 쓰임이 훨씬 많다) 작업이 늦어지므로, 막지 않고
실행 직후 바뀐 파일만 검사해 문제가 있으면 알린다(exit 2, stderr가 Claude에게 간다).

보는 명령: `python`, `sed -i`가 든 Bash 명령. settings.json의 `if` 조건으로 이 명령에만 훅을 띄운다.
Windows에서 훅 하나를 띄우는 데 약 0.5초가 들어 모든 Bash 뒤에 띄우면 그만큼 늦어진다.
`if: "Bash(*<<*)"`는 heredoc 명령에 걸리지 않았다(2026-10-21 확인). 깨진 사례는 모두 heredoc으로
만든 Python 스크립트였고 `python` 조건에 걸린다. `cat > 파일 <<'EOF'`는 내용을 그대로 쓴다.
보는 것: 바뀐 `.py`의 구문 오류, 작업트리가 CRLF가 된 파일(.gitattributes가 작업트리까지 LF로
정한다). 이스케이프하지 않은 `~`는 Write·Edit 쪽 전역 훅이 보고, Bash로 깨진 사례가 없어
보지 않는다.
`if`를 지원하지 않는 버전에서는 모든 Bash 뒤에 실행되므로 아래 TRIGGERS로 한 번 더 거른다.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

TRIGGERS = ("python", "sed -i")
ROOT = Path(__file__).resolve().parents[2]


def triggered(command: str, args: list[str]) -> bool:
    """검사할 명령인지. settings.json의 `if`는 조건을 묶을 수 없어 python·sed 핸들러를 따로 둔다.
    둘 다 든 명령에서 알림이 두 번 나지 않게 sed 핸들러(인자 sed)는 python이 든 명령을 넘긴다."""
    if args == ["sed"] and "python" in command:
        return False
    return any(t in command for t in TRIGGERS)


def changed_files(root: Path = ROOT) -> list[str]:
    """작업트리에서 바뀌었거나 새로 생긴(무시하지 않는) 파일."""
    out = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8").stdout
    paths, parts = [], iter(out.split("\0"))
    for e in parts:
        if not e[3:]:
            continue
        if e[0] in "RC":  # 이름 변경·복사는 다음 조각에 상태 없이 옛 경로가 온다
            next(parts, None)
        if e[:2].strip() != "D":
            paths.append(e[3:])
    return paths


def problems(paths: list[str], root: Path = ROOT) -> list[str]:
    found = []
    for rel in paths:
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\0" in raw:  # 이진 파일
            continue
        if b"\r\n" in raw:
            found.append(f"{rel}: 줄바꿈에 CRLF가 있다(저장소 규약은 LF). "
                         "스크립트로 쓸 때 open(..., newline='\\n')")
        if rel.endswith(".py"):
            try:
                ast.parse(raw.decode("utf-8"), filename=rel)
            except (SyntaxError, UnicodeDecodeError) as e:
                line = getattr(e, "lineno", "?")
                found.append(f"{rel}:{line}: 파이썬 구문 오류({e.__class__.__name__}). "
                             "heredoc 안 문자열의 이스케이프가 실제 줄바꿈으로 들어갔는지 본다")
    return found


def main() -> int:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not triggered(data.get("tool_input", {}).get("command", ""), sys.argv[1:]):
        return 0
    found = problems(changed_files())
    if not found:
        return 0
    msg = ["[파일 손상 검사] 이 Bash 명령 뒤 작업트리에서 아래를 찾았다. "
           "고친 파일이면 Edit 도구로 바로잡는다.",
           *found, "이 명령과 관계없는 기존 변경이면 무시하고 사용자에게 한 줄로 알린다."]
    sys.stderr.buffer.write(("\n".join(msg) + "\n").encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
