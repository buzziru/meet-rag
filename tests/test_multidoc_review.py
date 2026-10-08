from rag.multidoc.review import doc_heads, render


def test_render_numbers_docs_by_pool_order():
    check_in = "질의: q\n\n문서:\n[1] 회의 A\n본문\n[2] 회의 B\n[3] 회의 C\n"
    q = {
        "qid": "md-conf-0001", "type": "conf", "query_form": "쟁점형", "query": "q",
        "pool_doc_ids": ["a", "b", "c"], "gold_doc_ids": ["c", "a"], "answer": "ans",
        "elements": [{"fact": "f", "support": [{"doc_id": "c", "quote": "인용"}]}],
    }

    text = render(q, doc_heads(check_in), "data/multidoc/check_in/conf-0001.md")

    assert "- D3: 회의 C\n- D1: 회의 A" in text
    assert "   - D3: 인용" in text
    assert "- 판정:" in text
