"""multidoc-writer·multidoc-checker 에이전트의 Read·Write를 허용 경로로 제한하는 PreToolUse 훅.

두 에이전트 정의의 frontmatter에만 등록한다. agent_type이 다른 에이전트로 적힌 호출은
통과시킨다. 예외가 나면 막는다(통과시키면 제한이 조용히 풀린다).
- multidoc-writer: 읽기는 paths.multidoc_gen_in·multidoc_docs·multidoc_gen_out과 생성 지시
  파일(gen_v*.yaml), 쓰기는 multidoc_gen_out. 검사 지시(check_v*.yaml)는 읽지 못한다(ADR-0019)
- multidoc-checker: 읽기는 paths.multidoc_check_in, 쓰기는 multidoc_check_out. 검사 지시는 검사
  입력 파일 안에 들어 있다. 생성 출력은 읽지 못한다(ADR-0020)
config가 바뀌면 여기도 바꾼다.
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

# 에이전트마다 (Read 허용 디렉터리, Read 허용 파일 패턴, Write 허용 디렉터리)
RULES = {
    "multidoc-writer": (["data/multidoc/gen_in", "data/multidoc/docs", "data/multidoc/gen_out"],
                        "configs/multidoc/prompt/gen_v*.yaml", ["data/multidoc/gen_out"]),
    "multidoc-checker": (["data/multidoc/check_in"], "", ["data/multidoc/check_out"]),
}


def allowed(path: str, root: Path, dirs: list[str], files: str = "") -> bool:
    p = Path(path)
    p = (p if p.is_absolute() else root / p).resolve()
    if files and p.is_relative_to(root.resolve()):
        rel = p.relative_to(root.resolve()).as_posix()
        if fnmatch.fnmatch(rel.lower(), files.lower()):
            return True
    return any(p.is_relative_to((root / d).resolve()) for d in dirs)


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    data = json.load(sys.stdin)
    # 에이전트 이름은 정의 frontmatter의 훅 명령이 인자로 넘긴다. agent_type이 다른 에이전트면 통과
    agent = sys.argv[1]
    if data.get("agent_type") not in (None, agent):
        return
    read_dirs, read_files, write_dirs = RULES[agent]
    tool = data.get("tool_name")
    dirs = {"Read": read_dirs, "Write": write_dirs}.get(tool)
    if dirs is None:
        return
    files = read_files if tool == "Read" else ""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    path = data.get("tool_input", {}).get("file_path", "")
    if not allowed(path, root, dirs, files):
        where = ", ".join(dirs + ([files] if files else []))
        print(f"{agent}는 {tool}를 {where}에서만 쓸 수 있다: {path}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"multidoc_read_guard 오류로 막는다: {e!r}", file=sys.stderr)
        sys.exit(2)
