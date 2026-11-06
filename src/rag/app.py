"""채팅 API. 자유 질의를 검색해 답변을 스트리밍으로 보내고 끝나면 근거를 붙인다. 화면은 Vercel
페이지가 맡고 여기에는 화면이 없다(S48, D-88 결정 2).

명세는 docs/slices/35-chat-app.md. 실시간 재정렬은 Space 진입점이 GPU 점수 함수를 넘길 때만 켠다
(S39). 로컬에는 GPU가 없어 재정렬을 끈 구성으로 시작한다. 방문자 질의는 data/에 저장하지 않고
LangSmith 추적으로만 남는다.
"""

import base64
import gzip
import html
import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from langsmith.run_trees import configure
from omegaconf import OmegaConf

from rag.display import MeetingInfoMover, WordReplacer, move_meeting_info, replace_words
from rag.docs import Corpus, doc_body, doc_name, readable, shown_date, source_name
from rag.gen_eval.checks import CITE
from rag.generate import Pipeline, recipe
from rag.index import load_cfg
from rag.rewrite import FollowUpRewriter, PrevDecider
from rag.speakers import render


class TracingSwitch(logging.Handler):
    """LangSmith 월 한도를 넘으면 추적을 끄고 다음 달에 다시 켠다(D-71 자동화). 전송 실패는
    클라이언트 경고 로그로만 알 수 있어 로그를 본다. 끈 상태는 저장하지 않는다. 재시작하면 켠
    상태로 시작하고, 아직 한도를 넘었으면 첫 전송 실패로 다시 꺼진다."""

    LIMIT = "Rate limit exceeded"

    def __init__(self, today: Callable[[], date] = date.today):
        super().__init__(logging.WARNING)
        self.today = today
        self.off_month = None

    def month(self) -> tuple[int, int]:
        d = self.today()
        return d.year, d.month

    def emit(self, record: logging.LogRecord) -> None:
        if self.off_month is None and self.LIMIT in record.getMessage():
            self.off_month = self.month()
            configure(enabled=False)
            print("LangSmith 한도 초과로 추적을 끈다. 다음 달에 다시 켠다", flush=True)

    def refresh(self) -> None:
        if self.off_month is not None and self.off_month != self.month():
            self.off_month = None
            configure(enabled=True)
            print("달이 바뀌어 LangSmith 추적을 다시 켠다", flush=True)


TRACING = TracingSwitch()


class UsageLimit:
    """질문 수 한도(S41). 공개 Space는 누구나 부를 수 있어 같은 IP의 1시간·하루 질문 수와 하루 전체
    질문 수를 센다. 셈은 메모리에 두어 재시작하면 처음부터 센다. 하루는 Space 시계(UTC) 기준이다.
    check는 넘었으면 안내 글을, 아니면 None을 돌려주고 그 질문을 센다."""

    def __init__(self, limits, now: Callable[[], float] = time.time,
                 today: Callable[[], date] = date.today):
        # 설정 값을 시작할 때 읽어, 키가 빠지면 첫 질문이 아니라 앱 시작에서 멈춘다
        self.per_ip_hour, self.per_ip_day = int(limits.per_ip_hour), int(limits.per_ip_day)
        self.per_day = int(limits.per_day)
        self.per_ip_text, self.per_day_text = str(limits.per_ip_text), str(limits.per_day_text)
        self.now, self.today = now, today
        self.by_ip: dict[str, deque] = defaultdict(deque)
        self.day, self.count = None, 0
        self.ip_day: dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()

    def check(self, ip: str) -> str | None:
        with self.lock:
            if self.day != self.today():
                self.day, self.count = self.today(), 0
                self.ip_day.clear()
            if self.count >= self.per_day:
                return self.per_day_text
            t, seen = self.now(), self.by_ip[ip]
            while seen and seen[0] <= t - 3600:
                seen.popleft()
            if len(seen) >= self.per_ip_hour or self.ip_day[ip] >= self.per_ip_day:
                return self.per_ip_text
            seen.append(t)
            self.ip_day[ip] += 1
            self.count += 1
            return None


