"""multi-doc 생성 결과를 다른 모델(OpenRouter)로 검사하고 코드로 판정한다.

명세는 docs/slices/08-multidoc-queries.md. 검사 호출에는 질의와 후보 집합 전체 원문만 보내고,
생성 쪽 시작 묶음·기대 답·근거는 보내지 않는다. 검사 기록이 이미 있는 후보 집합은 건너뛴다(재사용).

    uv run python -m rag.multidoc.check [--dry-run] [hydra override...]
"""

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from rag.multidoc.prepare import META, load_docs, select, speaker_text

ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = ROOT / "configs" / "multidoc" / "prompt"

SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "elements": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "support": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"doc": {"type": "integer"}, "quote": {"type": "string"}},
                    "required": ["doc", "quote"], "additionalProperties": False}},
            },
            "required": ["fact", "support"], "additionalProperties": False}},
    },
    "required": ["answerable", "elements"],
    "additionalProperties": False,
}


def norm(text: str) -> str:
    return " ".join(text.split())


def quoted(quote: str, context: str) -> bool:
    """인용이 원문의 부분 문자열인가(공백을 한 칸으로 줄여 대조)."""
    q = norm(quote)
    return bool(q) and q in norm(context)


def best_window(q: str, c: str) -> tuple[float, int]:
    """공백을 줄인 인용 q와 원문 c에서 가장 비슷한 q 길이 대목의 (문자 유사도, 시작 위치).

    가장 긴 공통 부분으로 위치를 잡고 그 앞뒤로 q 길이의 4분의 1 안에서 찾는다.
    """
    n = len(q)
    m = SequenceMatcher(None, c, q, autojunk=False).find_longest_match(0, len(c), 0, n)
    best, at = 0.0, 0
    for s in range(max(0, m.a - m.b - n // 4), max(0, min(len(c) - 1, m.a - m.b + n // 4)) + 1):
        ratio = SequenceMatcher(None, q, c[s:s + n], autojunk=False).ratio()
        if ratio > best:
            best, at = ratio, s
    return best, at


def locate(quote: str, context: str, match) -> str | None:
    """인용에 해당하는 원문 대목(공백을 한 칸으로 줄인 것)을 찾는다. 없으면 None.

    부분 문자열이면 인용 그대로다. 인용이 match.min_chars자 이상이면 best_window로 인용과 길이가
    같은 대목 중 문자 유사도(difflib 비율)가 가장 높은 것을 찾는다. 유사도가 match.min_ratio
    이상이면 그 대목을 어절 경계까지 넓혀 돌려준다(맨 앞 어절이 앞 문장의 끝이면 뺀다). LLM이 접속어·존칭·낱말을 바꿔 옮긴 인용을
    받아들이고, 짧은 인용은 격식어가 우연히 겹쳐 유사도가 높게 나오므로 정확 대조만 한다(D-14).
    """
    q, c = norm(quote), norm(context)
    if not q:
        return None
    if q in c:
        return q
    n = len(q)
    if n < match.min_chars:
        return None
    best, at = best_window(q, c)
    if best < match.min_ratio:
        return None
    lo = c.rfind(" ", 0, at + 1) + 1
    hi = c.find(" ", min(at + n, len(c)) - 1)
    words = c[lo:hi if hi >= 0 else len(c)].split(" ")
    if len(words) > 1 and words[0][-1] in ".?!…":  # 앞 문장의 끝 어절은 뺀다
        words = words[1:]
    return " ".join(words)


def resolve(elements: list[dict], contexts: dict[str, str],
            match) -> tuple[list[dict], list[dict], int]:
    """검사 쪽 support를 원문 대목과 맞춘다.

    (맞춘 것만 남긴 요소, 못 맞춘 것도 남긴 요소, 유사도로 맞춰 quote를 바꾼 수)를 반환한다. 맞춘
    support의 quote는 원문 대목으로 바꾼다. 앞쪽은 support가 모두 빠진 요소를 뺀다. 문서 번호가
    범위 밖인 support는 둘 다에서 뺀다.
    """
    matched, kept, fixed = [], [], 0
    for el in elements:
        ok, rest = [], []
        for s in el["support"]:
            span = (locate(s["quote"], contexts[s["doc_id"]], match)
                    if s["doc_id"] in contexts else None)
            if span is not None:
                ok.append({**s, "quote": span})
                fixed += span != norm(s["quote"])
            elif s["doc_id"] in contexts:
                rest.append(s)
        if ok:
            matched.append({**el, "support": ok})
        if ok or rest:
            kept.append({**el, "support": ok + rest})
    return matched, kept, fixed


def gold_reasons(elements: list[dict], seed: list[str]) -> tuple[list[str], list[str]]:
    """정답 문서와 규칙 3~5의 사유(single_doc, substitutable, seed_mismatch)."""
    supports = [{s["doc_id"] for s in el["support"]} for el in elements]
    gold = sorted(set().union(*supports)) if supports else []
    unique = {next(iter(s)) for s in supports if len(s) == 1}
    reasons = [r for r, bad in [("single_doc", len(gold) < 2),
                                ("substitutable", bool(set(gold) - unique)),
                                ("seed_mismatch", set(gold) != set(seed))] if bad]
    return gold, reasons


def judge(gen: dict, elements: list[dict] | None, answerable: bool, pool_doc_ids: list[str],
          contexts: dict[str, str], max_gold: int, pool_seed: list[str] = (), *,
          match) -> dict:
    """생성·검사 결과로 통과 여부를 정한다.

    생성 쪽 정답 문서는 2개 이상 max_gold개 이하이고, S7 시작 묶음(pool_seed)을 모두 포함해야 한다.
    elements의 support는 {"doc_id", "quote"} 목록이다(번호를 doc_id로 바꾼 뒤). 번호가 범위 밖이면
    doc_id는 None이다. 인용은 locate로 원문과 맞춘다(match). 생성 쪽 인용을 맞추지 못하면
    quote_missing이다. 검사 쪽 인용을 맞추지 못한 support는 확인할 수 없는 근거라, 빼고 판정한
    결과와 두고 판정한 결과가 다르면 quote_dependent로 불통과한다(D-14). 사유를 모두 모으고,
    사유가 없으면 통과다. 정답 문서는 맞춘 support로 정한다.
    """
    if gen["status"] != "ok":
        return {"passed": False, "reasons": ["gen_skip"], "gold_doc_ids": [],
                "dropped_quotes": 0, "fixed_quotes": 0}
    reasons = []
    seed = gen["seed_doc_ids"]
    if not (2 <= len(seed) <= max_gold and len(set(seed)) == len(seed)
            and set(pool_seed) <= set(seed) <= set(pool_doc_ids)
            and {e["doc_id"] for e in gen["evidence"]} == set(seed)):
        reasons.append("gen_invalid")

    if not all(e["doc_id"] in contexts
               and locate(e["quote"], contexts[e["doc_id"]], match) is not None
               for e in gen["evidence"]):
        reasons.append("quote_missing")
    if not answerable:
        reasons.append("unanswerable")
    matched, kept, fixed = resolve(elements, contexts, match)
    gold, rules = gold_reasons(matched, seed)
    reasons += rules
    if bool(rules) != bool(gold_reasons(kept, seed)[1]):
        reasons.append("quote_dependent")
    n_support = sum(len(el["support"]) for el in elements)
    n_matched = sum(len(el["support"]) for el in matched)
    return {"passed": not reasons, "reasons": reasons, "gold_doc_ids": gold,
            "dropped_quotes": n_support - n_matched, "fixed_quotes": fixed}


def build_messages(prompt, query: str, pool_doc_ids: list[str],
                   docs: dict[str, dict]) -> list[dict]:
    """후보 집합 문서에 1부터 번호를 붙인다. 번호 순서는 pool_doc_ids(오름차순)다."""
    blocks = [prompt.document.format(n=i, text=docs[d]["context"],
                                     speakers=speaker_text(docs[d]["speakers"]),
                                     **{k: docs[d][k] for k in META})
              for i, d in enumerate(pool_doc_ids, 1)]
    user = prompt.user.format(query=query, documents="\n\n".join(blocks))
    return [{"role": "system", "content": prompt.system}, {"role": "user", "content": user}]


def to_doc_ids(elements: list[dict], pool_doc_ids: list[str]) -> list[dict]:
    """검사 출력의 문서 번호를 doc_id로 바꾼다. 범위 밖 번호는 None."""
    def doc(n):
        return pool_doc_ids[n - 1] if 1 <= n <= len(pool_doc_ids) else None
    return [{"fact": el["fact"], "support": [{"doc_id": doc(s["doc"]), "quote": s["quote"]}
                                             for s in el["support"]]} for el in elements]


def load_prompt(version: str):
    path = PROMPT_DIR / f"{version}.yaml"
    return OmegaConf.load(path), hashlib.sha256(path.read_bytes()).hexdigest()


def call(client, c, messages: list[dict]) -> tuple[str, dict]:
    resp = client.chat.completions.create(
        model=c.model, messages=messages, seed=c.seed, max_tokens=c.max_tokens,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "check", "strict": True, "schema": SCHEMA}},
        extra_body={"provider": {"order": [c.provider], "allow_fallbacks": False},
                    "reasoning": {"effort": c.reasoning_effort}, "usage": {"include": True}})
    return resp.choices[0].message.content, resp.usage.model_dump()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(records: list[dict]) -> None:
    by_type = Counter((r["type"], "pass" if r["verdict"]["passed"] else "fail") for r in records)
    reasons = Counter((r["type"], x) for r in records for x in r["verdict"]["reasons"])
    for t in sorted({r["type"] for r in records}):
        rs = {x: n for (tt, x), n in reasons.items() if tt == t}
        print(f"{t}: 통과 {by_type[(t, 'pass')]}, 불통과 {by_type[(t, 'fail')]} {rs}")
    usage = [r["usage"] for r in records if r.get("usage")]
    print(f"검사 호출 {len(usage)}건, 입력 토큰 {sum(u['prompt_tokens'] for u in usage):,}, "
          f"출력 토큰 {sum(u['completion_tokens'] for u in usage):,}, "
          f"비용 ${sum(u.get('cost') or 0 for u in usage):.4f}")


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config", overrides=[a for a in args if a != "--dry-run"])
    c, paths = cfg.multidoc.check, cfg.paths
    with (ROOT / paths.multidoc_pools).open(encoding="utf-8") as f:
        all_pools = [json.loads(line) for line in f]
    pools = select(all_pools, cfg.multidoc.gen.n_per_type)
    prompt, prompt_sha = load_prompt(c.prompt_version)
    gen_out, check_dir = ROOT / paths.multidoc_gen_out, ROOT / paths.multidoc_check
    # 원문은 이번 선택과 검사 기록이 있는 후보 집합 모두에 필요하다(기록 전체를 다시 판정)
    checked = {f.stem for f in check_dir.glob("*.json")}
    selected = {p["pool_id"] for p in pools}
    docs = load_docs(cfg, [p for p in all_pools if p["pool_id"] in selected | checked])
    contexts = {d: r["context"] for d, r in docs.items()}
    max_gold, match = cfg.multidoc.gen.max_gold, c.quote_match

    todo = [p for p in pools if not (check_dir / f"{p['pool_id']}.json").exists()]
    ready = [p for p in todo if (gen_out / f"{p['pool_id']}.json").exists()]
    if dry_run:
        chars = {p["pool_id"]: sum(len(m["content"]) for m in
                                   build_messages(prompt, "", p["doc_ids"], docs)) for p in todo}
        ready_ids = {p["pool_id"] for p in ready}
        print(f"검사 기록 없음 {len(todo)}개 중 생성 완료 {len(ready)}개. "
              f"호출 수 상한 {len(todo)}(생성 skip은 호출하지 않음)")
        print(f"입력 문자 수(질의 제외): 생성 완료분 {sum(chars[i] for i in ready_ids):,}, "
              f"전체 {sum(chars.values()):,}")
        return

    load_dotenv(ROOT / ".env")
    from openai import OpenAI
    client = OpenAI(base_url=c.base_url, api_key=os.environ[c.api_key_env])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    check_dir.mkdir(parents=True, exist_ok=True)
    for p in ready:
        gen = read_json(gen_out / f"{p['pool_id']}.json")
        rec = {"pool_id": p["pool_id"], "type": p["type"], "pool_doc_ids": p["doc_ids"],
               "gen": gen, "recipe": {
                   "commit": commit, "gen_prompt_version": gen.get("prompt_version"),
                   "gen_prompt_sha256": load_prompt(gen["prompt_version"])[1]
                   if gen.get("prompt_version") else None,
                   "check_prompt_version": c.prompt_version, "check_prompt_sha256": prompt_sha,
                   **OmegaConf.to_container(c, resolve=True)},
               "time": datetime.now().isoformat(timespec="seconds")}
        rec["recipe"].pop("api_key_env")
        if gen["status"] == "ok":
            content, rec["usage"] = call(client, c, build_messages(prompt, gen["query"],
                                                                   p["doc_ids"], docs))
            rec["response"] = content
            out = json.loads(content)
            elements = to_doc_ids(out["elements"], p["doc_ids"])
            rec["elements"] = elements
            rec["verdict"] = judge(gen, elements, out["answerable"], p["doc_ids"], contexts,
                                   max_gold, p["seed_doc_ids"], match=match)
        else:
            rec["verdict"] = judge(gen, None, False, p["doc_ids"], contexts, max_gold,
                                   match=match)
        (check_dir / f"{p['pool_id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(p["pool_id"], "통과" if rec["verdict"]["passed"] else rec["verdict"]["reasons"])

    # 판정 규칙이 바뀌면 검사 기록 전체를 저장된 응답으로 다시 판정한다(호출 없음).
    # n_per_type은 새로 호출할 대상만 고르고, queries.jsonl은 기록만으로 정해진다
    seeds = {p["pool_id"]: p["seed_doc_ids"] for p in all_pools}
    records = [read_json(f) for f in sorted(check_dir.glob("*.json"))]
    for r in records:
        if r["gen"]["status"] == "ok":
            verdict = judge(r["gen"], r["elements"], json.loads(r["response"])["answerable"],
                            r["pool_doc_ids"], contexts, max_gold, seeds[r["pool_id"]],
                            match=match)
            if verdict != r["verdict"]:
                r["verdict"] = verdict
                (check_dir / f"{r['pool_id']}.json").write_text(
                    json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    with (ROOT / paths.multidoc_queries).open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            if r["verdict"]["passed"]:
                g = r["gen"]
                f.write(json.dumps({
                    "qid": f"md-{r['pool_id']}", "pool_id": r["pool_id"], "type": r["type"],
                    "query": g["query"], "query_form": g.get("query_form", ""),
                    "gold_doc_ids": r["verdict"]["gold_doc_ids"],
                    "pool_doc_ids": r["pool_doc_ids"], "answer": g["answer"],
                    "elements": resolve(r["elements"], contexts, match)[0]},
                    ensure_ascii=False) + "\n")
    print(f"생성 대기 {len(todo) - len(ready)}개")
    summarize(records)


if __name__ == "__main__":
    main()
