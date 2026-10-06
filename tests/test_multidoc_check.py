from omegaconf import OmegaConf

from rag.multidoc.check import build_messages, judge, quoted, quoted_support, to_doc_ids

POOL = ["a", "b", "c"]
CONTEXTS = {"a": "가 위원은  예산 증액을 요구했다. 끝.", "b": "나 장관은 검토하겠다고 답했다.",
            "c": "다 위원도 예산 증액을 요구했다."}


def gen(seed=("a", "b"), status="ok"):
    return {"status": status, "seed_doc_ids": list(seed), "query": "질의", "answer": "답",
            "evidence": [{"doc_id": "a", "quote": "예산 증액을 요구했다"},
                         {"doc_id": "b", "quote": "검토하겠다고"}]}


def el(*support):
    return {"fact": "f", "support": [{"doc_id": d, "quote": q} for d, q in support]}


def run(g, elements, answerable=True):
    return judge(g, elements, answerable, POOL, CONTEXTS, max_gold=2)


def test_quoted_collapses_whitespace():
    assert quoted("가 위원은 예산", CONTEXTS["a"])
    assert not quoted("가 위원이 예산", CONTEXTS["a"])
    assert not quoted("  ", CONTEXTS["a"])


def test_pass_when_each_gold_doc_has_unique_element():
    v = run(gen(), [el(("a", "가 위원은 예산 증액")), el(("b", "검토하겠다고 답했다"))])
    assert v == {"passed": True, "reasons": [], "gold_doc_ids": ["a", "b"], "dropped_quotes": 0}


def test_quote_missing_in_gen():
    g = gen()
    g["evidence"][1]["quote"] = "검토할 것"
    assert run(g, [el(("a", "예산")), el(("b", "검토"))])["reasons"] == ["quote_missing"]


def test_check_quote_not_in_context_is_dropped():
    # c의 인용이 원문에 없으면 그 support만 빠져 a가 유일한 근거가 된다
    v = run(gen(), [el(("a", "예산 증액"), ("c", "없는 문장")), el(("b", "검토"))])
    assert v == {"passed": True, "reasons": [], "gold_doc_ids": ["a", "b"], "dropped_quotes": 1}
    # 요소의 근거가 모두 빠지면 요소도 빠져 b만 남는다
    v = run(gen(), [el(("a", "없는 문장")), el(("b", "검토")), el((None, "예산"))])
    assert v["reasons"] == ["single_doc", "seed_mismatch"] and v["dropped_quotes"] == 2


def test_quoted_support_keeps_only_quotes_in_context():
    els = [el(("a", "예산 증액"), ("c", "없는 문장")), el((None, "예산"))]
    assert quoted_support(els, CONTEXTS) == [el(("a", "예산 증액"))]


def test_unanswerable():
    assert "unanswerable" in run(gen(), [el(("a", "예산")), el(("b", "검토"))], False)["reasons"]


def test_single_doc():
    v = run(gen(), [el(("a", "예산")), el(("a", "가 위원"))])
    assert "single_doc" in v["reasons"] and "seed_mismatch" in v["reasons"]


def test_substitutable_when_doc_has_no_unique_element():
    # a의 유일한 요소를 c도 담고 있어 a는 대신할 수 있다
    v = run(gen(), [el(("a", "예산 증액"), ("c", "예산 증액")), el(("b", "검토"))])
    assert "substitutable" in v["reasons"]
    assert v["gold_doc_ids"] == ["a", "b", "c"]


def test_seed_mismatch_when_checker_finds_other_docs():
    v = run(gen(), [el(("a", "예산")), el(("b", "검토")), el(("c", "다 위원"))])
    assert v["reasons"] == ["seed_mismatch"]


def test_gen_skip_and_invalid():
    assert run(gen(status="skip"), None, False)["reasons"] == ["gen_skip"]
    v = run(gen(seed=("a", "z")), [el(("a", "예산")), el(("b", "검토"))])
    assert "gen_invalid" in v["reasons"]


def test_gen_invalid_over_max_gold_or_missing_pool_seed():
    g = gen(seed=("a", "b", "c"))
    g["evidence"].append({"doc_id": "c", "quote": "다 위원도"})
    els = [el(("a", "가 위원")), el(("b", "검토")), el(("c", "다 위원"))]
    assert "gen_invalid" in run(g, els)["reasons"]
    assert judge(g, els, True, POOL, CONTEXTS, max_gold=3)["passed"]
    v = judge(gen(), [el(("a", "예산")), el(("b", "검토"))], True, POOL, CONTEXTS, 3, ["c"])
    assert "gen_invalid" in v["reasons"]


def test_to_doc_ids_maps_numbers_and_flags_out_of_range():
    support = [{"doc": 2, "quote": "q"}, {"doc": 9, "quote": "q"}]
    out = to_doc_ids([{"fact": "f", "support": support}], POOL)
    assert [s["doc_id"] for s in out[0]["support"]] == ["b", None]
    v = run(gen(), [el(("a", "예산")), el(("b", "검토")), el((None, "x"))])
    assert v["passed"] and v["dropped_quotes"] == 1


def test_build_messages_sends_only_query_and_pool_docs():
    prompt = OmegaConf.create({"system": "S",
                               "document": "[{n}] {date} {agenda} {speakers}\n{text}",
                               "user": "Q: {query}\n{documents}"})
    meta = {k: "m" for k in ["date", "committee_name", "meeting_name", "meeting_number",
                             "session_number", "agenda"]}
    docs = {d: {"context": CONTEXTS[d], "speakers": [{"name": "김", "position": "위원"}], **meta}
            for d in POOL}
    msgs = build_messages(prompt, "질의", POOL, docs)
    user = msgs[1]["content"]
    assert user.startswith("Q: 질의")
    assert "[1] m m 김 위원" in user and "[3] m m" in user and "[4]" not in user
    assert "답" not in user.replace("답했다", "")  # 기대 답을 보내지 않는다