IP_PROBE = "198.51.100.7"  # 임시(S41): 문서용 주소 대역. 확인 요청이 헤더에 넣는 시험 값


def ip_header_probe(request) -> None:
    """임시(S41): 프록시가 x-forwarded-for를 어떻게 넘기는지 본다. 실제 주소는 남기지 않는다."""
    import ipaddress
    if request is None:
        return
    parts = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    host = request.client.host if request.client else ""
    try:
        private = ipaddress.ip_address(host).is_private
    except ValueError:
        private = None
    first, last = bool(parts) and parts[0] == IP_PROBE, bool(parts) and parts[-1] == IP_PROBE
    print(f"IP 헤더 확인: 주소 {len(parts)}개, 시험 값 맨 앞 {first}, 맨 끝 {last}, "
          f"접속 주소 사설망 {private}", flush=True)


def client_ip(request) -> str:
    """방문자 IP. Space는 프록시 뒤라 x-forwarded-for의 첫 값을 쓴다. 로그에는 남기지 않는다."""
    forwarded = request.headers.get("x-forwarded-for", "") if request else ""
    return forwarded.split(",")[0].strip() or (request.client.host if request else "")


CITATION = re.compile(r"\s*(?:\[\d+\])+")


def clean_history(history, cfg) -> list[dict]:
    """페이지가 보낸 앞 대화(S40). 방문자가 고칠 수 있어 믿지 않는다. 질문·답변이 글자가 아닌 턴은
    버리고, 최근 max_turns턴만 남기고, 앞 답변의 인용 번호를 지운 뒤 길이를 자른다. 번호를 지우는
    것은 지난 근거의 [1]과 이번 근거의 [1]이 섞이지 않게 하려는 것이다(결정 사항 2)."""
    m = cfg.app.multiturn
    if not isinstance(history, list):
        return []
    turns = [{"question": h["question"].strip()[:cfg.app.max_query_chars],
              "answer": CITATION.sub("", h["answer"]).strip()[:m.max_answer_chars]}
             for h in history
             if isinstance(h, dict) and isinstance(h.get("question"), str)
             and isinstance(h.get("answer"), str) and h["question"].strip() and h["answer"].strip()]
    return turns[max(0, len(turns) - m.max_turns):]


def last_rows(history, cfg, n_chunks: int) -> list[int]:
    """직전 답변이 인용한 근거의 청크 번호(S51). 페이지가 마지막 턴의 rows로 보낸다. 믿지 않으므로
    정수이고 인덱스 범위 안인 것만 앞에서부터 max_chunks개 남긴다. 원문은 서버가 다시 읽는다."""
    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
        return []
    rows = history[-1].get("rows")
    if not isinstance(rows, list):
        return []
    ok = [r for r in rows if type(r) is int and 0 <= r < n_chunks]
    return list(dict.fromkeys(ok))[:cfg.app.multiturn.reuse.max_chunks]


def follow_up(cfg) -> Callable[[str, list[dict]], tuple[str, dict]]:
    """후속 질문의 재작성(S40)과 앞 근거 판단(S51). decision이면 판단 모델을 재작성과 병렬로 불러
    지연이 둘 중 긴 쪽만큼만 든다. rewrite면 재작성 지시가 표시(flag)를 내야 한다."""
    mode = cfg.app.multiturn.reuse.mode
    if mode not in ("off", "rule", "rewrite", "decision"):
        raise SystemExit(f"app.multiturn.reuse.mode는 off·rule·rewrite·decision 중 하나다: {mode}")
    rewriter = FollowUpRewriter(cfg)
    if mode == "rewrite" and not rewriter.prompt.get("flag"):
        raise SystemExit("reuse.mode=rewrite는 표시(flag)를 내는 재작성 지시가 필요하다: "
                         f"{cfg.app.multiturn.rewrite.prompt}")
    if mode != "decision":
        return rewriter
    decider = PrevDecider(cfg)
    pool = ThreadPoolExecutor(2)

    def both(message: str, turns: list[dict]) -> tuple[str, dict]:
        decided = pool.submit(decider, message, turns)
        search, meta = rewriter(message, turns)
        return search, {**meta, **decided.result()}

    return both


