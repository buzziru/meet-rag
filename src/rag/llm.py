"""LLM 응답 처리. 검색(rag.rewrite)과 생성(rag.generate)이 함께 쓴다(S16)."""

# Gemma 4는 이 엔드포인트에서 사고 과정을 끌 수 없어 답변 앞에 붙여 낸다
THOUGHT_START, THOUGHT_END = "<thought>", "</thought>"


def split_thought(text: str) -> tuple[str, str]:
    """응답을 (사고 과정, 답변)으로 나눈다. 사고 과정이 없으면 빈 문자열."""
    if not text.lstrip().startswith(THOUGHT_START):
        return "", text.strip()
    head, sep, tail = text.partition(THOUGHT_END)
    if not sep:
        return head.lstrip()[len(THOUGHT_START):].strip(), ""
    return head.lstrip()[len(THOUGHT_START):].strip(), tail.strip()


def answer_start(text: str) -> int | None:
    """스트리밍 중 답변이 시작하는 위치. 아직 사고 과정 안이면 None."""
    if not text.lstrip().startswith(THOUGHT_START[: len(text.lstrip())]):
        return 0
    end = text.find(THOUGHT_END)
    return None if end < 0 else end + len(THOUGHT_END)
