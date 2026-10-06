from omegaconf import OmegaConf

from rag.multidoc.check import build_messages, judge, locate, quoted, resolve, to_doc_ids

POOL = ["a", "b", "c"]
CONTEXTS = {"a": "가 위원은  예산 증액을 요구했다. 끝.", "b": "나 장관은 검토하겠다고 답했다.",
            "c": "다 위원도 예산 증액을 요구했다."}
MATCH = OmegaConf.create({"min_ratio": 0.8, "min_chars": 15})


def gen(seed=("a", "b"), status="ok"):
    return {"status": status, "seed_doc_ids": list(seed), "query": "질의", "answer": "답",
            "evidence": [{"doc_id": "a", "quote": "예산 증액을 요구했다"},
                         {"doc_id": "b", "quote": "검토하겠다고"}]}


def el(*support):
    return {"fact": "f", "support": [{"doc_id": d, "quote": q} for d, q in support]}


def run(g, elements, answerable=True):
    return judge(g, elements, answerable, POOL, CONTEXTS, max_gold=2, match=MATCH)


def test_quoted_collapses_whitespace():
    assert quoted("가 위원은 예산", CONTEXTS["a"])
    assert not quoted("가 위원이 예산", CONTEXTS["a"])
    assert not quoted("  ", CONTEXTS["a"])


def test_pass_when_each_gold_doc_has_unique_element():
    v = run(gen(), [el(("a", "가 위원은 예산 증액")), el(("b", "검토하겠다고 답했다"))])
    assert v == {"passed": True, "reasons": [], "gold_doc_ids": ["a", "b"], "dropped_quotes": 0,
                 "fixed_quotes": 0}


def test_locate_accepts_rephrased_quote_and_returns_source_span():
    assert locate("가 위원은 예산", CONTEXTS["a"], MATCH) == "가 위원은 예산"
    # 접속어를 붙여 옮긴 인용은 어절 경계에 맞춘 원문 대목으로 바뀐다
    span = locate("그런데 가 위원은 예산 증액을 요구했다.", CONTEXTS["a"], MATCH)
    assert span == "가 위원은 예산 증액을 요구했다. 끝."
    assert locate("없는 문장인데 꽤 길게 써서 열다섯 자를 넘긴다", CONTEXTS["c"], MATCH) is None


def test_locate_matches_short_quote_only_exactly():
    # 15자 미만은 비슷해도 인정하지 않는다(격식어가 우연히 겹치는 경우)
    quote = "나 장관은 검토하겠다고 답했다"
    assert locate(quote, CONTEXTS["b"], MATCH) == quote
    assert locate("나 장관은 검토했다고", CONTEXTS["b"], MATCH) is None


def test_quote_missing_in_gen():
    g = gen()
    g["evidence"][1]["quote"] = "검토할 것"
    assert run(g, [el(("a", "예산")), el(("b", "검토"))])["reasons"] == ["quote_missing"]


def test_rephrased_check_quote_counts_as_support():
    v = run(gen(), [el(("a", "그런데 가 위원은 예산 증액을 요구했다.")), el(("b", "검토"))])
    assert v["passed"] and v["fixed_quotes"] == 1 and v["dropped_quotes"] == 0


def test_unmatched_check_quote_that_does_not_change_verdict_is_dropped():
    # a의 맞추지 못한 인용은 a·b 모두 유일한 요소가 있어 판정을 바꾸지 않는다
    els = [el(("a", "예산 증액")), el(("b", "검토")), el(("a", "없는 문장"), ("b", "답했다"))]
    v = run(gen(), els)
    assert v["passed"] and v["dropped_quotes"] == 1


def test_quote_dependent_when_unmatched_quote_changes_verdict():
    # c의 인용을 빼면 통과, 두면 c가 정답에 들어가 불통과
    v = run(gen(), [el(("a", "예산 증액"), ("c", "없는 문장")), el(("b", "검토"))])
    assert v["reasons"] == ["quote_dependent"] and v["gold_doc_ids"] == ["a", "b"]
    # a의 유일한 근거를 빼면 불통과, 두면 통과
    v = run(gen(), [el(("a", "없는 문장")), el(("b", "검토")), el((None, "예산"))])
    assert v["reasons"] == ["single_doc", "seed_mismatch", "quote_dependent"]
    assert v["dropped_quotes"] == 2


def test_resolve_replaces_quotes_with_source_span():
    els = [el(("a", "예산 증액"), ("c", "없는 문장")), el((None, "예산"))]
    matched, kept, fixed = resolve(els, CONTEXTS, MATCH)
    assert matched == [el(("a", "예산 증액"))]
    assert kept == [el(("a", "예산 증액"), ("c", "없는 문장"))] and fixed == 0


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
    assert judge(g, els, True, POOL, CONTEXTS, max_gold=3, match=MATCH)["passed"]
    v = judge(gen(), [el(("a", "예산")), el(("b", "검토"))], True, POOL, CONTEXTS, 3, ["c"],
              match=MATCH)
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
