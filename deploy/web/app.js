// 정적 채팅 화면(docs/slices/39b-vercel-front.md). 검색과 생성은 Space API가 맡는다.
// 답변과 문서 본문은 글자로만 넣어 HTML이 해석되지 않게 한다.
import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client@2.7.2/dist/index.min.js";

const SPACE = "ingyoun/meet-rag";
const WAIT_MS = 5000; // 첫 토큰이 이 시간 안에 오지 않으면 대기 문구를 보인다
const WAIT_TEXT = "근거를 찾아 답변을 준비하고 있습니다.";
const CONNECTING_TEXT = "서버에 연결하고 있습니다. 잠시만 기다려 주세요.";
const RETRY_MS = 5000;
const CONTEXTS_TITLE = "근거";
const FAILED_TEXT = "답변을 만들지 못했습니다. 다시 시도해 주세요.";
const CHUNK_START = "▼ 답변에 쓴 근거";
const YEAR_SETTLE_MS = 400; // 연도가 이 시간 동안 그대로면 회의 목록을 요청한다

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

let client = null;
let connecting = null;

/** Space에 닿을 때까지 다시 시도한다. 잠든 Space는 시작에 시간이 걸린다. */
function connect() {
  if (client) return Promise.resolve(client);
  connecting ??= (async () => {
    for (;;) {
      try {
        // 공개 전 점검용 토큰(D-88 결정 3). S41에서 지우고 토큰을 폐기한다.
        const token = localStorage.getItem("hf_token") ?? undefined;
        client = await Client.connect(SPACE, { events: ["data", "status"], token });
        $("connection").hidden = true;
        loadYears().catch(() => findStatus("회의록 목록을 불러오지 못했습니다. 페이지를 새로 고쳐 주세요."));
        loadExamples().catch(() => {}); // 추천 질문이 없어도 입력칸으로 물을 수 있다
        loadMeetingIndex().catch(() => {}); // 받지 못하면 연도를 고를 때마다 요청한다
        return client;
      } catch {
        $("connection").textContent = CONNECTING_TEXT;
        $("connection").hidden = false;
        await new Promise((done) => setTimeout(done, RETRY_MS));
      }
    }
  })();
  return connecting;
}

const call = async (name, args = []) => (await (await connect()).predict(`/${name}`, args)).data[0];

/** 글 조각을 넣는다. cite가 있으면 `[n]`을 cite(n)이 돌려준 노드로 바꾼다(없으면 글자 그대로). */
function appendText(parent, text, cite) {
  if (!cite) return parent.append(text);
  for (const [i, piece] of text.split(/\[(\d+)\]/).entries()) {
    parent.append(i % 2 ? (cite(Number(piece)) ?? `[${piece}]`) : piece);
  }
}

/** 줄바꿈으로 나뉜 글을 문단으로 넣는다. 한 문단 전체가 **굵게**이면 표지로 보인다. */
function fillParagraphs(parent, text, onMark, cite) {
  for (const part of text.split(/\n{2,}/)) {
    const line = part.trim();
    if (!line) continue;
    const bold = line.match(/^\*\*([^*]+)\*\*$/);
    const p = el("p");
    if (bold) {
      p.append(el("strong", onMark?.(bold[1]) ? "mark" : "", bold[1]));
    } else {
      for (const [i, piece] of line.split("**").entries()) {
        if (i % 2) {
          const strong = el("strong");
          appendText(strong, piece, cite);
          p.append(strong);
        } else {
          appendText(p, piece, cite);
        }
      }
    }
    parent.append(p);
  }
}

// 대화 ---------------------------------------------------------------------

let busy = false;
// 앞 대화(S40). 페이지 메모리에만 두어 새로 고치거나 "새 채팅"을 누르면 지워진다.
// 답변은 화면 글이 아니라 생성 원문(raw)을 들고, 최근 HISTORY_TURNS턴만 보낸다(서버도 같은 수로 자른다).
// rows는 그 답변이 인용한 근거의 청크 번호로, 서버가 다음 질문에서 근거를 다시 쓸 때 읽는다(S51)
const HISTORY_TURNS = 3;
let history = [];

/** 답변 아래 근거 목록. 답변이 인용한 근거와 참고만 한 근거(검색은 됐지만 인용되지 않음)를 나눈다(S41).
 *  돌려준 cite(n)은 답변 글의 `[n]`에 넣을 버튼을 만든다. 누르면 목록을 열고 그 근거로 옮긴다. */
