"""대상 PR을 gh로 모아 Claude(Messages API)에 한 번 보내고 일일 종합 이슈를 만든다(ADR-0047)."""

import json
import os
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


def ask_with_fallback(client: anthropic.Anthropic, content: str):
    """MODEL이 거절하거나 SDK 재시도 뒤에도 API 오류면 FALLBACK_MODEL로 한 번 더 부른다.

    반환: (응답, 실패 사유 또는 None)
    """
    try:
        response = ask(client, os.environ["MODEL"], content)
        if response.stop_reason != "refusal":
            return response, None
        failure = "거절"
    except anthropic.APIError as e:
        print(f"{os.environ['MODEL']} 호출 실패: {type(e).__name__}: {e}")
        failure = f"API 오류({type(e).__name__})"
    return ask(client, os.environ["FALLBACK_MODEL"], content), failure


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
    if body == NO_ITEMS:
        print("모을 항목이 없어 이슈를 만들지 않는다")
        return

    gh("label", "create", "daily-digest", "-R", REPO, "--color", "BFD4F2",
       "--description", "PR 일일 종합", "--force")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        note = f"작성 모델: `{response.model}`"
        if failure:
            note += f" (`{os.environ['MODEL']}`이 {failure}로 실패해 대체 모델로 작성)"
        f.write(f"{body}\n\n---\n{note}\n")
    print(gh("issue", "create", "-R", REPO, "--title", f"PR 일일 종합 {DAY}",
             "--label", "daily-digest", "--body-file", f.name))


if __name__ == "__main__":
    main()
