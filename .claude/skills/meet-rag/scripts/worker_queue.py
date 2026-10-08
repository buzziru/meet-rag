"""서브에이전트 작업자 풀의 작업 목록·큐 기록 (ADR-0024).

작업 하나는 항목(pool_id, qid 등) 몇 개이고, 항목마다 출력 파일 `{out}/{id}{ext}` 하나를 쓴다.
남은 일의 기준은 출력 파일이다. 큐 기록(jsonl)은 사람이 진행을 보는 이력이다.

    python worker_queue.py plan  --jobs J --out D --ids FILE --size N
    python worker_queue.py start --jobs J --out D --queue Q N [N ...]
    python worker_queue.py done  --jobs J --out D --queue Q N [N ...]
    python worker_queue.py status --jobs J --out D

start는 작업의 항목 중 출력이 없는 것만 출력한다. 에이전트 프롬프트의 항목 목록은 이 출력을
그대로 붙인다. 손으로 옮기다 항목을 빠뜨린 사례가 있다(G3 작업 274·290).
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


def log(queue: Path, job: int, status: str, ids: list[str]) -> None:
    rec = {"job": job, "status": status, "ids": ids,
           "time": datetime.now().astimezone().isoformat(timespec="seconds")}
    with queue.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "start", "done", "status"])
    ap.add_argument("job", nargs="*", type=int)
    ap.add_argument("--jobs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ext", default=".json")
    ap.add_argument("--queue", type=Path)
    ap.add_argument("--ids", type=Path, help="plan: 항목 id를 한 줄에 하나씩 적은 파일")
    ap.add_argument("--size", type=int, help="plan: 작업 하나의 항목 수")
    a = ap.parse_args()

    if a.cmd == "plan":
        ids = missing(a.ids.read_text(encoding="utf-8").split(), a.out, a.ext)
        chunks = [ids[k:k + a.size] for k in range(0, len(ids), a.size)]
        with a.jobs.open("w", encoding="utf-8", newline="\n") as f:
            for n, c in enumerate(chunks, 1):
                f.write(json.dumps({"job": n, "ids": c}, ensure_ascii=False) + "\n")
        print(f"{len(ids)} ids -> {len(chunks)} jobs ({a.jobs})")
        return

    jobs = load_jobs(a.jobs)
    if a.cmd == "status":
        todo = [n for n, ids in jobs.items() if missing(ids, a.out, a.ext)]
        print(f"done {len(jobs) - len(todo)}/{len(jobs)} jobs, next: {todo[:5]}")
        return
    for n in a.job:
        left = missing(jobs[n], a.out, a.ext)
        if a.cmd == "start":
            log(a.queue, n, "running", left)
            print(f"{n}: {' '.join(left)}")
        else:
            log(a.queue, n, "done" if not left else "partial", left)
            print(f"{n}: {'ok' if not left else 'missing ' + ' '.join(left)}")


if __name__ == "__main__":
    main()
