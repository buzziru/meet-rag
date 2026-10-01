"""문서를 고정 토큰 길이 청크로 나눈다. 규칙은 docs/slices/04-index.md "청킹"."""


def chunk_spans(
    offsets: list[tuple[int, int]], chunk_tokens: int, overlap_tokens: int
) -> list[tuple[int, int, int]]:
    """토큰 offset 목록을 (시작 문자, 끝 문자, 토큰 수) 청크 목록으로 나눈다.

    청크 텍스트는 이 문자 범위로 원문을 잘라 얻는다. 토큰을 다시 문자열로 바꾸면
    공백·문자가 원문과 달라질 수 있어서다.
    """
    if not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError("overlap_tokens는 0 이상 chunk_tokens 미만이어야 한다")
    step = chunk_tokens - overlap_tokens
    spans = []
    for i in range(0, len(offsets), step):
        toks = offsets[i : i + chunk_tokens]
        spans.append((toks[0][0], toks[-1][1], len(toks)))
        if i + chunk_tokens >= len(offsets):
            break
    return spans


def chunk_text(tokenizer, text: str, chunk_tokens: int, overlap_tokens: int):
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    return chunk_spans(enc["offset_mapping"], chunk_tokens, overlap_tokens)