def chunk_row(pipe, c: dict) -> int:
    """근거의 dense 청크 번호(ChunkStore 순서). 인덱스 이름과 그 인덱스 안의 번호로 계산한다."""
    store = pipe.store
    return int(store.bounds[store.names.index(c["index"])]) + int(c["chunk_id"])


def shown_words(cfg) -> dict[str, str]:
    """화면 글에서 바꿀 말(S52, app.shown_words). 빈 말은 모든 글자 사이에 새 말을 넣어 화면을
    조용히 망가뜨리므로 읽을 때 멈춘다."""
    words = OmegaConf.to_container(cfg.app.shown_words)
    if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in words.items()):
        raise SystemExit(f"app.shown_words는 빈 글자가 아닌 말을 글자로 바꾼다: {words}")
    return words


def shown(stream: Iterator[str | dict], max_name: int,
          words: dict[str, str] | None = None) -> Iterator[str | dict]:
    """pipe.stream의 답변을 화면 글로 바꾼다(S45). 생성 결과와 추적에는 원문이 남는다. 잡아 둔
    동안은 내보내지 않고, 첫 원문 조각과 첫 표시 글자 사이의 시간을 로그에 남긴다. words가 있으면
    회의 정보를 옮긴 뒤 그 말을 바꾼다(S52, 거부 문구의 "제공된 회의록" 등)."""
    mover = MeetingInfoMover(max_name)
    words = words or {}
    replacer = WordReplacer(words)
    raw_at = None
    logged = False
    for item in stream:
        if isinstance(item, dict):
            out = {**item, "answer": replace_words(move_meeting_info(item["answer"], max_name),
                                                   words), "raw": item["answer"]}
        else:
            raw_at = raw_at or time.perf_counter()
            out = replacer.feed(mover.feed(item))
        if out:
            if raw_at and not logged:
                print(f"첫 글자 지연: {time.perf_counter() - raw_at:.3f}초", flush=True)
                logged = True
            yield out


def context_payload(c: dict, corpus) -> dict:
    """정적 페이지(S39b)에 주는 근거 하나. 값을 골라 내 라벨·분할 정보가 나가지 않는다. 본문은
    페이지가 글자로 넣으므로 이스케이프를 푼다."""
    start, end = corpus.chunk_span(c["doc_id"], c["text"]) or (-1, -1)
    return {"n": c["n"], "date": shown_date(c), "committee_name": c["committee_name"],
            "name": source_name(corpus.meta[c["doc_id"]]),
            "original": c["original"], "doc_id": c["doc_id"], "start": start, "end": end,
            "body": html.unescape(readable(render(c)))}


