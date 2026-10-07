"""multi-doc 생성 결과를 다른 모델(OpenRouter)로 검사하고 코드로 판정한다.

명세는 docs/slices/08-multidoc-queries.md. 검사 호출에는 질의와 후보 집합 전체 원문만 보내고,
생성 쪽 시작 묶음·기대 답·근거는 보내지 않는다. 검사 기록이 이미 있는 후보 집합은 건너뛴다(재사용).

    uv run python -m rag.multidoc.check [--dry-run] [hydra override...]
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
from rapidfuzz import fuzz, process

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


def found(quote: str, context: str, p: float | None, min_prob: float) -> bool:
    """인용과 같은 의미가 원문에 있는가(지어낸 인용이 아닌가).

    공백을 한 칸으로 줄여 원문에 그대로 있으면 있다. 그대로 없으면 Jev가 판정한 같은 의미일 확률 p가
    min_prob 이상일 때 있다고 본다. p가 없으면(판정 전) 없다고 본다(D-14).
    """
    q = norm(quote)
    return bool(q) and (q in norm(context) or (p is not None and p >= min_prob))


def candidates(quote: str, context: str, top_k: int, window_sentences: int) -> list[str]:
    """원문을 문장 끝 부호로 나눠 window_sentences문장씩 묶은 대목(한 문장씩 민다) 중 인용과
    partial_ratio가 높은 top_k개. 문자 유사도는 Jev에 보낼 후보를 고르는 데만 쓴다."""
    sents = re.split(r"(?<=[.?!…])\s+", norm(context))
    windows = [" ".join(sents[i:i + window_sentences])
               for i in range(max(1, len(sents) - window_sentences + 1))]
    return [w for w, _, _ in process.extract(norm(quote), windows, scorer=fuzz.partial_ratio,
                                              limit=top_k)]


def all_quotes(rec: dict) -> list[tuple[str, str]]:
    """검사 기록의 생성 쪽 evidence와 검사 쪽 support 인용 (doc_id, 공백을 줄인 인용)."""
    pairs = [(e["doc_id"], e["quote"]) for e in rec["gen"].get("evidence") or []]
    pairs += [(s["doc_id"], s["quote"]) for el in rec.get("elements") or [] for s in el["support"]]
    return [(d, norm(q)) for d, q in pairs if d and norm(q)]


def quote_probs(rec: dict, s) -> dict[tuple[str, str], float]:
    """저장된 Jev 판정 중 지금 설정(s.model, s.prompt_version)과 같은 것만. 모델이나 질문을 바꾸면
    다시 묻는다."""
    return {(x["doc_id"], x["quote"]): x["p"] for x in rec.get("quote_checks", [])
            if x["model"] == s.model and x["prompt_version"] == s.prompt_version}


def fill_quote_checks(rec: dict, contexts: dict[str, str], s, ask) -> int:
    """원문에 그대로 없고 아직 판정하지 않은 인용을 ask(인용, 후보 대목)로 판정해
    rec["quote_checks"]에 더한다. 더한 수를 반환한다. ask는 {"p", "usage"}를 돌려준다."""
    probs = quote_probs(rec, s)
    todo = {(d, q) for d, q in all_quotes(rec)
            if d in contexts and q not in norm(contexts[d]) and (d, q) not in probs}
    for d, q in sorted(todo):
        passages = candidates(q, contexts[d], s.top_k, s.window_sentences)
        out = ask(q, passages)
        rec.setdefault("quote_checks", []).append({
            "doc_id": d, "quote": q, "passages": passages, "p": out["p"], "usage": out["usage"],
            "model": s.model, "prompt_version": s.prompt_version})
    return len(todo)


def ask_jev(s, prompt, api_key: str, quote: str, passages: list[str]) -> dict:
    """Jev Decisions API에 noul 질문 하나를 보내 같은 의미일 확률을 받는다."""
    body = {"model": s.model, "state": {"인용": quote, "후보 대목": passages},
            "questions": {"q": {"type": "noul", "instructions": prompt.instructions,
                                "criteria": OmegaConf.to_container(prompt.criteria)}}}
    req = urllib.request.Request(s.url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=s.timeout) as r:
        resp = json.loads(r.read().decode())
    return {"p": resp["answers"]["q"]["noul"], "usage": resp["usage"]}


def resolve(elements: list[dict], contexts: dict[str, str], probs: dict[tuple[str, str], float],
            min_prob: float) -> tuple[list[dict], list[dict]]:
    """검사 쪽 support의 인용과 같은 의미가 원문에 있는지 본다.

    (원문에 있는 support만 남긴 요소, 없는 것도 남긴 요소)를 반환한다. 인용은 바꾸지 않는다. 앞쪽은
    support가 모두 빠진 요소를 뺀다. 문서 번호가 범위 밖인 support는 둘 다에서 뺀다.
    """
    matched, kept = [], []
    for el in elements:
        sup = [s for s in el["support"] if s["doc_id"] in contexts]
        ok = [s for s in sup if found(s["quote"], contexts[s["doc_id"]],
                                      probs.get((s["doc_id"], norm(s["quote"]))), min_prob)]
        if ok:
            matched.append({**el, "support": ok})
        if sup:
            kept.append({**el, "support": sup})
    return matched, kept


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
          probs: dict[tuple[str, str], float], min_prob: float) -> dict:
    """생성·검사 결과로 통과 여부를 정한다.

    생성 쪽 정답 문서는 2개 이상 max_gold개 이하이고, S7 시작 묶음(pool_seed)을 모두 포함해야 한다.
    elements의 support는 {"doc_id", "quote"} 목록이다(번호를 doc_id로 바꾼 뒤). 번호가 범위 밖이면
    doc_id는 None이다. 인용은 found로 원문에 있는지 본다(probs, min_prob). 생성 쪽 인용이 없으면
    quote_missing이다. 검사 쪽 인용이 원문에 없는 support는 확인할 수 없는 근거라, 빼고 판정한
    결과와 두고 판정한 결과가 다르면 quote_dependent로 불통과한다(D-14). 사유를 모두 모으고,
    사유가 없으면 통과다. 정답 문서는 원문에 있는 support로 정한다.
    """
    if gen["status"] != "ok":
        return {"passed": False, "reasons": ["gen_skip"], "gold_doc_ids": [],
                "dropped_quotes": 0}
    reasons = []
    seed = gen["seed_doc_ids"]
    if not (2 <= len(seed) <= max_gold and len(set(seed)) == len(seed)
            and set(pool_seed) <= set(seed) <= set(pool_doc_ids)
            and {e["doc_id"] for e in gen["evidence"]} == set(seed)):
        reasons.append("gen_invalid")

    if not all(e["doc_id"] in contexts
               and found(e["quote"], contexts[e["doc_id"]],
                         probs.get((e["doc_id"], norm(e["quote"]))), min_prob)
               for e in gen["evidence"]):
        reasons.append("quote_missing")
    if not answerable:
        reasons.append("unanswerable")
    matched, kept = resolve(elements, contexts, probs, min_prob)
    gold, rules = gold_reasons(matched, seed)
    reasons += rules
    if bool(rules) != bool(gold_reasons(kept, seed)[1]):
        reasons.append("quote_dependent")
    n_support = sum(len(el["support"]) for el in elements)
    n_matched = sum(len(el["support"]) for el in matched)
    return {"passed": not reasons, "reasons": reasons, "gold_doc_ids": gold,
            "dropped_quotes": n_support - n_matched}


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
    jev = [x["usage"] for r in records for x in r.get("quote_checks", [])]
    print(f"Jev 판정 {len(jev)}건, 입력 토큰 {sum(u['input_tokens'] for u in jev):,}, "
          f"비용 ${sum(u.get('cost') or 0 for u in jev):.5f}")


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
    max_gold, s = cfg.multidoc.gen.max_gold, c.quote_semantic
    seeds = {p["pool_id"]: p["seed_doc_ids"] for p in all_pools}

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
        records = [read_json(f) for f in sorted(check_dir.glob("*.json"))]
        n_jev = sum(fill_quote_checks(r, contexts, s, lambda q, ps: {"p": None, "usage": None})
                    for r in records if r["gen"]["status"] == "ok")
        print(f"Jev 호출: 기존 검사 기록 {n_jev}건(새 검사분은 검사 응답의 인용에 따라 정해진다)")
        return

    load_dotenv(ROOT / ".env")
    from openai import OpenAI
    client = OpenAI(base_url=c.base_url, api_key=os.environ[c.api_key_env])
    quote_prompt = load_prompt(s.prompt_version)[0]

    def ask(quote, passages):
        return ask_jev(s, quote_prompt, os.environ[c.api_key_env], quote, passages)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    check_dir.mkdir(parents=True, exist_ok=True)

    def save(r):
        (check_dir / f"{r['pool_id']}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

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
            # 비용을 낸 검사 응답을 Jev 판정 전에 먼저 남긴다. Jev가 실패하면 다음 실행의
            # 재판정에서 남은 인용만 묻는다
            save(rec)
            fill_quote_checks(rec, contexts, s, ask)
            rec["verdict"] = judge(gen, elements, out["answerable"], p["doc_ids"], contexts,
                                   max_gold, p["seed_doc_ids"], probs=quote_probs(rec, s),
                                   min_prob=s.min_prob)
        else:
            rec["verdict"] = judge(gen, None, False, p["doc_ids"], contexts, max_gold,
                                   probs={}, min_prob=s.min_prob)
        save(rec)
        print(p["pool_id"], "통과" if rec["verdict"]["passed"] else rec["verdict"]["reasons"])

    # 판정 규칙이 바뀌면 검사 기록 전체를 저장된 응답으로 다시 판정한다(검사 호출 없음). Jev는
    # 아직 판정하지 않은 인용만 부르고 확률을 기록에 남긴다. n_per_type은 새로 호출할 대상만 고르고,
    # queries.jsonl은 기록만으로 정해진다
    records = [read_json(f) for f in sorted(check_dir.glob("*.json"))]
    for r in records:
        if r["gen"]["status"] == "ok":
            added = fill_quote_checks(r, contexts, s, ask)
            verdict = judge(r["gen"], r["elements"], json.loads(r["response"])["answerable"],
                            r["pool_doc_ids"], contexts, max_gold, seeds[r["pool_id"]],
                            probs=quote_probs(r, s), min_prob=s.min_prob)
            if added or verdict != r.get("verdict"):
                r["verdict"] = verdict
                save(r)
    with (ROOT / paths.multidoc_queries).open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            if r["verdict"]["passed"]:
                g = r["gen"]
                f.write(json.dumps({
                    "qid": f"md-{r['pool_id']}", "pool_id": r["pool_id"], "type": r["type"],
                    "query": g["query"], "query_form": g.get("query_form", ""),
                    "gold_doc_ids": r["verdict"]["gold_doc_ids"],
                    "pool_doc_ids": r["pool_doc_ids"], "answer": g["answer"],
                    "elements": resolve(r["elements"], contexts, quote_probs(r, s),
                                        s.min_prob)[0]},
                    ensure_ascii=False) + "\n")
    print(f"생성 대기 {len(todo) - len(ready)}개")
    summarize(records)


if __name__ == "__main__":
    main()
