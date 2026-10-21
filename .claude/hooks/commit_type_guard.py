"""git commit 메시지의 타입이 규약 밖이면 막는 PreToolUse 훅(ADR-0055).

규약(.claude/rules/git.md 커밋 절)에 없는 타입(`perf`)으로 커밋한 일이 두 번 있었다(사용자 지적
2026-10-21). 규약 문서만으로는 커밋할 때 대조하지 않아, `-m`/`--message`로 준 첫 줄의
`<타입>:`을 허용 목록과 대조한다. 메시지를 명령에서 찾지 못하면(`-F 파일`, `--amend --no-edit`,
편집기) 보지 않는다.
"""

import json
import re
import sys

TYPES = ("feat", "fix", "exp", "docs", "test", "refactor", "chore")
COMMIT = re.compile(r"\bgit\s+commit\b")
# -m "…", -m '…', -m "$(cat <<'EOF' …", --message=…, -qm "…" 다음의 메시지 시작
MESSAGE = re.compile(r"(?:\s-[a-zA-Z]*m|\s--message)(?:=|\s+)"
                     r"""(?:"\$\(cat\s+<<-?\s*'?\w+'?\s*\n|["']?)""")
SUBJECT = re.compile(r"^([A-Za-z]+):\s")  # 범위 표기 `fix(judge):`는 규약에 없다(이력 0건)
REASON = ("커밋 타입 `{t}`는 규약에 없다. 허용: " + ", ".join(TYPES)
          + ". 형식은 `<타입>: <요약>`이다(.claude/rules/git.md 커밋 절). 성능 개선은 refactor 등 "
          "가장 가까운 타입으로 쓴다.")


def commit_subject(command: str) -> str | None:
    """git commit 명령에서 메시지 첫 줄. git commit이 아니거나 메시지를 찾지 못하면 None."""
    commit = COMMIT.search(command)
    if not commit:
        return None
    m = MESSAGE.search(command, commit.end())
    if not m:
        return None
    return command[m.end():].split("\n", 1)[0]


def bad_type(subject: str) -> str | None:
    """규약 밖 타입이면 그 타입(형식이 아니면 첫 낱말), 맞으면 None."""
    m = SUBJECT.match(subject)
    if m and m.group(1) in TYPES:
        return None
    return m.group(1) if m else (subject.split() or [""])[0]


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    subject = commit_subject(data.get("tool_input", {}).get("command", ""))
    if subject is None:
        return
    t = bad_type(subject)
    if t is None:
        return
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": REASON.format(t=t)}}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
