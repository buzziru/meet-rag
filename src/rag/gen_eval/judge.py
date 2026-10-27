"""생성 기록(paths.gen_runs)을 코드 판정과 LLM judge로 채점해 paths.gen_judge에 쓴다(S14).

- 코드 판정: 거부 문구, 인용 번호, 회의 일자·위원회 이름, 정답 문서 포함
- judge(D-38): 충실성(진술 추출 → 진술별 근거 판정), 답변 관련성(3단계),
  핵심 답변 포함도(핵심 진술 추출 → 답변 포함 판정), 정답 문서 근거 청크의 핵심 답(같은
  핵심 진술 → 청크 포함 판정, D-40). 전체 거부 답변은 근거 청크 판정만 하고, 부분 거부 답변은
  충실성·인용 검사만 거부 문장을 뺀 내용으로 채점한다(S14b, D-41, D-47 결정 4)
- 질의 항목 단위 거부 평가(gen_eval.item_eval): 질의를 항목으로 나눠 항목마다 근거의 정보 상태와
  답변의 처리를 판정하고, 맞는 처리인지는 코드가 정한다(S14c, D-41 결정 2~4). 모든 답변에 한다.
  gen_eval.item_cases를 주면 생성 기록 대신 판정 확인 사례를 이 평가로만 채점한다
judge 응답은 요청 본문 해시로 paths.gen_judge_cache에 저장해 다시 실행할 때 쓴다
(같은 입력이면 API를 부르지 않는다). 명세는 docs/slices/14-gen-eval.md.
인자는 Hydra override(기본은 판정용 세트 dev-full 330질의, D-50. 예: +exp=exp017 judge.rep=1,
S14 표본은 gen_eval.queries=dev-small gen_eval.n=20).
"""

import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait

from langsmith import traceable
from langsmith.run_trees import get_cached_client
from langsmith.wrappers import wrap_openai
from omegaconf import OmegaConf
from openai import DefaultHttpxClient, OpenAI

from rag.conditions import DATE, DOC_DATE, committee_base
from rag.gen_eval.checks import (
    HANDLINGS,
    STATES,
    citation_check,
    gold_position,
    item_counts,
    item_outcome,
    metadata_mismatches,
    refusal_split,
)
from rag.gen_eval.common import eval_qids, load_refs, read_jsonl, stable
from rag.index import ROOT, git_state, load_cfg, refuse_existing, write_guarded

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


def check_prompt(cfg, gen_recipe: dict) -> None:
    """생성 기록을 만든 프롬프트가 지금 cfg.prompt와 같은지 본다. 거부 문구(cfg.prompt.refusal)를
    이 프롬프트에서 읽으므로, 버전 이름이 같아도 내용이 다르면 멈춘다(S16)."""
    if gen_recipe["prompt_sha256"] != sha(OmegaConf.to_container(cfg.prompt, resolve=True)):
        raise SystemExit(f"생성 기록의 프롬프트({gen_recipe['prompt_version']})가 지금 prompt "
                         "설정과 다르다. 생성에 쓴 프롬프트 파일로 채점한다")


def judge_recipe(cfg, gen_recipes: list[dict]) -> dict:
    """judge 설정, 코드 판정 설정(gen_eval, 프롬프트의 거부 문구), judge 실행 커밋, 생성 기록의
    커밋 목록(S15).

    생성 레시피는 커밋을 빼고(stable) 비교하므로, 커밋이 다른 생성 기록이 섞였는지는
    gen_commits를 보고 판단한다(S15 결정 사항 2). 일자 판정은 검색의 조건 정규식을 같이 쓰므로
    그 패턴을 남긴다. 검색 쪽에서 바꾸면 이전 judge 결과와 레시피가 달라진다(S16)."""
    j, g = cfg.judge, cfg.gen_eval
    prompt = OmegaConf.to_container(j.prompt, resolve=True)
    rec = {"name": j.name, "model": j.model, "base_url": j.base_url,
            "params": OmegaConf.to_container(j.params),
            "extra_body": OmegaConf.to_container(j.extra_body) if j.extra_body else None,
            "step_params": OmegaConf.to_container(j.step_params) if j.get("step_params") else None,
            "prompt_version": prompt["version"], "prompt_sha256": sha(prompt),
            "refusal": cfg.prompt.refusal, "filler_phrases": list(g.filler_phrases),
            "check_patterns": {"date": DATE.pattern, "doc_date": DOC_DATE.pattern},
            "chunk_key_min": g.chunk_key_min, "item_eval": g.item_eval,
            "rep": j.rep, "git_commit": git_state()[0]}
    if gen_recipes:  # 판정 확인 사례(합성 답변)에는 생성 기록이 없다(S14c)
        rec |= {"gen_commits": sorted({r["git_commit"] for r in gen_recipes}),
                "gen_recipe_sha256": sha(stable(gen_recipes[0]))}
    return rec