def chat_events(pipe, cfg, rec: dict, corpus, message: str, history=None,
                rewriter: Callable[[str, list[dict]], tuple[str, dict]] | None = None,
                log: dict | None = None,
                gate: Callable[[], str | None] | None = None) -> Iterator[dict]:
    """정적 페이지의 채팅. 지금까지의 답변을 조각마다 보내고 마지막에 근거와 생성 원문(raw)을
    붙인다. 페이지는 raw와 인용한 근거의 청크 번호(rows, S51)를 앞 대화로 들고 있다가 다음 질문에
    보낸다(S40). 앞 대화가 없으면
    재작성하지 않고 지금과 같은 프롬프트로 처리한다. API를 직접 불러 빈 질문을 보내면 생성을
    부르지 않는다. log를 주면 검색 질의·판단 값·앞 근거·근거를 담는다(표본 실행, S51)."""
    if not message.strip():
        return
    if len(message) > cfg.app.max_query_chars:  # 검색과 유료 생성을 부르지 않는다(S49)
        yield {"text": cfg.app.query_too_long, "done": True, "contexts": [], "raw": "", "rows": []}
        return
    if gate and (note := gate()):  # 사용 한도(S41). 검색과 유료 생성을 부르지 않는다
        print(f"사용 한도: {note}", flush=True)
        yield {"text": note, "done": True, "contexts": [], "raw": "", "rows": []}
        return
    TRACING.refresh()
    turns = clean_history(history, cfg)
    turn = len(turns) + 1
    search, meta = (message, {}) if not turns else rewriter(message, turns)
    if meta:  # 질의 원문은 로그에 남기지 않는다
        print(f"턴 {turn}: 재작성 {meta['rewrite_s']:.3f}초({meta['rewrite_status']})", flush=True)
    if "decision_s" in meta:
        print(f"턴 {turn}: 판단 {meta['decision_s']:.3f}초({meta['decision_status']})", flush=True)
    mode = cfg.app.multiturn.reuse.mode
    # rule은 retrieve가 후보로 거르고, rewrite·decision은 판단이 필요하다고 할 때만 넘긴다(S51)
    prev = (last_rows(history, cfg, pipe.index_meta["n_chunks"])
            if turns and (mode == "rule" or (mode != "off" and meta.get("needs_prev"))) else [])
    text = ""
    stream = pipe.stream(message, pipe.embed(search), turns, search, prev,
                         langsmith_extra={"metadata": {**rec, **meta, "turn": turn,
                                                       "prev_rows": len(prev)}})
    words = shown_words(cfg)
    for item in shown(stream, cfg.app.meeting_info_max_name, words):
        if isinstance(item, dict):
            if item.get("first_token_s") is not None:
                print(f"턴 {turn}: 첫 토큰 {item['first_token_s']:.3f}초", flush=True)
            ctx = item["contexts"]
            if log is not None:
                log.update(search=search, meta=meta, prev=prev, contexts=ctx,
                           first_token_s=item.get("first_token_s"))
            # 페이지가 다음 질문에 보낼 청크 번호: 이 답변이 인용한 근거만(S51). 끄면 보내지 않는다
            cited = sorted({int(n) for n in CITE.findall(item["raw"]) if 1 <= int(n) <= len(ctx)})
            rows = [chunk_row(pipe, ctx[n - 1]) for n in cited] if mode != "off" else []
            # 길이 제한으로 끝난 답변은 페이지가 답변 아래에 알린다(S41)
            notice = cfg.app.cut_notice if item.get("finish_reason") == "length" else ""
            yield {"text": item["answer"] or cfg.app.no_answer, "done": True, "raw": item["raw"],
                   "rows": rows, "notice": notice,
                   "contexts": [context_payload(c, corpus) for c in ctx]}
        else:
            text += item
            yield {"text": text, "done": False}


