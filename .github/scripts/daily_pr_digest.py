"""대상 PR을 gh로 모아 Claude(Messages API)에 보내고 일일 종합 이슈를 만든다(ADR-0047, ADR-0081).

종합과 코드 리뷰는 별도 호출이다. 리뷰가 실패해도 종합은 그대로 나간다.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import anthropic

REPO = os.environ["GITHUB_REPOSITORY"]
OWNER = os.environ["OWNER"]
SINCE = os.environ["SINCE"]
DAY = os.environ["DAY"]
PROMPT = Path(".github/prompts/daily-pr-digest.md")
NO_ITEMS = "NO_ITEMS"
REVIEW_PROMPT = Path(".github/prompts/daily-code-review.md")
NO_FINDINGS = "NO_FINDINGS"
REVIEW_HEADING = "## 코드 리뷰"
CODE_DIRS = ("src/", "tests/")
REVIEW_MAX_CHARS = 300_000  # 시험한 날 중 최대 약 27만 자, 약 15만 토큰(ADR-0081)
REVIEW_MAX_TOKENS = 32000


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def by_owner(items: list[dict], key: str) -> list[dict]:
    """외부인 코멘트의 지시가 입력에 섞이지 않게 저장소 소유자가 쓴 것만 남긴다."""
    return [i for i in items if (i.get(key) or {}).get("login") == OWNER]


def collect_pr(number: str) -> dict:
    pr = json.loads(gh(
        "pr", "view", number, "-R", REPO, "--json",
        "number,title,url,state,mergedAt,body,comments,reviews,files",
    ))
    head = {k: pr[k] for k in ("number", "title", "url", "state")}
    # 항목은 기간 안에 병합된 PR에서만 모은다. 열린 PR은 목록에 상태만 둔다
    if pr["state"] != "MERGED" or pr["mergedAt"] < SINCE:
        return head
    pages = json.loads(gh("api", f"repos/{REPO}/pulls/{number}/comments", "--paginate", "--slurp"))
    line_comments = by_owner([c for page in pages for c in page], "user")
    return head | {
        "body": pr["body"],
        "comments": [{"body": c["body"]} for c in by_owner(pr["comments"], "author")],
        "reviews": [
            {"state": r["state"], "body": r["body"]} for r in by_owner(pr["reviews"], "author")
        ],
        "line_comments": [
            {k: c.get(k) for k in ("id", "in_reply_to_id", "path", "line", "body")}
            for c in line_comments
        ],
        "files": [
            {"path": f["path"], "additions": f["additions"], "deletions": f["deletions"]}
            for f in pr["files"]
        ],
    }


def ask(client: anthropic.Anthropic, model: str, content: str):
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=PROMPT.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": content}],
    )
    print(f"stop_reason={response.stop_reason} model={response.model} usage={response.usage}")
    return response


def ask_review(client: anthropic.Anthropic, model: str, content: str):
    # 입력이 길고 사고가 길어질 수 있어 스트리밍으로 받는다
    with client.messages.stream(
        model=model,
        max_tokens=REVIEW_MAX_TOKENS,
        output_config={"effort": "high"},
        system=REVIEW_PROMPT.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()
    print(f"[리뷰] stop={response.stop_reason} model={response.model} usage={response.usage}")
    return response


def ask_with_fallback(client: anthropic.Anthropic, content: str, call=ask):
    """MODEL이 거절하거나 SDK 재시도 뒤에도 API 오류면 FALLBACK_MODEL로 한 번 더 부른다.

    반환: (응답, 실패 사유 또는 None)
    """
    try:
        response = call(client, os.environ["MODEL"], content)
        if response.stop_reason != "refusal":
            return response, None
        failure = "거절"
    except anthropic.APIError as e:
        print(f"{os.environ['MODEL']} 호출 실패: {type(e).__name__}: {e}")
        failure = f"API 오류({type(e).__name__})"
    return call(client, os.environ["FALLBACK_MODEL"], content), failure


def code_diffs(number: int) -> list[dict]:
    """PR diff에서 `src/`, `tests/` 파일만 남긴다."""
    out = []
    for part in re.split(r"(?m)^(?=diff --git )", gh("pr", "diff", str(number), "-R", REPO)):
        m = re.match(r"diff --git a/\S+ b/(\S+)", part)
        if m and m[1].startswith(CODE_DIRS):
            out.append({"pr": number, "path": m[1], "diff": part})
    return out


def numbered(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    return "\n".join(f"{i}\t{line}" for i, line in enumerate(text.splitlines(), 1))


def review_input(prs: list[dict]) -> tuple[dict | None, list[str]]:
    """그날 병합된 PR의 코드 diff와 바뀐 파일 전체. 코드가 없으면 (None, [])

    상한을 넘으면 diff를 파일 전체보다 먼저, 짧은 것부터 넣는다. 뺀 항목은 입력과 이슈에 적는다.
    """
    merged = [p for p in prs if "files" in p]
    diffs = [d for p in merged for d in code_diffs(p["number"])]
    if not diffs:
        return None, []
    paths = {d["path"] for d in diffs if d["path"].endswith(".py") and Path(d["path"]).is_file()}
    files = [{"path": p, "text": numbered(p)} for p in sorted(paths)]

    room, kept, omitted = REVIEW_MAX_CHARS, {"diff": [], "text": []}, []
    for group, field, label in [(diffs, "diff", "diff"), (files, "text", "파일")]:
        for item in sorted(group, key=lambda x: len(x[field])):
            if len(item[field]) <= room:
                room -= len(item[field])
                kept[field].append(item)
            else:
                omitted.append(f"{label} {item['path']}")
    data = {
        "prs": [{"number": p["number"], "title": p["title"]} for p in merged],
        "diffs": kept["diff"],
        "files": kept["text"],
        "omitted": omitted,
    }
    return data, omitted


def code_review_section(client: anthropic.Anthropic, prs: list[dict]) -> str | None:
    """이슈에 넣을 코드 리뷰 절. 지적도 실패도 없으면 None. 리뷰 실패는 절의 문장으로 낸다."""
    try:
        data, omitted = review_input(prs)
        if data is None:
            print("[리뷰] 병합된 코드 변경이 없어 부르지 않는다")
            return None
        content = json.dumps(data, ensure_ascii=False)
        print(f"[리뷰] 입력 {len(content)}자, 뺀 항목 {len(omitted)}개")
        response, failure = ask_with_fallback(client, content, ask_review)
    except (anthropic.APIError, subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"[리뷰] 실패: {type(e).__name__}: {e}")
        return f"{REVIEW_HEADING}\n\n리뷰 실패: `{type(e).__name__}`. 실행 로그를 본다."
    if response.stop_reason != "end_turn":
        return f"{REVIEW_HEADING}\n\n리뷰 중단: `{response.stop_reason}`. 실행 로그를 본다."
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text == NO_FINDINGS:
        return None
    note = f"작성 모델: `{response.model}`"
    if failure:
        note += f" (`{os.environ['MODEL']}`이 {failure}로 실패해 대체 모델로 작성)"
    if omitted:
        note += f". 크기 상한으로 뺀 항목: {', '.join(omitted)}"
    return f"{REVIEW_HEADING}\n\n{text}\n\n{note}"


def main() -> None:
    data = {
        "repository": REPO,
        "date_kst": DAY,
        "since_utc": SINCE,
        "prs": [collect_pr(n) for n in os.environ["PR_NUMBERS"].split()],
        "open_digest_issues": json.loads(gh(
            "issue", "list", "-R", REPO, "--label", "daily-digest", "--state", "open",
            "--json", "number,title,body",
        )),
    }

    client = anthropic.Anthropic()  # ANTHROPIC_FEDERATION_* 환경 변수로 ID federation 인증
    response, failure = ask_with_fallback(client, json.dumps(data, ensure_ascii=False))
    if response.stop_reason != "end_turn":
        raise SystemExit(f"응답이 끝나지 않았다: {response.stop_reason}")
    body = "".join(b.text for b in response.content if b.type == "text").strip()
    section = code_review_section(client, data["prs"])
    if body == NO_ITEMS and section is None:
        print("모을 항목이 없어 이슈를 만들지 않는다")
        return

    gh("label", "create", "daily-digest", "-R", REPO, "--color", "BFD4F2",
       "--description", "PR 일일 종합", "--force")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        note = f"작성 모델: `{response.model}`"
        if failure:
            note += f" (`{os.environ['MODEL']}`이 {failure}로 실패해 대체 모델로 작성)"
        parts = [] if body == NO_ITEMS else [f"{body}\n\n---\n{note}"]
        if section:
            parts.append(section)
        f.write("\n\n".join(parts) + "\n")
    print(gh("issue", "create", "-R", REPO, "--title", f"PR 일일 종합 {DAY}",
             "--label", "daily-digest", "--body-file", f.name))


if __name__ == "__main__":
    main()
