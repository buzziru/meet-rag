"""G3 검수용으로 multi-doc 통과 질의(queries.jsonl) 표본을 뽑아 md로 쓴다 (PLAN G3).

문서는 검사 입력(check_in)과 같은 번호(D1부터, pool_doc_ids 순서)로 적는다. 원문은 검사 입력
파일에서 같은 번호로 찾는다. 검수 칸은 비워 두고 사람이 채운다.

--scope는 표본 검수에서 나온 범위 재판정 대상(g3_scope)을 표본 밖에서 골라, 질의와 정답 문서
회의의 안건만 보여 주는 재판정 파일을 쓴다(notebooks/08_04_G3검수.ipynb).

    uv run python -m rag.multidoc.review [--scope]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from hydra import compose, initialize_config_dir

from rag.sample_review import sample_qids

ROOT = Path(__file__).resolve().parents[3]

HEADER = """# G3 multi-doc 질의 검수

동결 대상 `queries.jsonl` {total}건에서 무작위로 뽑은 {n}건(seed {seed})이다. 유형별: {types}.

평가에 쓰는 것은 질의와 정답 문서다. 기대 답과 요소·근거는 판정 근거를 보이는 참고 자료다.
원문은 건마다 적은 검사 입력 파일에서 같은 D 번호(`[n]`)로 찾는다.

검수 칸

- 판정: `통과`(질의와 정답 문서를 그대로 평가에 써도 됨), `불량`
- 불량 유형(불량일 때, 여럿 가능)
  - `정답 누락`: 답에 필요한 문서가 정답에 없음
  - `정답 과잉`: 정답에 답과 무관하거나 없어도 되는 문서가 있음
  - `단일 문서`: 문서 하나로 답할 수 있음
  - `답 불가`: 원문으로 답할 수 없거나 원문에 없는 내용을 물음
  - `질의 모호`: 답의 범위가 정해지지 않음
  - `기타`
- 정답 문서(판정과 다를 때): 맞다고 보는 D 번호
- 메모: 근거·요소 문제(요소 누락, 무관한 근거) 등
"""

REVIEW = """**검수**

- 판정:
- 불량 유형:
- 정답 문서:
- 메모:
"""


def doc_heads(check_in: str) -> dict[int, str]:
    """검사 입력 본문에서 문서 번호별 머리 줄(회의 정보)."""
    return {int(m[1]): m[2] for m in re.finditer(r"^\[(\d+)\] (.*)$", check_in, re.M)}


def render(q: dict, heads: dict[int, str], check_in_path: str) -> str:
    num = {d: i for i, d in enumerate(q["pool_doc_ids"], 1)}
    lines = [
        f"## {q['qid']}",
        "",
        f"- 유형: {q['type']}, 질의 형태: {q['query_form']}, 후보 문서 {len(num)}개",
        f"- 원문: `{check_in_path}`",
        "",
        f"**질의**: {q['query']}",
        "",
        "**정답 문서**",
        "",
    ]
    lines += [f"- D{num[d]}: {heads.get(num[d], '')}" for d in q["gold_doc_ids"]]
    lines += ["", f"**기대 답**: {q['answer']}", "", "**요소와 근거**", ""]
    for i, el in enumerate(q["elements"], 1):
        lines.append(f"{i}. {el['fact']}")
        lines += [f"   - D{num[s['doc_id']]}: {s['quote']}" for s in el["support"]]
    return "\n".join(lines) + "\n\n" + REVIEW


SCOPE_HEADER = """# G3 범위 재판정: law 회의별 쟁점형 질의

`queries.jsonl`의 {type} 질의 중 '{must}'와 '{any}'가 함께 나오는 {total}건에서
표본 검수한 {reviewed}건을 뺀 {n}건이다. 정답 문서 회의의 안건(발의자 목록은 뺌)을 함께 적는다.

- 판정
  - `통과`: 법안 하나나 주제로 답의 범위가 정해짐
  - `모호`: 회의 주제가 여럿인데 범위를 정하지 않음
- 모호로 판정한 질의는 세트에서 뺀다(사용자 결정 2026-10-08)
"""


def agenda_items(agenda: str) -> list[str]:
    """안건 문자열을 항목으로 나누고 발의자 괄호를 뺀다."""
    agenda = re.sub(r"\([^()]*발의\)", "", agenda)
    return [a.strip() for a in re.split(r"(?=(?<!\d)\d+\. )", agenda) if a.strip()]


def scope_target(query: str, must: str, any_: str) -> bool:
    return must in query and bool(re.search(any_, query))


def render_scope(q: dict, meta: dict[str, dict]) -> str:
    lines = [f"## {q['qid']}", "", f"**질의**: {q['query']}", ""]
    for d in sorted(q["gold_doc_ids"], key=lambda d: meta[d]["date"]):
        m = meta[d]
        meeting = " ".join(m[k] for k in ("date", "committee_name", "meeting_number",
                                             "session_number"))
        lines.append(f"- {meeting}")
        lines += [f"  - {a}" for a in agenda_items(m["agenda"])]
    return "\n".join(lines) + "\n\n- 판정:\n"


def scope_main(cfg, queries: dict[str, dict]) -> None:
    s, paths = cfg.g3_scope, cfg.paths
    reviewed = set(sample_qids(list(queries), cfg.seed, cfg.g3_sample_size))
    hit = [q for q in queries.values()
           if q["type"] == s.type and scope_target(q["query"], s.must, s.any)]
    todo = sorted((q for q in hit if q["qid"] not in reviewed), key=lambda q: q["qid"])
    gold = {d for q in todo for d in q["gold_doc_ids"]}
    meta = {}
    with (ROOT / paths.corpus).open(encoding="utf-8") as f:
        for d in map(json.loads, f):
            if d["doc_id"] in gold:
                meta[d["doc_id"]] = d
    head = SCOPE_HEADER.format(type=s.type, must=s.must, any=s.any, total=len(hit),
                               reviewed=len(hit) - len(todo), n=len(todo))
    out = ROOT / paths.multidoc_scope_review
    out.write_text("\n".join([head] + [render_scope(q, meta) for q in todo]),
                   encoding="utf-8", newline="\n")
    print(f"{len(todo)} queries -> {paths.multidoc_scope_review} (target {len(hit)})")


def main() -> None:
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="config")
    paths = cfg.paths
    with (ROOT / paths.multidoc_queries).open(encoding="utf-8") as f:
        queries = {q["qid"]: q for q in map(json.loads, f)}
    if "--scope" in sys.argv[1:]:
        scope_main(cfg, queries)
        return
    picked = [queries[qid] for qid in sample_qids(list(queries), cfg.seed, cfg.g3_sample_size)]

    types = Counter(q["type"] for q in picked)
    parts = [HEADER.format(total=len(queries), n=len(picked), seed=cfg.seed,
                           types=", ".join(f"{t} {types[t]}" for t in sorted(types)))]
    for q in picked:
        rel = f"{paths.multidoc_check_in}/{q['pool_id']}.md"
        heads = doc_heads((ROOT / rel).read_text(encoding="utf-8"))
        parts.append(render(q, heads, rel))

    out = ROOT / paths.multidoc_review
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"{len(picked)} queries -> {paths.multidoc_review}")
    print(dict(sorted(types.items())))


if __name__ == "__main__":
    main()
