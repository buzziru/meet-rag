"""multidoc-writer 에이전트의 Read·Write를 허용 경로로 제한하는 PreToolUse 훅.

multidoc-writer 정의의 frontmatter에만 등록한다. agent_type이 다른 에이전트로 적힌 호출은
통과시킨다. 예외가 나면 막는다(통과시키면 제한이 조용히 풀린다).
허용 경로는 configs/config.yaml의 paths.multidoc_gen_in·multidoc_docs·multidoc_gen_out과
생성 지시 디렉터리다. config가 바뀌면 여기도 바꾼다. 근거는 docs/harness/adr/0019.md.
"""

import json
import os
import sys
from pathlib import Path

AGENT = "multidoc-writer"
READ_DIRS = ["configs/multidoc/prompt", "data/multidoc/gen_in", "data/multidoc/docs",
             "data/multidoc/gen_out"]
WRITE_DIRS = ["data/multidoc/gen_out"]


def allowed(path: str, root: Path, dirs: list[str]) -> bool:
    p = Path(path)
    p = (p if p.is_absolute() else root / p).resolve()
    return any(p.is_relative_to((root / d).resolve()) for d in dirs)


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    data = json.load(sys.stdin)
    if data.get("agent_type") not in (None, AGENT):
        return
    tool = data.get("tool_name")
    dirs = {"Read": READ_DIRS, "Write": WRITE_DIRS}.get(tool)
    if dirs is None:
        return
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    path = data.get("tool_input", {}).get("file_path", "")
    if not allowed(path, root, dirs):
        print(f"{AGENT}는 {tool}를 {', '.join(dirs)} 아래에서만 쓸 수 있다: {path}",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"multidoc_read_guard 오류로 막는다: {e!r}", file=sys.stderr)
        sys.exit(2)