class HttpCounts:
    """HTTP 요청 수와 응답 상태 코드별 수. OpenAI SDK는 429·5xx·연결 오류를 judge.max_retries회
    다시 시도하고 재시도마다 요청을 새로 보내므로, 요청 수 − 성공 호출 수가 재시도 수이고
    상태 코드로 오류 종류를 안다(S25 D-51, 동시 수를 올리기 전에 확인할 값). 결과 파일에는
    넣지 않고 실행 출력에만 낸다. 대량 실행은 출력을 `_workspace/<작업>_run.log`로 남겨
    이 수를 보존한다(사용자 결정 2026-10-26, PR #154)."""

    def __init__(self):
        self.requests, self.status = 0, {}
        self.lock = threading.Lock()

    def on_request(self, request) -> None:
        with self.lock:
            self.requests += 1

    def on_response(self, response) -> None:
        with self.lock:
            self.status[response.status_code] = self.status.get(response.status_code, 0) + 1

    def summary(self, calls: int) -> str:
        """calls는 성공한 API 호출 수. 응답 없음은 타임아웃·연결 오류처럼 상태 코드가 없는 요청."""
        codes = ", ".join(f"{k} {v}" for k, v in sorted(self.status.items())) or "-"
        no_reply = self.requests - sum(self.status.values())
        return (f"HTTP 요청 {self.requests}회(응답 상태 {codes}, 응답 없음 {no_reply}), "
                f"성공 호출 밖 요청(재시도·실패) {self.requests - calls}회")


class Judge:
    """judge 호출 하나를 맡는다. 같은 요청 본문은 저장된 응답을 쓴다."""

    def __init__(self, cfg, session: str):
        j = cfg.judge
        self.j, self.prompt = j, j.prompt
        self.http = HttpCounts()
        self.client = wrap_openai(OpenAI(
            base_url=j.base_url, api_key=os.environ[j.api_key_env], timeout=j.timeout,
            max_retries=j.max_retries,
            default_headers={"User-Agent": j.user_agent, "x-opencode-session": session},
            http_client=DefaultHttpxClient(event_hooks={"request": [self.http.on_request],
                                                        "response": [self.http.on_response]})))
        self.params = OmegaConf.to_container(j.params)
        self.extra = OmegaConf.to_container(j.extra_body) if j.extra_body else None
        # 단계별로 params·extra_body를 덮어쓴다(예: 일부 단계만 사고 과정 켬, PR #106)
        self.step = OmegaConf.to_container(j.step_params) if j.get("step_params") else {}
        self.cache = ROOT / cfg.paths.gen_judge_cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.rep = j.rep
        self.lock = threading.Lock()
        self.calls = self.hits = 0

    def ask(self, step: str, **values: str) -> tuple[dict | None, dict]:
        """(파싱한 JSON 또는 None, usage). step은 지시 파일의 항목 이름.

        usage에는 토큰과 함께 단계 이름, 지연(latency_s), 저장 응답 사용 여부(cached), 끝난 이유
        (finish_reason)를 남긴다(S24). 저장 응답의 지연·끝난 이유는 저장할 때의 값이고, S24 전에
        저장한 응답에는 없다. 반복 번호(judge.rep)가 0보다 크면 요청 본문 해시(캐시 키)에 넣어 같은
        요청을 다시 묻는다. 0이면 키가 반복 도입 전과 같다(D-49)."""
        p = self.prompt[step]
        messages = [{"role": "system", "content": p.system},
                    {"role": "user", "content": render(p.user, **values)}]
        over = dict(self.step.get(step) or {})
        extra = over.pop("extra_body", self.extra)
        params = {**self.params, **over}
        body = {"model": self.j.model, "messages": messages, **params, "extra": extra}
        if self.rep:
            body["rep"] = self.rep
        path = self.cache / f"{sha(body)}.json"
        cached = path.exists()
        if cached:
            saved = json.loads(path.read_text(encoding="utf-8"))
            with self.lock:
                self.hits += 1
        else:
            t0 = time.perf_counter()
            r = self.client.chat.completions.create(
                model=self.j.model, messages=messages, extra_body=extra, **params)
            saved = {"content": r.choices[0].message.content,
                     "usage": r.usage.model_dump() if r.usage else None,
                     "latency_s": time.perf_counter() - t0,
                     "finish_reason": r.choices[0].finish_reason}
            # 빈 응답과 끝나지 않은 응답(잘림 등)은 저장하지 않아 다시 실행하면 다시 묻는다(D-42)
            if saved["content"] and saved["finish_reason"] == "stop":
                path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            with self.lock:
                self.calls += 1
        usage = {**(saved["usage"] or {}), "step": step, "cached": cached,
                 "latency_s": saved.get("latency_s"), "finish_reason": saved.get("finish_reason")}
        return parse_json(saved["content"]), usage