function renderSources(contexts, text) {
  const cited = new Set([...text.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])));
  const used = contexts.filter((c) => cited.has(c.n));
  const rest = contexts.filter((c) => !cited.has(c.n));
  const details = el("details", "sources");
  const summary = rest.length && used.length
    ? `${CONTEXTS_TITLE} ${used.length}개, 참고만 한 근거 ${rest.length}개`
    : `${CONTEXTS_TITLE} ${contexts.length}개`;
  details.append(el("summary", "", summary));
  const items = new Map();
  for (const [title, group] of [["답변에 인용한 근거", used], ["참고만 한 근거", rest]]) {
    if (!group.length) continue;
    if (used.length && rest.length) details.append(el("p", "source-group muted", title));
    for (const c of group) {
      const name = `${c.date} ${c.committee_name}`;
      const source = el("div", "source");
      source.tabIndex = -1; // 답변의 번호를 누르면 초점이 여기로 온다
      const head = el("div", "source-head");
      const open = el("button", "source-open", "원문에서 보기");
      open.type = "button";
      open.setAttribute("aria-label", `근거 ${c.n} ${name} 원문에서 보기`);
      open.addEventListener("click", () => openDocument(c.doc_id, c.start, c.end, open));
      head.append(el("strong", "source-title", `[${c.n}] ${name}`), open, originalLink(c.original, name));
      source.append(head);
      fillParagraphs(source, c.body);
      details.append(source);
      items.set(c.n, { source, name });
    }
  }
  const cite = (n) => {
    const item = items.get(n);
    if (!item) return null;
    const button = el("button", "cite", `[${n}]`);
    button.type = "button";
    button.title = item.name;
    button.setAttribute("aria-label", `근거 ${n}, ${item.name}`);
    button.addEventListener("click", () => {
      details.open = true;
      item.source.scrollIntoView({ block: "center", behavior: reduceMotion.matches ? "auto" : "smooth" });
      item.source.focus({ preventScroll: true });
      item.source.classList.remove("flash");
      void item.source.offsetWidth; // 같은 근거를 다시 눌러도 강조가 다시 보이게 한다
      item.source.classList.add("flash");
    });
    return button;
  };
  return { details, cite };
}

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

async function ask(message) {
  busy = true;
  updateSend();
  $("intro").hidden = true;
  const question = el("div", "user", message);
  const answer = el("div", "answer");
  const status = el("div", "status");
  const dots = el("span", "dots");
  dots.append(el("i"), el("i"), el("i"));
  status.append(dots);
  answer.append(status);
  $("messages").append(question, answer);
  question.scrollIntoView({ block: "start" });
  $("announce").textContent = "답변을 준비하고 있습니다.";

  // 첫 토큰이 늦으면 답변 밖 표시만 바꾼다. 답변 글에는 넣지 않는다
  const timer = setTimeout(() => {
    status.replaceChildren(el("span", "spinner"), el("span", "", WAIT_TEXT));
  }, WAIT_MS);
  const body = el("div");
  const showText = (text, cite) => {
    clearTimeout(timer);
    status.remove();
    if (!body.isConnected) answer.prepend(body);
    body.replaceChildren();
    fillParagraphs(body, text, undefined, cite);
  };

  try {
    const job = (await connect()).submit("/chat", [message, history.slice(-HISTORY_TURNS)]);
    let raw = "";
    let rows = [];
    let sources = null;
    for await (const event of job) {
      if (event.type === "status" && event.stage === "error") throw new Error(event.message);
      if (event.type !== "data") continue;
      const item = event.data[0];
      // 클라이언트가 마지막 값을 한 번 더 보내므로 근거는 처음 한 번만 만든다. 답변 글의 번호는 근거가 온
      // 뒤에야 버튼이 된다(스트리밍 중에는 글자다)
      if (item.done && item.contexts.length && !sources) sources = renderSources(item.contexts, item.text);
      showText(item.text, sources?.cite);
      if (item.done) ({ raw, rows = [] } = item);
      if (item.done && item.notice && !answer.querySelector(".notice")) answer.append(el("p", "notice muted", item.notice));
      if (sources && !sources.details.isConnected) answer.append(sources.details);
    }
    // 답을 만들지 못한 질문은 앞 대화에 넣지 않는다
    if (raw) history = [...history, { question: message, answer: raw, rows }].slice(-HISTORY_TURNS);
    const notice = answer.querySelector(".notice")?.textContent;
    $("announce").textContent = notice ? `답변을 마쳤습니다. ${notice}` : "답변을 마쳤습니다.";
  } catch {
    // 끝나지 않은 답변은 인용이 빠질 수 있어 지우고, 질문은 다시 보내기 쉽게 입력칸에 되살린다(S41 결정 사항 3)
    showText(FAILED_TEXT);
    $("announce").textContent = FAILED_TEXT;
    if (!$("input").value.trim()) {
      $("input").value = message;
      $("input").dispatchEvent(new Event("input")); // 입력칸 높이를 글에 맞춘다
    }
    // Space가 재시작했을 수 있어 다음 요청 전에 새로 연결한다
    client = null;
    connecting = null;
    connect();
  } finally {
    clearTimeout(timer);
    busy = false;
    updateSend();
  }
}

