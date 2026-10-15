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


def sentence_units(offsets: list[tuple[int, int]], sent_starts: list[int],
                   chunk_tokens: int) -> list[tuple[int, int]]:
    """토큰을 문장 단위 [시작, 끝) 토큰 구간으로 나눈다. chunk_tokens보다 긴 문장은
    그 길이로 자른다.

    토큰은 시작 문자가 속한 문장에 넣는다. 문장 사이 공백 등 문장 밖 문자에서 시작하는 토큰은
    앞 문장에 붙는다.
    """
    cuts = sorted(set(sent_starts) - {0})
    units, start, k = [], 0, 0
    for i, (s, _) in enumerate(offsets):
        while k < len(cuts) and s >= cuts[k]:
            if i > start:
                units.append((start, i))
                start = i
            k += 1
    if start < len(offsets):
        units.append((start, len(offsets)))
    out = []
    for a, b in units:
        out += [(i, min(i + chunk_tokens, b)) for i in range(a, b, chunk_tokens)]
    return out


def pack_units(units: list[tuple[int, int]], chunk_tokens: int,
               overlap_tokens: int) -> list[tuple[int, int]]:
    """연속한 단위를 토큰 합이 chunk_tokens 이하가 되게 묶는다(EXP-012 문장 경계 청킹).

    다음 청크는 앞 청크 끝 단위들 중 합이 overlap_tokens 이하인 만큼을 다시 넣고 시작하며,
    최소 한 단위는 앞으로 나아간다. 각 단위는 chunk_tokens 이하여야 한다.
    """
    spans, i = [], 0
    while i < len(units):
        j, n = i, 0
        while j < len(units) and n + units[j][1] - units[j][0] <= chunk_tokens:
            n += units[j][1] - units[j][0]
            j += 1
        spans.append((units[i][0], units[j - 1][1]))
        if j == len(units):
            break
        k, o = j, 0
        while k - 1 > i and o + units[k - 1][1] - units[k - 1][0] <= overlap_tokens:
            o += units[k - 1][1] - units[k - 1][0]
            k -= 1
        i = k
    return spans


def chunk_sentences(tokenizer, kiwi, text: str, chunk_tokens: int, overlap_tokens: int):
    """문장 경계 청킹. 결과 형식은 chunk_text와 같다(시작 문자, 끝 문자, 토큰 수)."""
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    offs = enc["offset_mapping"]
    if not offs:
        return []
    units = sentence_units(offs, [s.start for s in kiwi.split_into_sents(text)], chunk_tokens)
    return [(offs[a][0], offs[b - 1][1], b - a)
            for a, b in pack_units(units, chunk_tokens, overlap_tokens)]


def make_chunker(ch, tokenizer):
    """청킹 설정(name, chunk_tokens, overlap_tokens)에 맞는 함수 text → [(시작, 끝, 토큰 수)].

    fixed는 고정 토큰(S4), sentence는 문장 경계(EXP-012)다. Kiwi는 sentence일 때만 불러온다.
    """
    if ch.name == "fixed":
        return lambda text: chunk_text(tokenizer, text, ch.chunk_tokens, ch.overlap_tokens)
    if ch.name == "sentence":
        from kiwipiepy import Kiwi

        kiwi = Kiwi()
        return lambda text: chunk_sentences(tokenizer, kiwi, text, ch.chunk_tokens,
                                            ch.overlap_tokens)
    raise ValueError(f"알 수 없는 청킹 방식: {ch.name}")
