"""블라인드 확인(S25): judge 판정을 보지 않고 사람이 매긴 판정으로 judge를 확인한다.

- 기본: gen_eval.blind.pool에만 있는 질의(판정용 base 밖)에서 m개를 골라 {out}_blind.md(사람이
  체크하는 검수 문서)와 {out}_key.jsonl(judge 판정, 집계 전까지 열지 않음)을 쓴다
- --score: 검수 문서의 체크를 정답 키와 맞춰 기준별 일치·κ·TPR·TNR과 질의 단위 bootstrap 구간을 낸다
검수 문서에는 judge의 판정·이유·점수를 넣지 않는다. 질의 원문이 있어 data/ 아래에만 둔다.
인자는 Hydra override(예: +exp=exp017).
"""

import json
import re
import sys

import numpy as np
from rapidfuzz import fuzz
from sklearn.metrics import cohen_kappa_score

from rag.eval.metrics import load_gold
from rag.gen_eval.checks import HANDLINGS, OUTCOMES, STATES
from rag.gen_eval.common import read_jsonl, stable
from rag.gen_eval.judge import sha
from rag.index import ROOT, load_cfg, refuse_existing

# 판정 종류: (이름, 선택지, 실패 클래스). 순서는 검수 문서 안의 순서다(근거를 읽는 판정을 앞에)
KINDS = {
    "state": ("정보 상태", STATES, None),
    "faith": ("충실성", ("뒷받침", "아님"), {"아님"}),
    "handling": ("거부 처리", HANDLINGS, None),
    "inclusion": ("핵심 답변 포함도", ("들어 있음", "아님"), {"아님"}),
    "relevance": ("답변 관련성", ("답함", "일부", "답하지 않음"), {"일부", "답하지 않음"}),
}
CORRECT = {"맞음", "상황 전달"}  # 판정표(OUTCOMES)에서 실패가 아닌 결과
SENT = re.compile(r"(?<=[.?!다요])\s+")
CHECK = re.compile(r"^- \[([ xX])\] (.+)$")
UNIT = re.compile(r"^#### (\S+) (\S+)")


def units(row: dict) -> list[dict]:
    """judge 결과 한 줄의 판정 단위. 단위 문장(진술·항목)은 judge가 만든 것을 그대로 쓴다."""
    out = []
    items = (row.get("item_eval") or {}).get("items") or []
    for i, it in enumerate(items):
        out.append({"kind": "state", "uid": f"state{i}", "text": it["item"], "judge": it["state"]})
    for i, v in enumerate((row.get("faithfulness") or {}).get("verdicts") or []):
        out.append({"kind": "faith", "uid": f"faith{i}", "text": v["statement"],
                    "judge": "뒷받침" if v["verdict"] == 1 else "아님"})
    for i, it in enumerate(items):
        out.append({"kind": "handling", "uid": f"handling{i}", "text": it["item"],
                    "judge": it["handling"], "outcome": it.get("outcome")})
    for i, c in enumerate((row.get("inclusion") or {}).get("checks") or []):
        out.append({"kind": "inclusion", "uid": f"inclusion{i}", "text": c["statement"],
                    "judge": "들어 있음" if c["present"] == 1 else "아님"})
    label = (row.get("relevance") or {}).get("label")
    if label:
        out.append({"kind": "relevance", "uid": "relevance", "text": "", "judge": label})
    return out


def failures(us: list[dict]) -> int:
    """judge가 실패로 본 단위 수. 거부 처리는 판정표 결과가 실패인 것을 센다."""
    return sum(u.get("outcome") not in CORRECT if u["kind"] == "handling"
               else u["judge"] in (KINDS[u["kind"]][2] or ()) for u in us)


def pool_only(base: list[dict], pool: list[dict]) -> list[dict]:
    """풀 결과 중 판정용 결과(base)에 없는 질의."""
    seen = {r["qid"] for r in base}
    return [r for r in pool if r["qid"] not in seen]


def check_same_generation(rows: list[dict], gens: dict[str, dict]) -> None:
    """judge가 채점한 답변과 검수 문서에 넣을 생성 기록이 같은 생성인지 레시피 지문으로 본다.
    다르면 사람이 보는 답변과 정답 키가 조용히 어긋난다(gen_rep·프롬프트가 다른 기록 등)."""
    bad = [r["qid"] for r in rows if r["qid"] not in gens
           or sha(stable(gens[r["qid"]]["recipe"])) != r["judge_recipe"]["gen_recipe_sha256"]]
    if bad:
        raise SystemExit(f"judge 결과와 생성 기록(paths.gen_runs)의 생성이 다르다: {bad[:5]}. "
                         "같은 +exp·prompt·gen_eval.gen_rep로 실행한다")