const updateSend = () => {
  $("send").disabled = busy || !$("input").value.trim();
  $("new-chat").disabled = busy;
};

/** 대화 칸과 앞 대화를 비운다. 문서 뷰어와 문서 찾기 선택은 그대로 둔다. Space를 부르지 않는다. */
$("new-chat").addEventListener("click", () => {
  if (busy) return;
  history = [];
  $("messages").replaceChildren();
  $("intro").hidden = false;
});

/** 빈 화면의 추천 질문(S41). 질문 글은 Space 설정(app.examples)에서 받는다. 누르면 바로 보낸다. */
async function loadExamples() {
  if ($("examples").childElementCount) return; // 다시 연결해도 두 번 넣지 않는다
  for (const text of await call("examples")) {
    const button = el("button", "ghost-button", text);
    button.type = "button";
    button.addEventListener("click", () => {
      if (!busy) ask(text);
    });
    $("examples").append(button);
  }
}

function submit() {
  const message = $("input").value.trim();
  if (!message || busy) return;
  $("input").value = "";
  $("input").style.height = "auto";
  ask(message);
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  submit();
});

$("input").addEventListener("keydown", (event) => {
  // 한글 조합 중의 Enter는 글자 확정이므로 보내지 않는다
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submit();
  }
});

$("input").addEventListener("input", () => {
  const box = $("input");
  box.style.height = "auto";
  box.style.height = `${box.scrollHeight}px`;
  updateSend();
});

// 패널 ---------------------------------------------------------------------
// 넓은 화면: 문서 찾기와 문서 뷰어가 대화 옆에 붙는다. 뷰어를 열면 문서 찾기가 접힌다(S52).
// 좁은 화면(태블릿 세로): 두 패널이 화면을 덮는 서랍이다. 열면 초점을 서랍 안으로 옮기고 뒤 화면을
// inert로 막는다. Esc나 닫기로 닫으면 연 곳으로 초점을 돌린다(점검 UI-3).

const narrow = window.matchMedia("(max-width: 1023.98px)");
const sidebar = $("sidebar");
const viewer = $("viewer");
let viewerOpener = null;

const isOpen = (panel) => panel.classList.contains("open");
const drawer = () => (narrow.matches ? [sidebar, viewer].find(isOpen) ?? null : null);

function sync() {
  const open = drawer();
  $("scrim").hidden = !open;
  for (const node of [sidebar, $("chat"), viewer]) node.inert = Boolean(open) && node !== open;
  $("open-sidebar").hidden = isOpen(sidebar) && !narrow.matches;
}

/** 보이는 첫 대상에 초점을 둔다. 연 곳이 접힌 패널 안이면 다음 후보로 간다. */
function focusFirst(...targets) {
  const visible = (t) => t.getClientRects().length && !t.closest(".drawer:not(.open)");
  const target = targets.find((t) => t?.isConnected && !t.disabled && visible(t));
  target?.focus();
}

function openPanel(panel) {
  const lost = sidebar.contains(document.activeElement);
  if (narrow.matches) for (const other of [sidebar, viewer]) other.classList.remove("open");
  else if (panel === viewer) sidebar.classList.remove("open");
  panel.classList.add("open");
  sync();
  // 서랍이거나, 문서 찾기에서 열어 초점이 접힌 칸에 남으면 뷰어 안으로 옮긴다
  if (narrow.matches || (lost && !isOpen(sidebar))) panel.querySelector(".panel-head button").focus();
}

