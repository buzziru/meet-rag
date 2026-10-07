import json

from omegaconf import OmegaConf

from rag.multidoc.check import (
    candidates,
    check_input,
    fill_quote_checks,
    found,
    judge,
    pool_state,
    quote_probs,
    quoted,
    resolve,
    take_output,
    to_doc_ids,
)

POOL = ["a", "b", "c"]
CONTEXTS = {"a": "가 위원은  예산 증액을 요구했다. 끝.", "b": "나 장관은 검토하겠다고 답했다.",
            "c": "다 위원도 예산 증액을 요구했다."}
REPHRASED = "그런데 가 위원은 예산 증액을 요구했다."
# Jev가 같은 의미로 판정한 확률(원문에 그대로 없는 인용만 기록된다)
PROBS = {("a", REPHRASED): 0.95, ("c", "예산 증액을 줄이자고 했다"): 0.4}
MIN_PROB = 0.9
SEM = OmegaConf.create({"top_k": 2, "window_sentences": 1, "model": "m", "prompt_version": "v"})


def gen(seed=("a", "b"), status="ok"):
    return {"status": status, "seed_doc_ids": list(seed), "query": "질의", "answer": "답",
            "evidence": [{"doc_id": "a", "quote": "예산 증액을 요구했다"},
                         {"doc_id": "b", "quote": "검토하겠다고"}]}


def el(*support):
    return {"fact": "f", "support": [{"doc_id": d, "quote": q} for d, q in support]}


def run(g, elements, answerable=True):
    return judge(g, elements, answerable, POOL, CONTEXTS, max_gold=2, probs=PROBS,
                 min_prob=MIN_PROB)


def test_quoted_collapses_whitespace():
    assert quoted("가 위원은 예산", CONTEXTS["a"])
    assert not quoted("가 위원이 예산", CONTEXTS["a"])
    assert not quoted("  ", CONTEXTS["a"])


def test_pass_when_each_gold_doc_has_unique_element():
    v = run(gen(), [el(("a", "가 위원은 예산 증액")), el(("b", "검토하겠다고 답했다"))])
    assert v == {"passed": True, "reasons": [], "gold_doc_ids": ["a", "b"], "dropped_quotes": 0}


def test_found_uses_exact_match_or_jev_probability():
    assert found("가 위원은 예산", CONTEXTS["a"], None, MIN_PROB)
    assert found(REPHRASED, CONTEXTS["a"], 0.95, MIN_PROB)
    assert not found(REPHRASED, CONTEXTS["a"], 0.4, MIN_PROB)
    # 판정 전(확률 없음)이면 원문에 그대로 있을 때만 인정한다
    assert not found(REPHRASED, CONTEXTS["a"], None, MIN_PROB)
    assert not found("  ", CONTEXTS["a"], 1.0, MIN_PROB)


def test_candidates_returns_most_similar_sentence_windows():
    context = "첫 문장입니다. 예산 증액을 요구했다. 마지막 문장입니다."
    assert candidates("예산 증액을 꼭 요구했다.", context, 1, 1) == ["예산 증액을 요구했다."]
    assert candidates("예산 증액을 꼭 요구했다.", context, 2, 2)[0] in (
        "첫 문장입니다. 예산 증액을 요구했다.", "예산 증액을 요구했다. 마지막 문장입니다.")


def test_fill_quote_checks_asks_only_unmatched_quotes_once():
    els = [el(("a", REPHRASED), ("a", "가 위원은 예산")), el((None, "x"))]
    rec = {"gen": gen(), "elements": els}
    asked = []

    def ask(q, passages):
        asked.append((q, passages))
        return {"p": 0.95, "usage": {"input_tokens": 1, "cost": 0.0}}

    assert fill_quote_checks(rec, CONTEXTS, SEM, ask) == 1
    assert [q for q, _ in asked] == [REPHRASED] and len(asked[0][1]) == 2
    assert quote_probs(rec, SEM) == {("a", REPHRASED): 0.95}
    # 이미 판정한 인용은 다시 묻지 않는다
    assert fill_quote_checks(rec, CONTEXTS, SEM, ask) == 0 and len(asked) == 1
    # 질문 버전을 바꾸면 이전 판정을 쓰지 않고 다시 묻는다
    sem2 = OmegaConf.merge(SEM, {"prompt_version": "v2"})
    assert quote_probs(rec, sem2) == {}
    assert fill_quote_checks(rec, CONTEXTS, sem2, ask) == 1 and len(asked) == 2


