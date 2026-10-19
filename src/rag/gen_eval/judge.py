"""생성 기록(paths.gen_runs)을 코드 판정과 LLM judge로 채점해 paths.gen_judge에 쓴다(S14).

- 코드 판정: 거부 문구, 인용 번호, 회의 일자·위원회 이름, 정답 문서 포함
- judge(D-38): 충실성(진술 추출 → 진술별 근거 판정), 답변 관련성(3단계),
  핵심 답변 포함도(핵심 진술 추출 → 답변 포함 판정), 정답 문서 근거 청크의 핵심 답(같은
  핵심 진술 → 청크 포함 판정, D-40). 거부 답변은 근거 청크 판정만 한다
judge 응답은 요청 본문 해시로 paths.gen_judge_cache에 저장해 다시 실행할 때 쓴다
(같은 입력이면 API를 부르지 않는다). 명세는 docs/slices/14-gen-eval.md.
인자는 Hydra override(예: +exp=exp017 gen_eval.n=20).
"""

import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from langsmith import traceable
from langsmith.run_trees import get_cached_client
from langsmith.wrappers import wrap_openai
from omegaconf import OmegaConf
from openai import OpenAI

from rag.conditions import committee_base
from rag.gen_eval.checks import (
    citation_check,
    gold_position,
    is_refusal,
    metadata_mismatches,
)
from rag.gen_eval.common import eval_qids, load_refs, read_jsonl
from rag.index import ROOT, load_cfg
from rag.search import write_guarded

RELEVANCE = {"답함": 1.0, "일부": 0.5, "답하지 않음": 0.0}


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def render(template: str, **values: str) -> str:
    """자리표시자 {name}만 바꾼다. 지시문의 JSON 예시 중괄호는 그대로 둔다."""
    for k, v in values.items():
        template = template.replace("{" + k + "}", v)
    return template