def same_statements(rows, statements: list[str]) -> bool:
    """judge 응답 목록이 입력 진술을 같은 순서·같은 문구로 담았는지(기준 문서 P6, S22 결정 사항 2).
    다르면 어느 판정이 어느 진술의 것인지 알 수 없어 형식 오류로 본다."""
    return (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
            and [r.get("statement") for r in rows] == statements)


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
    if not same_statements(verdicts, statements):
        return {"score": None, "error": "verdicts 형식 오류", "statements": statements,
                "usage": [u1, u2]}
    # speaker_unclear: 진술을 뒷받침한 근거 내용의 발언자를 구분할 수 없음(기준 문서 F7)
    ok = [v.get("verdict") in (0, 1) and isinstance(v.get("speaker_unclear"), bool)
          for v in verdicts]
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
    if not same_statements(checks, keys) or not all(c.get("present") in (0, 1) for c in checks):
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


def item_eval(judge: Judge, question: str, answer: str, contexts: list[dict]) -> dict:
    """질의 항목 단위 거부 평가(S14c, D-41 결정 2~4). 항목과 정보 상태는 답변 없이 근거로 정하고,
    처리는 근거 없이 답변으로 정한다. 맞는 처리인지는 코드가 정한다(checks.item_outcome).
    값이 정해진 값 밖이거나 처리의 항목 번호가 항목 단계와 다르면 형식 오류로 판단 불가다."""
    it, u1 = judge.ask("items", question=question, contexts=format_contexts(contexts))
    items = it.get("items") if it else None
    if (not isinstance(items, list) or not items
            or not all(isinstance(i, dict) and isinstance(i.get("item"), str)
                       and i.get("state") in STATES and isinstance(i.get("speaker_unclear"), bool)
                       for i in items)):
        return {"error": "items 형식 오류", "usage": [u1]}
    listed = [{"n": k, "item": i["item"]} for k, i in enumerate(items, 1)]
    hd, u2 = judge.ask("item_handling", question=question, answer=answer,
                       items=json.dumps(listed, ensure_ascii=False))
    handling = hd.get("handling") if hd else None
    if (not isinstance(handling, list)
            or [h.get("n") if isinstance(h, dict) else None for h in handling]
            != [x["n"] for x in listed]
            or not all(h.get("handling") in HANDLINGS for h in handling)):
        return {"error": "item_handling 형식 오류", "items": items, "usage": [u1, u2]}
    rows = [{**i, "handling": h["handling"], "handling_reason": h.get("reason"),
             "outcome": item_outcome(i["state"], h["handling"])}
            for i, h in zip(items, handling, strict=True)]
    return {"items": rows, "counts": item_counts(rows), "usage": [u1, u2]}


