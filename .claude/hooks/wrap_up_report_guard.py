"""질문 상자를 띄우는 wrap_up 앞에 본문 보고가 있는지 보는 PreToolUse 훅(ADR-0052).

결과·지시서를 본문으로 보고하지 않고 질문 상자로 넘어가는 일이 Claude Code 업데이트 뒤 반복됐다
(2026-10-15~10-20, 7회 이상). 메모리로 막히지 않아, 마지막 사용자 메시지 뒤에 쓴 본문 글자 수가
MIN_CHARS보다 적으면 wrap_up을 막고 보고를 먼저 쓰게 한다. 질문이 없는 wrap_up은 보지 않는다.
"""

import json
import sys

MIN_CHARS = 400
REASON = (f"질문 상자 전에 이 턴 본문에 쓴 보고가 {{n}}자다(기준 {MIN_CHARS}자). "
          "상자를 띄우기 전에 본문으로 보고한다: 만든 것·한 것, 결과 수치(표), 해석, "
          "어긋난 항목의 구체 내용, "
          "판단할 곳(선택지·차이·근거). 짧은 답이 맞는 질문이면 답을 본문에 쓰고 다시 호출한다.")


def is_user_prompt(row: dict) -> bool:
    if row.get("type") != "user" or row.get("isMeta"):
        return False
    content = row["message"]["content"]
    if isinstance(content, str):
        return True
    types = {b.get("type") for b in content}
    return "text" in types and "tool_result" not in types


def turn_text_len(rows: list[dict]) -> int:
    start = max((i for i, r in enumerate(rows) if is_user_prompt(r)), default=-1)
    return sum(len(b.get("text", "")) for r in rows[start + 1:] if r.get("type") == "assistant"
               for b in r["message"]["content"] if b.get("type") == "text")


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not data.get("tool_input", {}).get("ask"):
        return
    with open(data["transcript_path"], encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    n = turn_text_len(rows)
    if n >= MIN_CHARS:
        return
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": REASON.format(n=n)}}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