def parse_json(text: str | None) -> dict | None:
    """응답의 JSON 객체. 코드 울타리(```json)는 벗긴다. 형식이 틀리면 None(다시 묻지 않는다)."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        out = json.loads(s)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def format_contexts(contexts: list[dict]) -> str:
    return "\n\n".join(f"[{c['n']}] {c['date']} {c['committee_name']} {c['meeting_number']} "
                       f"{c['session_number']}\n{c['text']}" for c in contexts)


def judge_recipe(cfg, gen_recipe: dict) -> dict:
    j = cfg.judge
    prompt = OmegaConf.to_container(j.prompt, resolve=True)
    return {"name": j.name, "model": j.model, "base_url": j.base_url,
            "params": OmegaConf.to_container(j.params),
            "extra_body": OmegaConf.to_container(j.extra_body) if j.extra_body else None,
            "prompt_version": prompt["version"], "prompt_sha256": sha(prompt),
            "gen_recipe_sha256": sha(gen_recipe)}


class Judge:
    """judge 호출 하나를 맡는다. 같은 요청 본문은 저장된 응답을 쓴다."""

    def __init__(self, cfg, session: str):
        j = cfg.judge
        self.j, self.prompt = j, j.prompt
        self.client = wrap_openai(OpenAI(
            base_url=j.base_url, api_key=os.environ[j.api_key_env], timeout=j.timeout,
            default_headers={"User-Agent": j.user_agent, "x-opencode-session": session}))
        self.params = OmegaConf.to_container(j.params)
        self.extra = OmegaConf.to_container(j.extra_body) if j.extra_body else None
        self.cache = ROOT / cfg.paths.gen_judge_cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.calls = self.hits = 0

    def ask(self, step: str, **values: str) -> tuple[dict | None, dict | None]:
        """(파싱한 JSON 또는 None, usage). step은 지시 파일의 항목 이름."""
        p = self.prompt[step]
        messages = [{"role": "system", "content": p.system},
                    {"role": "user", "content": render(p.user, **values)}]
        body = {"model": self.j.model, "messages": messages, **self.params, "extra": self.extra}
        path = self.cache / f"{sha(body)}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            with self.lock:
                self.hits += 1
        else:
            r = self.client.chat.completions.create(
                model=self.j.model, messages=messages, extra_body=self.extra, **self.params)
            saved = {"content": r.choices[0].message.content,
                     "usage": r.usage.model_dump() if r.usage else None}
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            with self.lock:
                self.calls += 1
        return parse_json(saved["content"]), saved["usage"]


def faithfulness(judge: Judge, question: str, answer: str, contexts: list[dict]) -> dict:
    """RAGAS 충실성: 뒷받침된 진술 수 / 전체 진술 수."""
    st, u1 = judge.ask("statements", question=question, answer=answer)
    statements = st.get("statements") if st else None
    if not isinstance(statements, list):
        return {"score": None, "error": "statements 형식 오류", "usage": [u1]}
    if not statements:
        return {"score": None, "error": "진술 없음", "usage": [u1]}
    vd, u2 = judge.ask("verdicts", contexts=format_contexts(contexts),
                       statements=json.dumps(statements, ensure_ascii=False))
    verdicts = vd.get("verdicts") if vd else None
    if not isinstance(verdicts, list) or len(verdicts) != len(statements):
        return {"score": None, "error": "verdicts 형식 오류", "statements": statements,
                "usage": [u1, u2]}
    ok = [v.get("verdict") in (0, 1) for v in verdicts]
    if not all(ok):
        return {"score": None, "error": "verdict 값 오류", "usage": [u1, u2]}
    return {"score": sum(v["verdict"] for v in verdicts) / len(verdicts), "verdicts": verdicts,
            "usage": [u1, u2]}


def relevance(judge: Judge, question: str, answer: str) -> dict:
    out, u = judge.ask("relevance", question=question, answer=answer)
    label = out.get("label") if out else None
    if label not in RELEVANCE:
        return {"score": None, "error": "label 형식 오류", "usage": [u]}
    return {"score": RELEVANCE[label], "label": label, "reason": out.get("reason"), "usage": [u]}


def key_statements(judge: Judge, question: str, reference: str) -> dict:
    """answer.comment에서 질의에 답하는 핵심 진술. 답변과 무관해 질의마다 한 번 부르고, 핵심 답변
    포함도와 근거 청크 판정이 같은 진술을 쓴다. 빈 목록이면 참조 사용 불가다."""
    out, u = judge.ask("key_statements", question=question, reference=reference)
    keys = out.get("key_statements") if out else None
    if not isinstance(keys, list):
        return {"keys": None, "error": "key_statements 형식 오류", "usage": [u]}
    return {"keys": keys, "usage": [u]}


def key_presence(judge: Judge, step: str, keys: list[str], **text: str) -> dict:
    """핵심 진술마다 대상 글(답변 또는 근거 청크)에 들어 있는지 판정하고 들어 있는 비율을 낸다."""
    out, u = judge.ask(step, key_statements=json.dumps(keys, ensure_ascii=False), **text)
    checks = out.get("checks") if out else None
    if (not isinstance(checks, list) or len(checks) != len(keys)
            or not all(c.get("present") in (0, 1) for c in checks)):
        return {"score": None, "error": f"{step} 형식 오류", "usage": [u]}
    return {"score": sum(c["present"] for c in checks) / len(checks), "checks": checks,
            "usage": [u]}


def inclusion(judge: Judge, answer: str, ks: dict | None) -> dict:
    """핵심 답변 포함도: 핵심 진술 중 답변에 담긴 비율. ks가 None이면 정답 문서가 근거에 없다."""
    if ks is None:
        return {"score": None, "excluded": "gold_missing"}
    if ks["keys"] is None:
        return {"score": None, "error": ks["error"]}
    if not ks["keys"]:
        return {"score": None, "excluded": "reference_unusable"}
    return {**key_presence(judge, "key_checks", ks["keys"], answer=answer),
            "key_statements": ks["keys"]}


@traceable(name="judge_record", process_inputs=lambda i: {"qid": i["gen"]["qid"]})
def judge_record(judge: Judge, gen: dict, ref: dict, cfg, committees: set[str]) -> dict:
    """생성 기록 하나의 코드 판정과 judge 채점.

    정답 문서가 근거에 있으면 거부 여부와 관계없이 핵심 진술을 뽑고, 그 진술이 정답 문서의 근거
    청크에 들어 있는 비율이 gen_eval.chunk_key_min 이상이면 청크에 답이 있다고 본다(S14 결정 5).
    핵심 진술이 없거나 형식 오류면 answer_in_chunk는 None(판단 불가)이다."""
    g = cfg.gen_eval
    answer, contexts = gen["answer"], gen["contexts"]
    gold_n = gold_position(contexts, ref["doc_id"])
    out = {"qid": gen["qid"], "refusal": is_refusal(answer, g.refusal), "gold_n": gold_n,
           "answer_in_chunk": None, "usage": gen["usage"], "provider": gen["provider"],
           "first_token_s": gen["first_token_s"], "total_s": gen["total_s"]}
    ks = key_statements(judge, gen["query"], ref["answer_comment"]) if gold_n else None
    if ks is not None:
        out["key_statements"] = ks
        if ks["keys"]:
            chunk = key_presence(judge, "chunk_checks", ks["keys"],
                                 excerpt=contexts[gold_n - 1]["text"])
            out["chunk_keys"] = chunk
            if chunk["score"] is not None:
                out["answer_in_chunk"] = chunk["score"] >= g.chunk_key_min
    if out["refusal"]:  # 거부 답변은 거부 교차 집계로만 본다(초안 "거부 답변의 처리")
        return out
    out["citations"] = citation_check(answer, len(contexts))
    out["metadata"] = metadata_mismatches(answer, contexts, committees)
    out["faithfulness"] = faithfulness(judge, gen["query"], answer, contexts)
    out["relevance"] = relevance(judge, gen["query"], answer)
    out["inclusion"] = inclusion(judge, answer, ks)
    return out


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    qids = [q for q in eval_qids(cfg) if q in gens]  # 표본 순서. 아직 생성하지 않은 qid는 뺀다
    refs = load_refs(cfg, qids)
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        committees = {committee_base(json.loads(line)["committee_name"]) for line in f} - {""}
    recipes = {sha(gens[q]["recipe"]) for q in qids}
    if len(recipes) != 1:
        raise SystemExit("생성 기록의 레시피가 여럿이다")
    rec = judge_recipe(cfg, gens[qids[0]]["recipe"])
    judge = Judge(cfg, session=f"meet-rag-judge-{sha(rec)[:16]}")

    def one(qid):
        return judge_record(judge, gens[qid], refs[qid], cfg, committees,
                            langsmith_extra={"metadata": {"qid": qid, **rec}})

    with ThreadPoolExecutor(cfg.judge.concurrency) as ex:
        rows = list(ex.map(one, qids))
    get_cached_client().flush()
    text = "".join(json.dumps({**r, "judge_recipe": rec}, ensure_ascii=False) + "\n" for r in rows)
    state = write_guarded(ROOT / cfg.paths.gen_judge, text, cfg.search.overwrite)
    print(f"{len(rows)}개 채점, API 호출 {judge.calls}회, 저장된 응답 {judge.hits}회 "
          f"-> {cfg.paths.gen_judge} ({state})")


if __name__ == "__main__":
    main()
