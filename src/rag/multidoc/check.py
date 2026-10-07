"""multi-doc 생성 결과의 검사 입력을 만들고, 검사 에이전트 출력을 코드로 판정한다.

명세는 docs/slices/08-multidoc-queries.md, 08c-checker-agent.md. 검사 입력에는 질의와 후보 집합
전체 원문만 넣고 생성 쪽 시작 묶음·기대 답·근거는 넣지 않는다. 검사는 multidoc-checker
에이전트가 check_in 파일을 읽고 check_out에 쓴다. 진행 상태는 파일 존재로 정해져 중단 뒤
같은 명령으로 이어 간다.

    uv run python -m rag.multidoc.check [--prepare | --dry-run] [hydra override...]
"""

import hashlib
import json
import os
import re
import shutil
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


def wrap_lines(text: str, width: int) -> str:
    """width자를 넘는 줄을 문장 끝 뒤 공백에서 줄바꿈으로 나눈다. 검사 작업자가 한 번에 읽을 수
    있는 줄 길이를 넘는 문단 때문이다. 공백 하나를 줄바꿈으로 바꿀 뿐이라 공백을 줄인 인용 대조는
    같다."""
    out = []
    for line in text.split("\n"):
        cur = ""
        for sent in re.split(r"(?<=[.?!…]) ", line) if len(line) > width else [line]:
            if cur and len(cur) + 1 + len(sent) > width:
                out.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}" if cur else sent
        out.append(cur)
    return "\n".join(out)


def check_input(prompt, query: str, pool_doc_ids: list[str], docs: dict[str, dict],
                width: int) -> str:
    """검사 입력 파일 본문. 후보 집합 문서에 1부터 번호를 붙인다(pool_doc_ids 순서, 오름차순)."""
    blocks = [prompt.document.format(n=i, text=wrap_lines(docs[d]["context"], width),
                                     speakers=speaker_text(docs[d]["speakers"]),
                                     **{k: docs[d][k] for k in META})
              for i, d in enumerate(pool_doc_ids, 1)]
    user = prompt.user.format(query=query, documents="\n\n".join(blocks))
    return f"# 지시\n\n{prompt.system}\n\n# 입력\n\n{user}"


def valid_output(out) -> bool:
    """검사 출력이 {answerable, elements[{fact, support[{doc, quote}]}]} 형식인가."""
    return (isinstance(out, dict) and isinstance(out.get("answerable"), bool)
            and isinstance(out.get("elements"), list)
            and all(isinstance(el, dict) and isinstance(el.get("fact"), str)
                    and isinstance(el.get("support"), list)
                    and all(isinstance(x, dict) and type(x.get("doc")) is int
                            and isinstance(x.get("quote"), str) for x in el["support"])
                    for el in out["elements"]))


def read_output(path: Path) -> dict | None:
    """검사 출력 파일을 읽는다. 쓰다 만 파일이나 형식이 틀린 파일이면 None."""
    try:
        out = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return out if valid_output(out) else None


def rejects(path: Path) -> int:
    """검사 출력 path가 형식 오류로 rejected/에 옮겨진 횟수."""
    return len(list((path.parent / "rejected").glob(f"{path.stem}.*.json")))


def take_output(path: Path) -> dict | None:
    """검사 출력을 읽는다. 쓰다 만 출력이나 형식 오류면 같은 폴더의 rejected/{이름}.{n}.json으로
    옮겨 다시 검사 대기로 두고 None을 돌려준다(n은 그 후보 집합의 거부 순번)."""
    out = read_output(path)
    if out is None:
        (path.parent / "rejected").mkdir(exist_ok=True)
        shutil.move(path, path.parent / "rejected" / f"{path.stem}.{rejects(path) + 1}.json")
    return out


def to_doc_ids(elements: list[dict], pool_doc_ids: list[str]) -> list[dict]:
    """검사 출력의 문서 번호를 doc_id로 바꾼다. 범위 밖 번호는 None."""
    def doc(n):
        return pool_doc_ids[n - 1] if 1 <= n <= len(pool_doc_ids) else None
    return [{"fact": el["fact"], "support": [{"doc_id": doc(s["doc"]), "quote": s["quote"]}
                                             for s in el["support"]]} for el in elements]


