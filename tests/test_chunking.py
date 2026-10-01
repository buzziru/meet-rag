import pytest

from rag.chunking import chunk_spans


def offsets(n, width=3):
    """토큰 n개, 각 토큰은 문자 width개 + 공백 1개."""
    return [(i * (width + 1), i * (width + 1) + width) for i in range(n)]


@pytest.mark.parametrize("n, ct, ov", [(10, 4, 1), (100, 16, 2), (17, 8, 0), (9, 4, 3)])
def test_chunks_bounded_overlapping_and_covering(n, ct, ov):
    offs = offsets(n)
    text = " ".join("abc" for _ in range(n))
    spans = chunk_spans(offs, ct, ov)
    first_tok = {s: i for i, (s, _) in enumerate(offs)}
    last_tok = {e: i for i, (_, e) in enumerate(offs)}

    assert all(k <= ct for _, _, k in spans)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)  # 문서 전체를 덮는다
    for (_, e1, _), (s2, _, _) in zip(spans, spans[1:], strict=False):
        assert last_tok[e1] - first_tok[s2] + 1 == ov  # 이웃 청크는 정확히 ov 토큰 겹친다
    assert all(text[s:e] in text for s, e, _ in spans)


def test_short_doc_is_one_chunk():
    assert chunk_spans(offsets(5), 8, 1) == [(0, 19, 5)]


def test_exact_fit_has_no_trailing_chunk():
    assert len(chunk_spans(offsets(8), 8, 2)) == 1
    assert len(chunk_spans(offsets(14), 8, 2)) == 2


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValueError):
        chunk_spans(offsets(5), 4, 4)
