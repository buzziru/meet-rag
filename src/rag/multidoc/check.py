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


def judge(gen: dict, elements: list[dict] | None, answerable: bool,
          pool_doc_ids: list[str], contexts: dict[str, str]) -> dict:
    """생성·검사 결과로 통과 여부를 정한다.

    elements의 support는 {"doc_id", "quote"} 목록이다(번호를 doc_id로 바꾼 뒤). 번호가 범위 밖이면
    doc_id는 None이다. 사유를 모두 모으고, 사유가 없으면 통과다.
    """
    if gen["status"] != "ok":
        return {"passed": False, "reasons": ["gen_skip"], "gold_doc_ids": []}
    reasons = []
    seed = gen["seed_doc_ids"]
    if not (2 <= len(seed) <= 3 and len(set(seed)) == len(seed) and set(seed) <= set(pool_doc_ids)
            and {e["doc_id"] for e in gen["evidence"]} == set(seed)):
        reasons.append("gen_invalid")

    quotes = [(e["doc_id"], e["quote"]) for e in gen["evidence"]]
    quotes += [(s["doc_id"], s["quote"]) for el in elements for s in el["support"]]
    if not all(d in contexts and quoted(q, contexts[d]) for d, q in quotes):
        reasons.append("quote_missing")
    if not answerable:
        reasons.append("unanswerable")

    supports = [{s["doc_id"] for s in el["support"] if s["doc_id"] is not None} for el in elements]
    gold = sorted(set().union(*supports)) if supports else []
    if len(gold) < 2:
        reasons.append("single_doc")
    unique = {next(iter(s)) for s in supports if len(s) == 1}
    if set(gold) - unique:
        reasons.append("substitutable")
    if set(gold) != set(seed):
        reasons.append("seed_mismatch")
    return {"passed": not reasons, "reasons": reasons, "gold_doc_ids": gold}


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
        pools = select([json.loads(line) for line in f], cfg.multidoc.gen.n_per_type)
    docs = load_docs(cfg, pools)
    contexts = {d: r["context"] for d, r in docs.items()}
    prompt, prompt_sha = load_prompt(c.prompt_version)
    gen_out, check_dir = ROOT / paths.multidoc_gen_out, ROOT / paths.multidoc_check

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
            rec["verdict"] = judge(gen, elements, out["answerable"], p["doc_ids"], contexts)
        else:
            rec["verdict"] = judge(gen, None, False, p["doc_ids"], contexts)
        (check_dir / f"{p['pool_id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(p["pool_id"], "통과" if rec["verdict"]["passed"] else rec["verdict"]["reasons"])

    records = [read_json(f) for f in sorted(check_dir.glob("*.json"))]
    with (ROOT / paths.multidoc_queries).open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            if r["verdict"]["passed"]:
                g = r["gen"]
                f.write(json.dumps({
                    "qid": f"md-{r['pool_id']}", "pool_id": r["pool_id"], "type": r["type"],
                    "query": g["query"], "gold_doc_ids": r["verdict"]["gold_doc_ids"],
                    "pool_doc_ids": r["pool_doc_ids"], "answer": g["answer"],
                    "elements": r["elements"]}, ensure_ascii=False) + "\n")
    print(f"생성 대기 {len(todo) - len(ready)}개")
    summarize(records)


if __name__ == "__main__":
    main()
