from rag.multidoc.freeze import excluded
from rag.multidoc.review import agenda_items, doc_heads, jobs, render, scope_target


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


def test_agenda_items_drops_proposers_and_splits():
    agenda = "1. 가법 일부개정법률안(홍 의원 대표발의)(홍․김 의원 발의)(계속)2. 나법안(의안번호 12)"

    assert agenda_items(agenda) == ["1. 가법 일부개정법률안(계속)", "2. 나법안(의안번호 12)"]


def test_scope_target_needs_both_terms():
    assert scope_target("두 회의에서 각각 논의된 쟁점은?", "각각", "쟁점|질의와 답변")
    assert not scope_target("두 회의에서 논의된 쟁점은?", "각각", "쟁점|질의와 답변")


def test_excluded_merges_groups():
    assert excluded({"sample": ["a", "b"], "scope": ["c"]}) == {"a", "b", "c"}


def test_jobs_respects_size_and_count():
    sizes = [("a", 40), ("b", 30), ("c", 10), ("d", 100), ("e", 1)]

    assert jobs(sizes, max_chars=70, max_queries=2) == [["a", "b"], ["c"], ["d"], ["e"]]
