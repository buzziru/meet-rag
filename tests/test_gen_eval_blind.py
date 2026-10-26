import pytest

from rag.gen_eval.blind import document, parse, pick, pool_only, reasons, score, units


def row(qid, faith=(1,), present=(1,), label="답함", items=(("있음", "답함", "맞음"),)):
    return {"qid": qid,
            "faithfulness": {"verdicts": [{"statement": f"{qid} 진술{i}", "verdict": v,
                                           "reason": "JUDGE_REASON"} for i, v in enumerate(faith)]},
            "inclusion": {"checks": [{"statement": f"{qid} 핵심{i}", "present": p,
                                      "reason": "JUDGE_REASON"} for i, p in enumerate(present)]},
            "relevance": {"label": label, "reason": "JUDGE_REASON"},
            "item_eval": {"items": [{"item": f"{qid} 항목{i}", "state": s, "handling": h,
                                     "outcome": o, "reason": "JUDGE_REASON"}
                                    for i, (s, h, o) in enumerate(items)]}}


def gen(qid):
    ctx = [{"committee_name": "위원회", "date": "2020-01-01",
            "text": f"{qid} 진술0 내용이다. 다른 문장이다."}]
    return {"qid": qid, "query": "질문", "answer": "답변", "contexts": ctx * 5}


def test_units_order_reads_contexts_first():
    kinds = [u["kind"] for u in units(row("q"))]
    assert kinds == ["state", "faith", "handling", "inclusion", "relevance"]


def test_pick_is_deterministic_one_per_meeting_with_clean_share():
    rows = [row(f"q{i}", faith=(0,) if i % 2 else (1,)) for i in range(20)]
    meeting = {f"q{i}": f"m{i // 2}" for i in range(20)}  # 두 질의씩 같은 회의
    a = pick(rows, meeting, 6, 0.33, 1)
    assert [r["qid"] for r in a] == [r["qid"] for r in pick(rows, meeting, 6, 0.33, 1)]
    assert len({meeting[r["qid"]] for r in a}) == 6
    clean = sum(r["faithfulness"]["verdicts"][0]["verdict"] == 1 for r in a)
    assert clean >= 2  # round(6·0.33). 실패 질의가 모자라면 실패 없는 질의로 채운다


def test_pool_excludes_judging_set():
    base = [row("q0"), row("q1")]
    assert [r["qid"] for r in pool_only(base, base + [row("q2")])] == ["q2"]


def test_pick_stops_when_pool_too_small():
    with pytest.raises(SystemExit):
        pick([row("q0")], {"q0": "m"}, 2, 0.5, 1)


def test_document_hides_judge_output():
    text = document([row("q", faith=(0,), present=(0,), label="일부")], {"q": gen("q")})
    assert "JUDGE_REASON" not in text and "- [x]" not in text
    assert "찾을 곳 [1]: q 진술0 내용이다." in text


def check(text, choices):
    """단위 순서대로 선택지를 체크한 문서."""
    out, it = [], iter(choices)
    pending = None
    for line in text.splitlines():
        if line.startswith("#### "):
            pending = next(it)
        if pending and line == f"- [ ] {pending}":
            line, pending = f"- [x] {pending}", None
        out.append(line)
    return "\n".join(out)


def test_parse_reports_missing_and_double_checks():
    text = document([row("q")], {"q": gen("q")})
    _, bad = parse(text)
    assert len(bad) == 5
    doubled = text.replace("- [ ] 답함", "- [x] 답함")  # 처리·관련성 단위에 같은 선택지
    marks, bad = parse(check(doubled, ["있음", "뒷받침", "거부", "들어 있음", "일부"]))
    assert any("체크 2개" in b for b in bad)


def test_score_agreement_and_refusal_outcome():
    r = row("q", faith=(1, 0), items=(("있음", "답함", "맞음"),))
    text = document([r], {"q": gen("q")})
    key = [{"qid": "q", **u} for u in units(r)]
    # 사람: 정보 상태 있음·처리 거부(판정표 과잉 거부 = 실패), 충실성 하나 다름
    done = check(text, ["있음", "뒷받침", "뒷받침", "거부", "들어 있음", "답함"])
    done = done.replace("\n이유:\n", "\n이유: 근거 2에 있다\n", 1)
    res = score(done, key, 50, 1)
    assert res["충실성"]["agree"] == 0.5
    assert res["충실성"]["tpr"] == (0, 0) and res["충실성"]["tnr"] == (1, 2)
    assert res["거부 정확도(판정표 결과)"]["tpr"] == (0, 1)
    assert res["답변 관련성"]["agree"] == 1.0
    assert reasons(done) == {("q", "state0"): "근거 2에 있다"}


def test_check_same_generation_stops_on_other_recipe():
    from rag.gen_eval.blind import check_same_generation
    from rag.gen_eval.common import stable
    from rag.gen_eval.judge import sha
    recipe = {"prompt": "v2", "git_commit": "a"}
    r = {**row("q"), "judge_recipe": {"gen_recipe_sha256": sha(stable(recipe))}}
    # 커밋만 다르면 같은 생성이다
    check_same_generation([r], {"q": {"recipe": {**recipe, "git_commit": "b"}}})
    with pytest.raises(SystemExit):
        check_same_generation([r], {"q": {"recipe": {**recipe, "prompt": "v1"}}})