def load_prompt(version: str):
    path = PROMPT_DIR / f"{version}.yaml"
    return OmegaConf.load(path), hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(records: list[dict]) -> None:
    by_type = Counter((r["type"], "pass" if r["verdict"]["passed"] else "fail") for r in records)
    reasons = Counter((r["type"], x) for r in records for x in r["verdict"]["reasons"])
    for t in sorted({r["type"] for r in records}):
        rs = {x: n for (tt, x), n in reasons.items() if tt == t}
        print(f"{t}: 통과 {by_type[(t, 'pass')]}, 불통과 {by_type[(t, 'fail')]} {rs}")
    jev = [x["usage"] for r in records for x in r.get("quote_checks", [])]
    print(f"Jev 판정 {len(jev)}건, 입력 토큰 {sum(u['input_tokens'] for u in jev):,}, "
          f"비용 ${sum(u.get('cost') or 0 for u in jev):.5f}")


def pool_state(pool_id: str, dirs: dict[str, Path], max_rejects: int) -> str:
    """후보 집합의 진행 단계를 파일 존재로 정한다.

    gen_wait, prepare, check_wait, judge_wait, held, done 중 하나. 생성 입력도 없으면 none.
    held는 검사 출력이 max_rejects번 거부돼 자동으로 다시 검사하지 않는 보류 상태다.
    """
    def has(k):
        return (dirs[k] / f"{pool_id}.json").exists()
    if has("check"):
        return "done"
    if not has("gen_out"):
        return "gen_wait" if has("gen_in") else "none"
    if (dirs["check_out"] / f"{pool_id}.json").exists():
        return "judge_wait"
    gen = read_json(dirs["gen_out"] / f"{pool_id}.json")
    if gen["status"] != "ok":
        return "judge_wait"  # 생성 skip은 검사 없이 기록한다
    if not (dirs["check_in"] / f"{pool_id}.md").exists():
        return "prepare"
    return "held" if rejects(dirs["check_out"] / f"{pool_id}.json") >= max_rejects else "check_wait"


