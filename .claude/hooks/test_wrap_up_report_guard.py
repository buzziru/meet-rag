import json
import subprocess
import sys
import time
from pathlib import Path

from wrap_up_report_guard import MIN_CHARS, turn_text_len

HOOK = Path(__file__).with_name("wrap_up_report_guard.py")


def user(content, **kw):
    return {"type": "user", "message": {"content": content}, **kw}


def assistant(*texts):
    blocks = [{"type": "text", "text": t} for t in texts]
    return {"type": "assistant", "message": {"content": blocks}}


TOOL_RESULT = user([{"type": "tool_result", "content": "ok"}])


def test_counts_only_text_after_last_user_prompt():
    rows = [user("첫 요청"), assistant("이전 턴 보고" * 100), user("다음 요청"),
            assistant("가" * 10), TOOL_RESULT, assistant("나" * 20)]
    assert turn_text_len(rows) == 30


def test_meta_and_tool_results_do_not_start_a_turn():
    rows = [user("요청"), assistant("가" * 50), user("<system-reminder>", isMeta=True), TOOL_RESULT,
            assistant("나" * 50)]
    assert turn_text_len(rows) == 100


def test_user_prompt_given_as_text_blocks():
    rows = [assistant("가" * 50), user([{"type": "text", "text": "요청"}]), assistant("나" * 5)]
    assert turn_text_len(rows) == 5


def run_hook(tmp_path, rows, tool_input):
    tx = tmp_path / "t.jsonl"
    tx.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    payload = {"transcript_path": str(tx), "tool_input": tool_input}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, check=True)
    return r.stdout.decode("utf-8")


def test_denies_short_report_before_question(tmp_path):
    ask = {"recap": "r", "ask": "진행할까요?"}
    out = run_hook(tmp_path, [user("요청"), assistant("짧음")], ask)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allows_long_report_or_no_question(tmp_path):
    long_rows = [user("요청"), assistant("가" * MIN_CHARS)]
    assert run_hook(tmp_path, long_rows, {"recap": "r", "ask": "진행할까요?"}) == ""
    assert run_hook(tmp_path, [user("요청"), assistant("짧음")], {"recap": "r"}) == ""


def test_waits_until_same_message_text_is_written(tmp_path):
    """같은 메시지의 본문과 tool_use 행이 훅이 뜬 뒤에 기록돼도 센다."""
    tx = tmp_path / "t.jsonl"
    tx.write_text(json.dumps(user("요청"), ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {"transcript_path": str(tx), "tool_use_id": "toolu_1",
               "tool_input": {"recap": "r", "ask": "진행할까요?"}}
    p = subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(json.dumps(payload).encode("utf-8"))
    p.stdin.close()
    time.sleep(0.5)
    tool_use = {"type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "wrap_up"}]}}
    with tx.open("a", encoding="utf-8") as f:
        for r in (assistant("가" * MIN_CHARS), tool_use):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    assert p.wait(timeout=10) == 0
    assert p.stdout.read() == b""
