// 정적 채팅 화면(docs/slices/39b-vercel-front.md). 검색과 생성은 Space API가 맡는다.
// 답변과 문서 본문은 글자로만 넣어 HTML이 해석되지 않게 한다.
import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client@2.7.2/dist/index.min.js";

const SPACE = "ingyoun/meet-rag";
const WAIT_MS = 5000; // 첫 토큰이 이 시간 안에 오지 않으면 대기 문구를 보인다
const WAIT_TEXT = "근거를 찾아 답변을 준비하고 있습니다.";
const CONNECTING_TEXT = "서버에 연결하고 있습니다. 잠시만 기다려 주세요.";
const RETRY_MS = 5000;
const CONTEXTS_TITLE = "근거";
const CHUNK_START = "▼ 답변에 쓴 근거";

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
        loadYears();
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

/** 줄바꿈으로 나뉜 글을 문단으로 넣는다. 한 문단 전체가 **굵게**이면 표지로 보인다. */
function fillParagraphs(parent, text, onMark) {
  for (const part of text.split(/\n{2,}/)) {
    const line = part.trim();
    if (!line) continue;
    const bold = line.match(/^\*\*([^*]+)\*\*$/);
    const p = el("p");
    if (bold) {
      p.append(el("strong", onMark?.(bold[1]) ? "mark" : "", bold[1]));
    } else {
      for (const [i, piece] of line.split("**").entries()) {
        p.append(i % 2 ? el("strong", "", piece) : document.createTextNode(piece));
      }
    }
    parent.append(p);
  }
}

// 대화 ---------------------------------------------------------------------

let busy = false;

function renderSources(contexts) {
  const details = el("details", "sources");
  details.append(el("summary", "", `${CONTEXTS_TITLE} ${contexts.length}개`));
  for (const c of contexts) {
    const source = el("div", "source");
    const head = el("div", "source-head");
    const open = el("button", "source-open", `[${c.n}] ${c.date} ${c.committee_name}`);
    open.type = "button";
    open.addEventListener("click", () => openDocument("evidence", c.doc_id, c.start, c.end));
    const link = el("a", "muted", "회의록");
    link.href = c.original;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    head.append(open, link);
    source.append(head);
    fillParagraphs(source, c.body);
    details.append(source);
  }
  return details;
}

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

  // 첫 토큰이 늦으면 답변 밖 표시만 바꾼다. 답변 글에는 넣지 않는다
  const timer = setTimeout(() => {
    status.replaceChildren(el("span", "spinner"), el("span", "", WAIT_TEXT));
  }, WAIT_MS);
  const body = el("div");
  const showText = (text) => {
    clearTimeout(timer);
    status.remove();
    if (!body.isConnected) answer.append(body);
    body.replaceChildren();
    fillParagraphs(body, text);
  };

  try {
    const job = (await connect()).submit("/chat", [message]);
    for await (const event of job) {
      if (event.type === "status" && event.stage === "error") throw new Error(event.message);
      if (event.type !== "data") continue;
      const item = event.data[0];
      showText(item.text);
      // 클라이언트가 마지막 값을 한 번 더 보내므로 근거는 처음 한 번만 붙인다
      if (item.done && !answer.querySelector(".sources")) answer.append(renderSources(item.contexts));
    }
  } catch {
    showText("답변을 만들지 못했습니다. 다시 시도해 주세요.");
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
};

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

// 탭 -----------------------------------------------------------------------

function showTab(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  }
  for (const panel of ["chat", "doc", "evidence"]) {
    $(`panel-${panel}`).hidden = panel !== name;
  }
}

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
}

// 문서 ---------------------------------------------------------------------

async function openDocument(tab, docId, start = -1, end = -1) {
  const view = $(tab === "doc" ? "doc-view" : "evidence-view");
  showTab(tab);
  closeSidebar();
  view.replaceChildren(el("p", "muted", "문서를 불러오고 있습니다."));
  try {
    const doc = await call("document", [docId, start, end]);
    const link = el("a", "", "회의록");
    link.href = doc.original;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const original = el("p");
    original.append(link);
    view.replaceChildren(el("h2", "", doc.name), el("p", "", doc.agenda), original, el("hr"));
    fillParagraphs(view, doc.body, (text) => text.startsWith("▼") || text.startsWith("▲"));
    if (start >= 0) {
      const first = [...view.querySelectorAll("strong.mark")].find((s) => s.textContent === CHUNK_START);
      first?.scrollIntoView({ block: "start" });
    } else {
      view.parentElement.scrollTop = 0;
    }
  } catch {
    view.replaceChildren(el("p", "muted", "문서를 불러오지 못했습니다. 다시 시도해 주세요."));
  }
}

/** 입력해 거르는 선택 칸. 조합 중인 한글도 input 이벤트로 거른다. */
function combobox(input, list, onPick) {
  let items = [];
  const render = () => {
    const query = input.value.trim().toLowerCase();
    const shown = items.filter(([name]) => name.toLowerCase().includes(query));
    list.replaceChildren();
    for (const [name, value] of shown) {
      const li = el("li", "", name);
      li.addEventListener("mousedown", (event) => {
        event.preventDefault(); // 입력칸의 blur가 먼저 목록을 닫지 않게 한다
        input.value = name;
        list.hidden = true;
        onPick(value);
      });
      list.append(li);
    }
    if (!shown.length) list.append(el("li", "empty", "일치하는 항목이 없습니다"));
  };
  input.addEventListener("focus", () => {
    render();
    list.hidden = false;
  });
  input.addEventListener("input", () => {
    render();
    list.hidden = false;
  });
  input.addEventListener("blur", () => {
    list.hidden = true;
  });
  return {
    set(next) {
      items = next;
      input.value = "";
      input.disabled = !next.length;
      list.hidden = true;
    },
  };
}

const documents = combobox($("document"), $("document-list"), (docId) => openDocument("doc", docId));
const meetings = combobox($("meeting"), $("meeting-list"), async (conference) => {
  documents.set(await call("documents", [conference]));
  $("document").focus();
});

function resetSelection() {
  $("year").value = "";
  meetings.set([]);
  documents.set([]);
}

async function loadYears() {
  if ($("year").options.length > 1) return; // 다시 연결해도 두 번 넣지 않는다
  for (const year of await call("years")) {
    const option = el("option", "", String(year));
    option.value = year;
    $("year").append(option);
  }
  $("year").disabled = false;
}

$("year").addEventListener("change", async () => {
  const year = Number($("year").value);
  documents.set([]);
  meetings.set(year ? await call("meetings", [year]) : []);
});

$("reset").addEventListener("click", resetSelection);

// 좁은 화면의 사이드바 -------------------------------------------------------

function closeSidebar() {
  $("sidebar").classList.remove("open");
  $("scrim").hidden = true;
}

$("open-sidebar").addEventListener("click", () => {
  $("sidebar").classList.add("open");
  $("scrim").hidden = false;
});
$("close-sidebar").addEventListener("click", closeSidebar);
$("scrim").addEventListener("click", closeSidebar);

updateSend();
connect();