def test_quote_missing_in_gen():
    g = gen()
    g["evidence"][1]["quote"] = "검토할 것"
    assert run(g, [el(("a", "예산")), el(("b", "검토"))])["reasons"] == ["quote_missing"]


def test_rephrased_check_quote_counts_as_support():
    v = run(gen(), [el(("a", REPHRASED)), el(("b", "검토"))])
    assert v["passed"] and v["dropped_quotes"] == 0


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


def test_resolve_keeps_quotes_as_given():
    q, low = REPHRASED, "예산 증액을 줄이자고 했다"
    els = [el(("a", q), ("c", low)), el((None, "예산"))]
    matched, kept = resolve(els, CONTEXTS, PROBS, MIN_PROB)
    assert matched == [el(("a", q))]
    assert kept == [el(("a", q), ("c", low))]


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
    assert judge(g, els, True, POOL, CONTEXTS, max_gold=3, probs=PROBS, min_prob=MIN_PROB)[
        "passed"
    ]
    v = judge(gen(), [el(("a", "예산")), el(("b", "검토"))], True, POOL, CONTEXTS, 3, ["c"],
              probs=PROBS, min_prob=MIN_PROB)
    assert "gen_invalid" in v["reasons"]


def test_to_doc_ids_maps_numbers_and_flags_out_of_range():
    support = [{"doc": 2, "quote": "q"}, {"doc": 9, "quote": "q"}]
    out = to_doc_ids([{"fact": "f", "support": support}], POOL)
    assert [s["doc_id"] for s in out[0]["support"]] == ["b", None]
    v = run(gen(), [el(("a", "예산")), el(("b", "검토")), el((None, "x"))])
    assert v["passed"] and v["dropped_quotes"] == 1


def test_check_input_has_only_instruction_query_and_pool_docs():
    prompt = OmegaConf.create({"system": "S",
                               "document": "[{n}] {date} {agenda} {speakers}\n{text}",
                               "user": "Q: {query}\n{documents}"})
    meta = {k: "m" for k in ["date", "committee_name", "meeting_name", "meeting_number",
                             "session_number", "agenda"]}
    docs = {d: {"context": CONTEXTS[d], "speakers": [{"name": "김", "position": "위원"}], **meta}
            for d in POOL}
    text = check_input(prompt, "질의", POOL, docs)
    assert text.startswith("# 지시\n\nS\n\n# 입력\n\nQ: 질의")
    assert "[1] m m 김 위원" in text and "[3] m m" in text and "[4]" not in text
    assert "답" not in text.replace("답했다", "")  # 기대 답을 넣지 않는다


def test_take_output_moves_partial_or_malformed_output_to_rejected(tmp_path):
    good = {"answerable": True, "elements": [{"fact": "f", "support": [{"doc": 1, "quote": "q"}]}]}
    (tmp_path / "ok.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "cut.json").write_text('{"answerable": true, "elem', encoding="utf-8")
    bad = {"answerable": True, "elements": [{"fact": "f", "support": [{"doc": "1", "quote": "q"}]}]}
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    assert take_output(tmp_path / "ok.json") == good
    assert take_output(tmp_path / "cut.json") is None
    assert take_output(tmp_path / "bad.json") is None
    assert sorted(f.name for f in (tmp_path / "rejected").iterdir()) == ["bad.json", "cut.json"]
    assert (tmp_path / "ok.json").exists() and not (tmp_path / "cut.json").exists()


def test_pool_state_follows_files_so_work_resumes(tmp_path):
    dirs = {k: tmp_path / k for k in ["gen_in", "gen_out", "check_in", "check_out", "check"]}
    for d in dirs.values():
        d.mkdir()

    def put(k, name, data="{}"):
        (dirs[k] / name).write_text(data, encoding="utf-8")

    assert pool_state("p", dirs) == "none"
    put("gen_in", "p.json")
    assert pool_state("p", dirs) == "gen_wait"
    put("gen_out", "p.json", json.dumps({"status": "ok"}))
    assert pool_state("p", dirs) == "prepare"
    put("check_in", "p.md", "")
    assert pool_state("p", dirs) == "check_wait"
    put("check_out", "p.json")
    assert pool_state("p", dirs) == "judge_wait"
    put("check", "p.json")
    assert pool_state("p", dirs) == "done"
    # 생성 skip은 검사 없이 판정 대기다
    put("gen_out", "q.json", json.dumps({"status": "skip"}))
    assert pool_state("q", dirs) == "judge_wait"