@traceable(name="judge_record", process_inputs=lambda i: {"qid": i["gen"]["qid"]})
def judge_record(judge: Judge, gen: dict, ref: dict, cfg, committees: set[str]) -> dict:
    """생성 기록 하나의 코드 판정과 judge 채점.

    정답 문서가 근거에 있으면 거부 여부와 관계없이 핵심 진술을 뽑고, 그 진술이 정답 문서의 근거
    청크에 들어 있는 비율이 gen_eval.chunk_key_min 이상이면 청크에 답이 있다고 본다(S14 결정 5).
    핵심 진술이 없거나 형식 오류면 answer_in_chunk는 None(판단 불가)이다.
    부분 거부 답변은 거부 문장을 뺀 내용으로 충실성·인용 검사를 하고(S14b, D-41), 관련성과
    포함도는 답변 전체로 본다. 관련성은 찾지 못했다고 밝힌 부분을 감점하지 않는다(D-47 결정 4)."""
    g = cfg.gen_eval
    answer, contexts = gen["answer"], gen["contexts"]
    gold_n = gold_position(contexts, ref["doc_id"])
    # 거부 문구는 생성 프롬프트 파일에 있다. 기록 경로에 prompt.version이 들어가 cfg.prompt가
    # 이 기록을 만든 프롬프트다(S16)
    kind, refused, rest = refusal_split(answer, cfg.prompt.refusal, list(g.filler_phrases))
    out = {"qid": gen["qid"], "refusal": kind, "refused_sentences": refused, "gold_n": gold_n,
           "answer_in_chunk": None, "usage": gen["usage"], "provider": gen["provider"],
           "first_token_s": gen["first_token_s"], "total_s": gen["total_s"],
           # S24 전 생성 기록에는 없다
           "retrieve_s": gen.get("retrieve_s"), "concurrency": gen.get("concurrency")}
    full = kind == "full"  # 전체 거부는 거부 집계로만 본다(초안 "거부 답변의 처리")

    def key_chain():
        ks = key_statements(judge, gen["query"], ref["answer_comment"]) if gold_n else None
        chunk = None
        if ks and ks["keys"]:
            chunk = key_presence(judge, "chunk_checks", ks["keys"],
                                 excerpt=contexts[gold_n - 1]["text"])
        inc = None if full else inclusion(judge, answer, ks)
        return ks, chunk, inc

    # 서로 입력이 이어지지 않는 네 사슬(포함도·근거 청크, 항목 평가, 충실성, 관련성)을 동시에
    # 부른다. 요청 본문은 차례로 부를 때와 같아 캐시 키와 판정은 바뀌지 않는다(S24 사용자 지시)
    with ThreadPoolExecutor(4) as ex:
        key_f = ex.submit(key_chain)
        # 항목 평가는 거부 여부와 관계없이 답변 전체로 본다(S14c)
        item_f = (ex.submit(item_eval, judge, gen["query"], answer, contexts)
                  if g.item_eval else None)
        faith_f = None if full else ex.submit(faithfulness, judge, gen["query"], rest, contexts)
        rel_f = None if full else ex.submit(relevance, judge, gen["query"], answer)
    ks, chunk, inc = key_f.result()
    if ks is not None:
        out["key_statements"] = ks
        if chunk is not None:
            out["chunk_keys"] = chunk
            if chunk["score"] is not None:
                out["answer_in_chunk"] = chunk["score"] >= g.chunk_key_min
    if item_f is not None:
        out["item_eval"] = item_f.result()
    if full:
        return out
    out["citations"] = citation_check(rest, len(contexts), list(g.filler_phrases))
    out["metadata"] = metadata_mismatches(rest, contexts, committees)
    out["faithfulness"] = faith_f.result()
    out["relevance"] = rel_f.result()
    out["inclusion"] = inc
    return out


def check_item_steps(cfg) -> None:
    """항목 평가를 켰는데 judge 지시 파일에 두 단계가 없으면 judge 호출 전에 멈춘다(S14c, ADR-0056).
    없으면 첫 생성 기록에서 원인을 알 수 없는 KeyError가 난다."""
    missing = [s for s in ("items", "item_handling") if s not in cfg.judge.prompt]
    if cfg.gen_eval.item_eval and missing:
        raise SystemExit(f"gen_eval.item_eval=true인데 judge 지시 {cfg.judge.prompt.version}에 "
                         f"{', '.join(missing)} 단계가 없다. j_v7 이후 지시를 쓰거나 "
                         "gen_eval.item_eval=false로 실행한다")


def run_all(fn, items: list, concurrency: int, name) -> list:
    """items를 동시에 처리해 입력 순서대로 돌려준다. 하나라도 실패하면 아직 시작하지 않은 항목을
    취소하고, 실행 중인 항목이 끝나면 실패한 항목과 원인을 모두 적고 멈춘다. Ctrl+C도 시작하지
    않은 항목을 취소하고 그대로 올린다. 성공한 응답은 judge 캐시에 남아 다시 실행하면 이어진다.
    입력 순서로 결과를 꺼내는 map은 앞 항목이 늦으면 뒤 항목의 실패를 늦게 알아 그동안 남은
    항목을 계속 채점했다(이슈 #156)."""
    ex = ThreadPoolExecutor(concurrency)
    futures = [ex.submit(fn, x) for x in items]
    try:
        # Windows에서는 timeout 없는 대기가 Ctrl+C로 깨지 않아 1초마다 깨어난다
        while True:
            done, pending = wait(futures, timeout=1, return_when=FIRST_EXCEPTION)
            if not pending or any(f.exception() for f in done):
                break
    finally:
        ex.shutdown(cancel_futures=True)
    failed = [f"{name(x)}: {type(f.exception()).__name__}: {f.exception()}"
              for x, f in zip(items, futures, strict=True)
              if not f.cancelled() and f.exception()]
    if failed:
        skipped = sum(f.cancelled() for f in futures)
        raise SystemExit(f"judge 실패 {len(failed)}건, 시작하지 않고 취소 {skipped}건"
                         "(다시 실행하면 저장된 응답으로 이어진다):\n" + "\n".join(failed))
    return [f.result() for f in futures]


