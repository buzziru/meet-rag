"""wrap_up 호출 직후 맥락에 마무리 규칙을 넣는 PostToolUse 훅(ADR-0042).

wrap_up 뒤에 앞의 보고를 다시 쓰는 일이 반복됐다(2026-10-15, 한 세션 세 번). 이미 출력한 텍스트는
훅이 되돌릴 수 없어, 쓰기 직전인 wrap_up 결과 시점에 규칙을 한 번 더 넣는다.
"""

import json
import sys

ASK = ("next-step 상자에 질문이 떴다. 이 턴은 여기서 끝낸다. "
       "텍스트를 더 쓰지 않는다(앞의 보고·표·질문을 다시 쓰지 않는다).")
NO_ASK = ("닫는 말은 상자와 앞 메시지에 없는 내용만 한국어로 쓴다. "
          "recap이나 앞에서 한 보고를 다시 쓰지 않는다. 더할 내용이 없으면 쓰지 않는다.")

data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
msg = ASK if data.get("tool_input", {}).get("ask") else NO_ASK
out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
