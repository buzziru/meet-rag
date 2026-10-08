"""서브에이전트 작업자 풀의 작업 목록·큐 기록 (ADR-0024).

작업 하나는 항목(pool_id, qid 등) 몇 개이고, 항목마다 출력 파일 `{out}/{id}{ext}` 하나를 쓴다.
남은 일의 기준은 출력 파일이다. 큐 기록(jsonl)은 사람이 진행을 보는 이력이고, 보류한 항목을
다음 plan에서 빼는 근거다.

    python worker_queue.py plan   --jobs J --out D --ids FILE --size N [--queue Q]
    python worker_queue.py start  --jobs J --out D --queue Q N [N ...]
    python worker_queue.py done   --jobs J --out D --queue Q N [N ...]
    python worker_queue.py hold   --jobs J --out D --queue Q N --hold ID [ID ...]
    python worker_queue.py status --jobs J --out D

start는 작업의 항목 중 출력이 없는 것만 출력한다. 에이전트 프롬프트의 항목 목록은 이 출력을
그대로 붙인다. 손으로 옮기다 항목을 빠뜨린 사례가 있다(G3 작업 274·290).
hold는 작업자가 입력을 끝까지 읽지 못해 건너뛴 항목을 보류로 기록한다. 같은 입력이면 다시
실패하므로 plan이 이 항목을 빼고, 처리는 사용자가 정한다.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


def load_jobs(path: Path) -> dict[int, list[str]]:
    with path.open(encoding="utf-8") as f:
        return {j["job"]: j["ids"] for j in map(json.loads, f)}


def missing(ids: list[str], out: Path, ext: str) -> list[str]:
    return [i for i in ids if not (out / f"{i}{ext}").exists()]


def held(queue: Path | None) -> set[str]:
    if queue is None or not queue.exists():
        return set()
    with queue.open(encoding="utf-8") as f:
        return {i for r in map(json.loads, f) if r["status"] == "held" for i in r["ids"]}


def log(queue: Path, jobs: Path, job: int, status: str, ids: list[str]) -> None:
    # 작업 번호는 작업 목록 파일마다 1부터라 파일 이름을 함께 남긴다
    rec = {"jobs": jobs.name, "job": job, "status": status, "ids": ids,
           "time": datetime.now().astimezone().isoformat(timespec="seconds")}
    with queue.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "start", "done", "hold", "status"])
    ap.add_argument("job", nargs="*", type=int)
    ap.add_argument("--jobs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ext", default=".json")
    ap.add_argument("--queue", type=Path)
    ap.add_argument("--ids", type=Path, help="plan: 항목 id를 한 줄에 하나씩 적은 파일")
    ap.add_argument("--size", type=int, help="plan: 작업 하나의 항목 수")
    ap.add_argument("--hold", nargs="+", default=[], help="hold: 보류할 항목 id")
    a = ap.parse_args()

    if a.cmd == "plan":
        # 같은 이름으로 다시 쓰면 큐 기록에서 이전 작업과 구분되지 않는다
        if a.jobs.exists():
            ap.error(f"{a.jobs}가 이미 있다. 단계·회차마다 새 작업 목록 파일을 쓴다")
        skip = held(a.queue)
        ids = [i for i in missing(a.ids.read_text(encoding="utf-8").split(), a.out, a.ext)
               if i not in skip]
        chunks = [ids[k:k + a.size] for k in range(0, len(ids), a.size)]
        with a.jobs.open("w", encoding="utf-8", newline="\n") as f:
            for n, c in enumerate(chunks, 1):
                f.write(json.dumps({"job": n, "ids": c}, ensure_ascii=False) + "\n")
        print(f"{len(ids)} ids -> {len(chunks)} jobs ({a.jobs}), held {len(skip)}")
        return

    jobs = load_jobs(a.jobs)
    if a.cmd == "status":
        todo = [n for n, ids in jobs.items() if missing(ids, a.out, a.ext)]
        print(f"done {len(jobs) - len(todo)}/{len(jobs)} jobs, next: {todo[:5]}")
        return
    if a.queue is None:
        ap.error(f"{a.cmd}에는 --queue가 필요하다")
    for n in a.job:
        if n not in jobs:
            ap.error(f"작업 {n}이 {a.jobs}에 없다")
        left = missing(jobs[n], a.out, a.ext)
        if a.cmd == "hold":
            log(a.queue, a.jobs, n, "held", a.hold)
            print(f"{n}: held {' '.join(a.hold)}")
        elif a.cmd == "start":
            if not left:
                print(f"{n}: 남은 항목 없음, 띄우지 않는다")
                continue
            log(a.queue, a.jobs, n, "running", left)
            print(f"{n}: {' '.join(left)}")
        else:
            log(a.queue, a.jobs, n, "done" if not left else "partial", left)
            print(f"{n}: {'ok' if not left else 'missing ' + ' '.join(left)}")


if __name__ == "__main__":
    main()