def pick(rows: list[dict], meeting: dict[str, str], m: int, clean_share: float,
         seed: int) -> list[dict]:
    """seed로 섞고 회의마다 첫 질의만 남긴 뒤, 실패 없는 질의 round(m·clean_share)개와
    실패가 많은 질의를 나머지만큼 고른다(한쪽이 모자라면 다른 쪽에서 채움). 섞은 순서로 돌려준다."""
    order = [rows[i] for i in np.random.default_rng(seed).permutation(len(rows))]
    seen, uniq = set(), []
    for r in order:
        if meeting[r["qid"]] not in seen:
            seen.add(meeting[r["qid"]])
            uniq.append(r)
    clean = [r for r in uniq if failures(units(r)) == 0]
    failing = sorted((r for r in uniq if failures(units(r))), key=lambda r: -failures(units(r)))
    k = round(m * clean_share)
    first = clean[:k] + failing[:m - k]
    rest = clean[k:] + failing[m - k:]  # 한쪽이 모자라면 다른 쪽에서 채운다
    chosen = {r["qid"] for r in first + rest[:m - len(first)]}
    if len(chosen) < m:
        raise SystemExit(f"고를 수 있는 질의가 {len(chosen)}개뿐이다(m = {m})")
    return [r for r in uniq if r["qid"] in chosen]


def hint(text: str, contexts: list[dict]) -> tuple[int, str]:
    """근거를 문장으로 나눠 문자열 유사도가 가장 높은 (근거 번호, 문장). 판정이 아니라 읽을 곳."""
    sents = [(i, s) for i, c in enumerate(contexts, 1) for s in SENT.split(c["text"]) if s.strip()]
    return max(sents, key=lambda x: fuzz.partial_ratio(text, x[1]))


def document(rows: list[dict], gens: dict[str, dict]) -> str:
    lines = ["# S25 블라인드 확인 검수 문서", "",
             "판정마다 선택지 하나의 `[ ]`를 `[x]`로 바꾼다. 이유는 필요할 때만 `이유:` 뒤에 쓴다.",
             "`찾을 곳`은 코드가 문자열 유사도로 고른 근거 문장이다. 읽을 곳을 줄이는 용도이고 "
             "판정이 아니다. 판정은 근거 전체를 보고 한다.", "",
             "판정 기준: 정보 상태는 근거 5개에 그 항목의 답이 있음·일부·없음·모호(예정·검토 중)·"
             "회피(답을 피함) 중 무엇인지, 충실성은 진술이 근거로 뒷받침되는지, 거부 처리는 답변이 "
             "그 항목을 어떻게 다뤘는지, 포함도는 핵심 진술이 답변에 들어 있는지, 관련성은 답변이 "
             "질문에 답하는지다.", ""]
    for n, r in enumerate(rows, 1):
        g = gens[r["qid"]]
        lines += [f"## {n}. {r['qid']}", "", f"**질문**: {g['query']}", "", "**답변**", "",
                  g["answer"], "", "<details><summary>근거 5개</summary>", ""]
        for i, c in enumerate(g["contexts"], 1):
            lines += [f"[{i}] {c['committee_name']} {c['date']}", "", c["text"], ""]
        lines += ["</details>", ""]
        for u in units(r):
            name, choices, _ = KINDS[u["kind"]]
            lines += [f"#### {r['qid']} {u['uid']} {name}", ""]
            if u["text"]:
                lines += [f"> {u['text']}", ""]
            if u["kind"] in ("state", "faith"):
                i, s = hint(u["text"], g["contexts"])
                lines += [f"찾을 곳 [{i}]: {s}", ""]
            lines += [f"- [ ] {c}" for c in choices] + ["", "이유:", ""]
    return "\n".join(lines)


def parse(text: str) -> tuple[dict[tuple[str, str], str], list[str]]:
    """검수 문서의 체크. (qid, uid) → 선택지와, 체크가 없거나 둘 이상인 단위 목록."""
    marks, cur, bad = {}, None, []
    for line in text.splitlines() + ["#### END END"]:
        if (u := UNIT.match(line)):
            if cur is not None and len(marks.get(cur, [])) != 1:
                bad.append(f"{cur[0]} {cur[1]}: 체크 {len(marks.get(cur, []))}개")
            cur = (u.group(1), u.group(2))
            marks.setdefault(cur, [])
        elif cur and (c := CHECK.match(line)) and c.group(1) != " ":
            marks[cur].append(c.group(2).strip())
    marks.pop(("END", "END"))
    return {k: v[0] for k, v in marks.items() if len(v) == 1}, bad


def reasons(text: str) -> dict[tuple[str, str], str]:
    """사용자가 남긴 이유. 어긋난 판정을 볼 때 쓴다."""
    out, cur = {}, None
    for line in text.splitlines():
        if (u := UNIT.match(line)):
            cur = (u.group(1), u.group(2))
        elif cur and line.startswith("이유:") and line[3:].strip():
            out[cur] = line[3:].strip()
    return out