def packed(value) -> str:
    """JSON을 gzip으로 줄여 base64 글자로 보낸다. 페이지가 DecompressionStream으로 푼다(S41)."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def doc_payload(pipe, cfg, corpus, doc_id: str, start: int, end: int) -> dict:
    """정적 페이지의 문서 한 건. start가 음수면 근거 위치 표시를 하지 않는다."""
    doc = corpus.read(doc_id)
    labels = cfg.app.labels
    spans = pipe.spans.get(doc_id, []) if pipe.speakers != "off" else []
    body = doc_body(doc, spans, pipe.speakers, (start, end) if start >= 0 else None,
                    (labels.chunk_start, labels.chunk_end))
    return {"name": doc_name(doc), "agenda": doc["agenda"], "original": doc["original"],
            "body": html.unescape(body)}


def build(cfg, pipe, corpus, endpoint: Callable | None = None):
    """API만 여는 Blocks를 만든다. 평가·실험 환경에는 gradio가 없어 여기서 불러온다(pyproject의
    app). endpoint는 Space의 GPU 점수 함수로, 토큰 호출에 쓰도록 API 문서에 보이지 않는 경로로
    연다(S39, D-74)."""
    import gradio as gr

    # 대화 이어 가기 설정은 첫 질문 동작을 바꾸지 않아 생성 레시피 밖의 추적 메타데이터로 남긴다
    # (S40)
    shown_words(cfg)  # 시작할 때 설정을 확인한다
    rec = {**recipe(cfg, pipe.index_meta, True),
           "multiturn": OmegaConf.to_container(cfg.app.multiturn)}
    rewriter = follow_up(cfg)
    api = {"api_visibility": "undocumented"}

    limit = UsageLimit(cfg.app.limits)

    def chat(message: str, history: list | None = None,
             request: gr.Request = None) -> Iterator[dict]:
        # history는 앞 대화(S40). 기본값이 있어 앞 대화를 보내지 않는 페이지도 그대로 동작한다.
        # request는 Gradio가 넣는 특수 인자라 API 입력에 나오지 않는다
        yield from chat_events(pipe, cfg, rec, corpus, message, history, rewriter,
                               gate=lambda: limit.check(client_ip(request)))

    def years(request: gr.Request = None) -> list[int]:
        ip_header_probe(request)  # 임시: IP 헤더 위조 확인(S41). 확인 뒤 지운다
        return corpus.years()

    def examples() -> list[str]:
        return list(cfg.app.examples)

    def meetings(year: int) -> list[list[str]]:
        return [list(m) for m in corpus.meetings(year)]

    def meetings_packed(year: int) -> str:
        # 연도 하나의 회의 목록은 44~72KB이고 Space 응답은 압축되지 않아 전송이 회의 칸
        # 지연의 대부분이다(S41). 페이지가 풀어 쓴다. 병합 전 페이지가 meetings를 부르므로
        # 둘 다 연다
        return packed(meetings(year))

    def documents(conference: str) -> list[list[str]]:
        return [list(d) for d in corpus.documents(conference)]

    def document(doc_id: str, start: int, end: int) -> dict:
        return doc_payload(pipe, cfg, corpus, doc_id, start, end)

    with gr.Blocks(title=cfg.app.title) as demo:
        if endpoint is not None:
            gr.api(endpoint, api_name=cfg.deploy.rerank.api_name, **api)
        # 동시 처리 수(app.concurrency)를 chat 그룹에 건다
        gr.api(chat, api_name="chat", concurrency_id="answer", **api)
        # 답변 생성이 큐를 잡고 있어도 문서를 볼 수 있게 문서 함수는 큐를 거치지 않는다
        for fn in (years, examples, meetings, meetings_packed, documents, document):
            gr.api(fn, api_name=fn.__name__, queue=False, **api)
    return demo


def main(endpoint: Callable | None = None, scorer: Callable | None = None,
         embedder: Callable | None = None) -> None:
    cfg = load_cfg(["index.scope=full", *sys.argv[1:]])
    if cfg.retriever.get("rerank") and cfg.retriever.rerank.enabled and scorer is None:
        raise SystemExit("실시간 재정렬은 Space의 GPU 점수 함수가 있어야 한다(S39). 로컬은 "
                         "retriever.rerank.enabled=false로 실행한다")
    if cfg.app.concurrency != 1:
        # 임베딩 프로세스 파이프와 재정렬 멈춤 상태가 질의 하나씩을 전제한다. 둘이 겹치면 오류 없이
        # 서로의 질의 벡터를 받는다(이슈 #239)
        raise SystemExit(f"app.concurrency는 1만 지원한다: {cfg.app.concurrency}")
    logging.getLogger("langsmith.client").addHandler(TRACING)
    start = time.perf_counter()
    pipe = Pipeline(cfg, scorer=scorer, embedder=embedder)
    loaded = time.perf_counter()
    pipe.embed(cfg.app.title)  # 임베딩 모델을 먼저 불러 첫 질의가 기다리지 않게 한다
    parts = ", ".join(f"{k} {v:.1f}초" for k, v in pipe.retriever.timings.items())
    print(f"시작: 인덱스·코퍼스 {loaded - start:.1f}초({parts}), 임베딩 모델 "
          f"{time.perf_counter() - loaded:.1f}초", flush=True)
    demo = build(cfg, pipe, Corpus(cfg), endpoint)
    demo.queue(default_concurrency_limit=cfg.app.concurrency).launch()


if __name__ == "__main__":
    main()