def judge_cases(cfg) -> None:
    """판정 확인 사례(S14c)를 항목 평가로만 채점한다. 사례 줄은 case·query·answer·contexts를 담는다.
    결과는 judge 지시·설정에 따라 달라지므로 출력이 있으면 시작할 때 멈춘다. 사례 파일의 해시를
    레시피에 남겨, 사례 정답을 고친 뒤 옛 결과와 대조하면 report가 멈춘다(이슈 #142)."""
    src = ROOT / cfg.gen_eval.item_cases
    out = src.with_suffix(".judge.jsonl")
    refuse_existing(out, cfg.search.overwrite)
    cases = read_jsonl(src)
    rec = judge_recipe(cfg, [])  # 합성 답변이라 생성 기록이 없다
    rec["item_cases_sha256"] = hashlib.sha256(src.read_bytes()).hexdigest()
    judge = Judge(cfg, session=f"meet-rag-judge-{sha(stable(rec))[:16]}")
    try:
        rows = run_all(lambda c: {"case": c["case"], **item_eval(
            judge, c["query"], c["answer"], c["contexts"])}, cases, cfg.judge.concurrency,
            lambda c: c["case"])
    finally:  # 재시도를 다 쓰고 멈춘 실행에서도 오류 수를 남긴다
        print(judge.http.summary(judge.calls))
    get_cached_client().flush()
    text = "".join(json.dumps({**r, "judge_recipe": rec}, ensure_ascii=False) + "\n" for r in rows)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"사례 {len(rows)}개, API 호출 {judge.calls}회, 저장된 응답 {judge.hits}회 -> {out}")


def main() -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    check_item_steps(cfg)
    if cfg.gen_eval.item_cases:
        judge_cases(cfg)
        return
    refuse_existing(ROOT / cfg.paths.gen_judge, cfg.search.overwrite)  # judge 호출 전에 본다
    gens = {r["qid"]: r for r in read_jsonl(ROOT / cfg.paths.gen_runs)}
    qids = [q for q in eval_qids(cfg) if q in gens]  # 표본 순서. 아직 생성하지 않은 qid는 뺀다
    refs = load_refs(cfg, qids)
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        committees = {committee_base(json.loads(line)["committee_name"]) for line in f} - {""}
    recipes = {sha(stable(gens[q]["recipe"])) for q in qids}  # 이어 쓰기(done_qids)와 같은 규칙
    if len(recipes) != 1:
        raise SystemExit("생성 기록의 레시피가 여럿이다")
    check_prompt(cfg, gens[qids[0]]["recipe"])
    rec = judge_recipe(cfg, [gens[q]["recipe"] for q in qids])
    judge = Judge(cfg, session=f"meet-rag-judge-{sha(stable(rec))[:16]}")

    def one(qid):
        return judge_record(judge, gens[qid], refs[qid], cfg, committees,
                            langsmith_extra={"metadata": {"qid": qid, **rec}})

    try:
        rows = run_all(one, qids, cfg.judge.concurrency, str)
    finally:  # 재시도를 다 쓰고 멈춘 실행에서도 오류 수를 남긴다
        print(judge.http.summary(judge.calls))
    get_cached_client().flush()
    text = "".join(json.dumps({**r, "judge_recipe": rec}, ensure_ascii=False) + "\n" for r in rows)
    state = write_guarded(ROOT / cfg.paths.gen_judge, text, cfg.search.overwrite)
    print(f"{len(rows)}개 채점, API 호출 {judge.calls}회, 저장된 응답 {judge.hits}회 "
          f"-> {cfg.paths.gen_judge} ({state})")


if __name__ == "__main__":
    main()