def stats(pairs: list[tuple[str, str, str]], fail: set[str] | None, n_boot: int,
          seed: int) -> dict:
    """(qid, 사람, judge) 목록의 일치율·κ와 질의 단위 bootstrap 95% 구간, 실패 클래스 TPR·TNR."""
    def one(ps):
        h, j = [p[1] for p in ps], [p[2] for p in ps]
        agree = float(np.mean([a == b for a, b in zip(h, j, strict=True)]))
        kappa = cohen_kappa_score(h, j) if len(set(h) | set(j)) > 1 else float("nan")
        return agree, kappa

    agree, kappa = one(pairs)
    qids = sorted({p[0] for p in pairs})
    by_q = {q: [p for p in pairs if p[0] == q] for q in qids}
    rng = np.random.default_rng(seed)
    boots = np.array([one([p for q in rng.choice(qids, len(qids)) for p in by_q[q]])
                      for _ in range(n_boot)])
    out = {"n": len(pairs), "queries": len(qids), "agree": agree, "kappa": kappa,
           "agree_ci": tuple(np.nanquantile(boots[:, 0], [0.025, 0.975])),
           "kappa_ci": tuple(np.nanquantile(boots[:, 1], [0.025, 0.975]))}
    if fail:
        pos = [p for p in pairs if p[1] in fail]
        neg = [p for p in pairs if p[1] not in fail]
        out["tpr"] = (sum(p[2] in fail for p in pos), len(pos))
        out["tnr"] = (sum(p[2] not in fail for p in neg), len(neg))
    return out


def score(text: str, key: list[dict], n_boot: int, seed: int) -> dict[str, dict]:
    """기준별 통계. 거부 정확도는 사람의 (정보 상태, 처리)를 판정표에 넣은 결과와 judge의 판정표
    결과를 실패 여부로 맞춘다."""
    marks, bad = parse(text)
    missing = [f"{k['qid']} {k['uid']}" for k in key if (k["qid"], k["uid"]) not in marks]
    if bad or missing:
        raise SystemExit("체크를 고칠 판정:\n" + "\n".join(bad + [f"{m}: 없음" for m in missing]))
    res = {}
    for kind, (name, _, fail) in KINDS.items():
        pairs = [(k["qid"], marks[k["qid"], k["uid"]], k["judge"])
                 for k in key if k["kind"] == kind]
        res[name] = stats(pairs, fail, n_boot, seed)
    outcome = []
    for k in key:
        if k["kind"] == "handling":
            state = marks[k["qid"], k["uid"].replace("handling", "state")]
            human = OUTCOMES.get((state, marks[k["qid"], k["uid"]]))
            outcome.append((k["qid"], "실패" if human not in CORRECT else "맞음",
                            "실패" if k["outcome"] not in CORRECT else "맞음"))
    res["거부 정확도(판정표 결과)"] = stats(outcome, {"실패"}, n_boot, seed)
    return res


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--score"]
    cfg = load_cfg(["index.scope=full", *args])
    b = cfg.gen_eval.blind
    out = ROOT / b.out
    doc, keyf = out.with_name(out.name + "_blind.md"), out.with_name(out.name + "_key.jsonl")
    if "--score" in sys.argv:
        res = score(doc.read_text(encoding="utf-8"), read_jsonl(keyf), b.bootstrap, b.seed)
        print(json.dumps(res, ensure_ascii=False, indent=1, default=float))
        return
    refuse_existing(doc, cfg.search.overwrite)  # 사람이 채우는 파일
    refuse_existing(keyf, cfg.search.overwrite)
    rows = pool_only(read_jsonl(ROOT / b.base), read_jsonl(ROOT / b.pool))
    meeting = load_gold(cfg, "dev-full")["conference_number"].to_dict()
    chosen = pick(rows, meeting, b.m, b.clean_share, b.seed)
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    check_same_generation(chosen, gens)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(document(chosen, gens), encoding="utf-8", newline="\n")
    keys = [{"qid": r["qid"], **u} for r in chosen for u in units(r)]
    keyf.write_text("".join(json.dumps(k, ensure_ascii=False) + "\n" for k in keys),
                    encoding="utf-8", newline="\n")
    counts = {KINDS[k][0]: sum(u["kind"] == k for u in keys) for k in KINDS}
    print(f"질의 {len(chosen)}개, 판정 {len(keys)}개 {counts} -> {doc.relative_to(ROOT)}")
    print("dev_queries.yaml blind 목록에 더할 qid:", " ".join(r["qid"] for r in chosen))


if __name__ == "__main__":
    main()
