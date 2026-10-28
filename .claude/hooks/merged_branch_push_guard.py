"""이미 병합된 PR의 브랜치로 push하면 막는 PreToolUse 훅(ADR-0076).

병합된 PR 브랜치에 STATUS 커밋을 push해 사용자가 지운 원격 브랜치를 다시 만든 일이 두 번
있었다(이슈 #120 세션, 2026-10-27 aea30e7). git.md의 push 전 확인 절차만으로는 건너뛸 수 있어
명령에서 push 대상 브랜치를 찾아 `gh pr list --head <브랜치> --state merged`로 대조한다.
main으로의 push(핸드오프 STATUS)와 원격 브랜치 삭제는 보지 않는다. gh가 실패하거나 브랜치를
알 수 없으면 막지 않는다(오탐으로 정당한 push를 막지 않으려는 것이다).
"""

import json
import re
import subprocess
import sys

PUSH = re.compile(r"\bgit\s+(?:-C\s+(\"[^\"]+\"|'[^']+'|\S+)\s+)?push\b([^\n;&|]*)")
SKIP = {"main", "HEAD", ""}
REASON = ("브랜치 `{b}`의 PR #{n}은 이미 병합됐다. push하면 지운 원격 브랜치가 다시 생기고 "
          "커밋은 어느 PR에도 들어가지 않는다. 최신 main에서 새 브랜치를 만들어 옮기거나, "
          "핸드오프 STATUS면 main 맞추기 뒤 main에 커밋한다(.claude/rules/git.md PR 절·핸드오프).")


def push_target(command: str) -> tuple[str | None, str | None] | None:
    """(브랜치 또는 None=현재 브랜치, -C 경로). git push가 아니거나 삭제 push면 None."""
    m = PUSH.search(command)
    if not m:
        return None
    args = m.group(2).split()
    if any(a in ("-d", "--delete") or a.startswith(":") for a in args):
        return None
    pos = [a for a in args if not a.startswith("-")]
    path = m.group(1).strip("\"'") if m.group(1) else None
    if len(pos) < 2:
        return None, path
    ref = pos[1].split(":")[-1].removeprefix("refs/heads/")
    return (None if ref == "HEAD" else ref), path


def current_branch(cwd: str | None) -> str:
    r = subprocess.run(["git", "branch", "--show-current"], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def merged_pr(branch: str, cwd: str | None) -> int | None:
    """그 브랜치를 head로 병합된 PR 번호. 없거나 gh가 실패하면 None."""
    try:
        r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "merged",
                            "--json", "number"], cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", timeout=20)
        prs = json.loads(r.stdout) if r.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    return prs[0]["number"] if prs else None


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    target = push_target(data.get("tool_input", {}).get("command", ""))
    if target is None:
        return
    branch, path = target
    cwd = path or data.get("cwd")
    branch = branch or current_branch(cwd)
    if branch in SKIP:
        return
    n = merged_pr(branch, cwd)
    if n is None:
        return
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": REASON.format(b=branch, n=n)}}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