def main() -> None:
    args = sys.argv[1:]
    dry_run, prepare = "--dry-run" in args, "--prepare" in args
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config",
                      overrides=[a for a in args if a not in ("--dry-run", "--prepare")])
    c, paths = cfg.multidoc.check, cfg.paths
    with (ROOT / paths.multidoc_pools).open(encoding="utf-8") as f:
        all_pools = [json.loads(line) for line in f]
    pools = select(all_pools, cfg.multidoc.gen.n_per_type)
    prompt, prompt_sha = load_prompt(c.prompt_version)
    dirs = {"gen_in": ROOT / paths.multidoc_gen_in, "gen_out": ROOT / paths.multidoc_gen_out,
            "check_in": ROOT / paths.multidoc_check_in,
            "check_out": ROOT / paths.multidoc_check_out, "check": ROOT / paths.multidoc_check}
    check_dir = dirs["check"]
    state = {p["pool_id"]: pool_state(p["pool_id"], dirs, c.max_rejects) for p in pools}
    # 원문은 이번 선택과 검사 기록이 있는 후보 집합 모두에 필요하다(기록 전체를 다시 판정)
    checked = {f.stem for f in check_dir.glob("*.json")}
    docs = load_docs(cfg, [p for p in all_pools if p["pool_id"] in set(state) | checked])
    contexts = {d: r["context"] for d, r in docs.items()}
    max_gold, s = cfg.multidoc.gen.max_gold, c.quote_semantic
    seeds = {p["pool_id"]: p["seed_doc_ids"] for p in all_pools}
    counts = Counter(state.values())

    if dry_run:
        print(f"선택 {len(pools)}개: 생성 대기 {counts['gen_wait']}, "
              f"검사 준비 {counts['prepare']}, "
              f"검사 대기 {counts['check_wait']}, 판정 대기 {counts['judge_wait']}, "
              f"보류 {counts['held']}, 완료 {counts['done']}, 생성 입력 없음 {counts['none']}")
        if counts["held"]:  # 검사 작업에 넣지 않고 사용자에게 보고한다
            print("보류:", ", ".join(k for k, v in state.items() if v == "held"))
        records = [read_json(f) for f in sorted(check_dir.glob("*.json"))]
        n_jev = sum(fill_quote_checks(r, contexts, s, lambda q, ps: {"p": None, "usage": None})
                    for r in records if r["gen"]["status"] == "ok")
        print(f"Jev 호출: 기존 검사 기록 {n_jev}건(판정 대기분은 검사 출력의 인용에 따라 정해진다)")
        return

    if prepare:
        dirs["check_in"].mkdir(parents=True, exist_ok=True)
        todo = [p for p in pools if state[p["pool_id"]] == "prepare"]
        for p in todo:
            gen = read_json(dirs["gen_out"] / f"{p['pool_id']}.json")
            (dirs["check_in"] / f"{p['pool_id']}.md").write_text(
                check_input(prompt, gen["query"], p["doc_ids"], docs, c.max_line_chars),
                encoding="utf-8",
                newline="\n")
        print(f"검사 입력 {len(todo)}개를 썼다 → {dirs['check_in']}. "
              f"검사 대기 {counts['check_wait'] + len(todo)}개")
        return

    load_dotenv(ROOT / ".env")
    quote_prompt = load_prompt(s.prompt_version)[0]

    def ask(quote, passages):
        return ask_jev(s, quote_prompt, os.environ[c.api_key_env], quote, passages)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    check_dir.mkdir(parents=True, exist_ok=True)

    def save(r):
        (check_dir / f"{r['pool_id']}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    rejected = 0
    for p in pools:
        if state[p["pool_id"]] != "judge_wait":
            continue
        gen = read_json(dirs["gen_out"] / f"{p['pool_id']}.json")
        rec = {"pool_id": p["pool_id"], "type": p["type"], "pool_doc_ids": p["doc_ids"],
               "gen": gen, "recipe": {
                   "commit": commit, "gen_prompt_version": gen.get("prompt_version"),
                   "gen_prompt_sha256": load_prompt(gen["prompt_version"])[1]
                   if gen.get("prompt_version") else None, "checker": "multidoc-checker",
                   "check_prompt_version": c.prompt_version, "check_prompt_sha256": prompt_sha},
               "time": datetime.now().isoformat(timespec="seconds")}
        if gen["status"] == "ok":
            path = dirs["check_out"] / f"{p['pool_id']}.json"
            out = take_output(path)
            if out is None:
                rejected += 1
                continue
            rec["response"] = json.dumps(out, ensure_ascii=False)
            rec["elements"] = to_doc_ids(out["elements"], p["doc_ids"])
            save(rec)  # Jev 판정 전에 남겨, Jev가 실패해도 다음 실행 재판정에서 이어 간다
            fill_quote_checks(rec, contexts, s, ask)
            rec["verdict"] = judge(gen, rec["elements"], out["answerable"], p["doc_ids"],
                                   contexts, max_gold, p["seed_doc_ids"],
                                   probs=quote_probs(rec, s), min_prob=s.min_prob)
        else:
            rec["verdict"] = judge(gen, None, False, p["doc_ids"], contexts, max_gold,
                                   probs={}, min_prob=s.min_prob)
        save(rec)
        print(p["pool_id"], "통과" if rec["verdict"]["passed"] else rec["verdict"]["reasons"])
    if rejected:
        print(f"형식이 틀린 검사 출력 {rejected}개를 {dirs['check_out'] / 'rejected'}로 옮겼다"
              f"(거부 {c.max_rejects}회 미만은 검사 대기, 닿으면 보류)")

    # 판정 규칙이 바뀌면 검사 기록 전체를 저장된 응답으로 다시 판정한다. Jev는 아직 판정하지 않은
    # 인용만 부르고 확률을 기록에 남긴다. n_per_type은 새로 처리할 대상만 고르고, queries.jsonl은
    # 기록만으로 정해진다
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
    left = Counter(pool_state(p["pool_id"], dirs, c.max_rejects) for p in pools)
    print(f"남은 작업: 생성 대기 {left['gen_wait']}, 검사 준비 {left['prepare']}, "
          f"검사 대기 {left['check_wait']}, 보류 {left['held']}")
    summarize(records)


if __name__ == "__main__":
    main()