function closePanel(panel) {
  panel.classList.remove("open");
  sync();
  const back = panel === sidebar ? [] : [viewerOpener];
  focusFirst(...back, $("open-sidebar"), $("input"));
}

$("open-sidebar").addEventListener("click", () => openPanel(sidebar));
$("close-sidebar").addEventListener("click", () => closePanel(sidebar));
$("close-viewer").addEventListener("click", () => closePanel(viewer));
$("scrim").addEventListener("click", () => closePanel(drawer()));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawer()) closePanel(drawer());
});
narrow.addEventListener("change", () => {
  if (narrow.matches) sidebar.classList.remove("open");
  sync();
});
if (narrow.matches) sidebar.classList.remove("open");
sync();

// 문서 뷰어 -----------------------------------------------------------------

/** 새 탭으로 여는 회의록 PDF 링크. 어느 회의인지 이름에 넣는다(점검 UI-12). 화면 안 문서를 여는 "원문에서 보기"와
 *  헷갈리지 않게 "PDF"로 부른다(S41). */
function originalLink(href, meeting) {
  const link = el("a", "muted", "회의록 PDF");
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `${meeting} 회의록 PDF(새 탭)`);
  return link;
}

/** 안건 문자열을 번호(숫자.) 앞에서 나눈 목록으로 넣는다. 번호가 없으면 문단 하나다(점검 UI-7). */
function agendaBlock(text) {
  // 번호로 시작하는 안건만 나눈다. 본문 속 날짜("2020. 1.")에서 나누지 않게 하려는 것이다
  if (!/^\s*\d{1,2}\.(?!\d)/.test(text)) return el("p", "", text);
  const items = text.split(/(?:^|(?<=[\s)]))(?=\d{1,2}\.(?!\d))/).map((s) => s.trim()).filter(Boolean);
  if (items.length < 2) return el("p", "", text);
  const list = el("ul", "agenda");
  for (const item of items) list.append(el("li", "", item));
  return list;
}

async function openDocument(docId, start = -1, end = -1, opener = document.activeElement) {
  const view = $("viewer-body");
  viewerOpener = opener;
  openPanel(viewer);
  $("viewer-original").hidden = true;
  $("viewer-title").textContent = "";
  view.replaceChildren(el("p", "muted", "문서를 불러오고 있습니다."));
  try {
    const doc = await call("document", [docId, start, end]);
    const link = $("viewer-original");
    link.href = doc.original;
    link.setAttribute("aria-label", `${doc.name} 회의록 PDF(새 탭)`);
    link.hidden = false;
    $("viewer-title").textContent = doc.name;
    view.replaceChildren(agendaBlock(doc.agenda), el("hr"));
    fillParagraphs(view, doc.body, (text) => text.startsWith("▼") || text.startsWith("▲"));
    if (start >= 0) {
      const first = [...view.querySelectorAll("strong.mark")].find((s) => s.textContent === CHUNK_START);
      first?.scrollIntoView({ block: "start" });
    } else {
      view.scrollTop = 0;
    }
  } catch {
    view.replaceChildren(el("p", "muted", "문서를 불러오지 못했습니다. 다시 시도해 주세요."));
  }
}

// 문서 찾기 -----------------------------------------------------------------

/** 입력해 거르는 선택 칸. 브라우저 목록(datalist)이라 키보드로 고를 수 있다(점검 UI-1). 이름이 목록의
 *  항목과 같아지면 고른 것으로 본다. */
function picker(input, list, onPick) {
  let byName = new Map();
  input.addEventListener("input", () => {
    if (byName.has(input.value)) onPick(byName.get(input.value));
  });
  return {
    set(items) {
      byName = new Map(items);
      list.replaceChildren(...items.map(([name]) => Object.assign(el("option"), { value: name })));
      input.value = "";
      input.disabled = !items.length;
    },
  };
}

/** 마지막 요청의 응답만 쓰게 한다. Windows의 선택 칸은 화살표를 누를 때마다 change가 나서 목록 요청이
 *  겹치고 응답이 순서를 바꿔 도착한다. 늦게 온 다른 연도의 응답이 목록을 덮고 고르던 값을 지웠다(사용자 확인
 *  2026-11-06, PR #251). turn()은 새 요청을 시작하고, 돌려준 함수는 그 요청이 아직 마지막인지 알려 준다. */
