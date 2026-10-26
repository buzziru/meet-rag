import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("wrap_up_reminder.py")


def context(tool_input):
    out = subprocess.run([sys.executable, str(HOOK)], capture_output=True,
                         input=json.dumps({"tool_input": tool_input}).encode("utf-8"), check=True)
    return json.loads(out.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]


def test_ask_ends_the_turn():
    assert "턴은 여기서 끝낸다" in context({"recap": "r", "ask": "진행할까요?"})


def test_without_ask_allows_only_new_closing_text():
    assert "다시 쓰지 않는다" in context({"recap": "r"})