function latestOnly() {
  let last = 0;
  return () => {
    const mine = ++last;
    return () => mine === last;
  };
}

const yearTurn = latestOnly();
const meetingTurn = latestOnly();

const documents = picker($("document"), $("document-options"), (docId) => openDocument(docId, -1, -1, $("document")));
const meetings = picker($("meeting"), $("meeting-options"), async (conference) => {
  const current = meetingTurn();
  findStatus("");
  documents.set([]); // 새 목록이 오기 전에 앞 회의의 문서를 고르지 않게 한다(화면 리뷰)
  loading($("document"), true);
  try {
    const list = await call("documents", [conference]);
    if (!current()) return;
    documents.set(list);
  } catch {
    if (current()) findStatus("문서 목록을 불러오지 못했습니다. 회의를 다시 골라 주세요.");
    return;
  } finally {
    if (current()) loading($("document"), false);
  }
  $("document").focus();
});

function resetSelection() {
  yearTurn();
  meetingTurn();
  loading($("meeting"), false);
  loading($("document"), false);
  $("year").value = "";
  meetings.set([]);
  documents.set([]);
}

// 모든 연도의 회의 목록(S41). API 호출마다 계산과 무관하게 약 3초가 들어, 연결할 때 한 번 받아 둔다
let meetingIndex = null;

async function loadMeetingIndex() {
  meetingIndex ??= await call("meeting_index");
}

async function loadYears() {
  if ($("year").options.length > 1) return; // 다시 연결해도 두 번 넣지 않는다
  const years = await call("years");
  for (const year of years) {
    const option = el("option", "", String(year));
    option.value = year;
    $("year").append(option);
  }
  $("year").disabled = false;
  // 질문 범위는 적재한 연도에서 채운다(점검 UI-6). 글에 연도를 박지 않는다
  if (years.length) {
    $("scope").textContent = `${Math.min(...years)}~${Math.max(...years)}년 국회 회의록에서 찾아 답하고, 답변마다 근거 원문을 붙입니다.`;
  }
}

/** 목록을 불러오는 동안 칸 아래에 안내와 진행 표시를 둔다(S41, 사용자 결정 2026-11-06). 비활성 칸은 금지 표시
 *  대신 진행 커서가 된다. 안내 칸은 늘 있는 role="status"라 글자를 넣고 비우면 화면 낭독기가 알린다(화면 리뷰). */
function loading(input, on) {
  input.closest(".field").classList.toggle("busy", on);
  const status = $(`${input.id}-loading`);
  if (on) status.replaceChildren(el("span", "spinner"), document.createTextNode(status.dataset.text));
  else status.replaceChildren();
}

/** 문서 찾기 패널 안의 안내. 목록 호출이 실패하면 원인과 다음 행동을 적는다(화면 리뷰). */
function findStatus(text) {
  $("find-status").textContent = text;
}

$("year").addEventListener("change", async () => {
  const current = yearTurn();
  meetingTurn(); // 앞 연도의 문서 목록 요청도 버린다
  const year = Number($("year").value);
  documents.set([]);
  meetings.set([]);
  findStatus("");
  loading($("document"), false);
  // 미리 받은 목록이 있으면 요청 없이 바로 켠다(S41). 받기 전에 고르면 아래처럼 그 연도만 요청한다
  const ready = meetingIndex?.[year];
  if (ready) meetings.set(ready);
  loading($("meeting"), Boolean(year) && !ready);
  if (!year || ready) return;
  // 화살표로 연도를 넘기는 동안은 요청하지 않는다. Space가 목록 요청을 하나씩(약 4초) 처리해, 중간 연도마다
  // 요청하면 마지막 목록까지 오래 걸렸다(일곱 번 넘기면 약 20초)
  await new Promise((done) => setTimeout(done, YEAR_SETTLE_MS));
  if (!current()) return;
  try {
    const list = await call("meetings", [year]);
    if (current()) meetings.set(list);
  } catch {
    if (current()) findStatus("회의 목록을 불러오지 못했습니다. 연도를 다시 골라 주세요.");
  } finally {
    if (current()) loading($("meeting"), false);
  }
});

$("reset").addEventListener("click", resetSelection);

updateSend();
connect();
