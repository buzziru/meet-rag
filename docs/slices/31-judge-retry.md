# S31 judge 실행의 실패 질의 모아 재시도

judge 호출이 재시도까지 실패하면 지금은 시작하지 않은 질의를 취소하고 멈춘다(D-57 결정 2, PR #160). EXP-019 기준 재채점은 330질의에서 시간 초과로 두 번 멈춰 사람이 세 번 실행했다(호출 1,175회 중 응답 없음 16회, 멈춘 두 질의는 서로 달랐다). 전체를 끝까지 돌리고 실패한 질의만 다시 시도하게 바꾼다(사용자 결정 2026-11-02).

## 만드는 것

- `rag.gen_eval.judge.run_all`: 한 질의가 실패해도 나머지를 계속 처리한다. 첫 차례가 끝나면 실패한 질의만 `judge.retry_passes`번까지 다시 처리한다. 저장된 응답이 있는 요청은 다시 부르지 않는다. 빈 응답·잘린 응답은 저장하지 않아(D-42) 다시 부른다
- 그래도 실패한 질의가 남으면 실패 질의와 원인을 모두 적고 결과 파일 없이 멈춘다. 결측을 만들지 않는 D-57 이유(2)를 그대로 지킨다
- 연속 실패가 `judge.stop_after_failures`건에 이르면 시작하지 않은 질의를 취소하고 바로 멈춘다. 서버 장애나 인증 오류, 코드 오류처럼 모든 질의가 실패하는 경우에 300질의가 각각 대기하지 않게 한다
- 값은 `configs/judge/deepseek_go.yaml`에 둔다: `retry_passes: 1`, `stop_after_failures: 8`. `timeout`·`max_retries`처럼 judge 레시피와 캐시 키에 넣지 않는다(D-57 결정 3과 같은 이유). 호출 대기 120초와 SDK 재시도 1회는 바꾸지 않는다
- 사례: 330질의 중 질의 a가 시간 초과로 실패하면 나머지 329질의를 마치고 a만 다시 부른다. 성공하면 결과 파일을 쓴다. 다시 실패하면 "judge 실패 1건, a: APITimeoutError"로 멈추고 결과 파일을 쓰지 않는다. 서버가 응답하지 않아 8건이 연이어 실패하면 그 자리에서 남은 질의를 취소하고 멈춘다
- `docs/DECISIONS.md`에 새 결정(D-64. D-63은 EXP-019 브랜치가 쓴다)을 적고 D-57 결정 2에 `이후 변경` 표시를 붙인다

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | `tests/test_gen_eval.py`의 `run_all` 테스트 | 첫 차례에 실패한 항목만 다시 호출되고 성공한 항목은 다시 호출되지 않는다. 재시도로 성공하면 입력 순서대로 돌려준다 |
| 3 | 같은 파일 | 재시도 뒤에도 실패하면 실패 항목과 원인을 적고 멈춘다 |
| 4 | 같은 파일 | 연속 실패가 상한에 이르면 시작하지 않은 항목을 취소하고 멈춘다. 중간에 성공이 끼면 셈이 처음부터 시작한다 |
| 5 | `tests/test_gen_eval_freeze.py` | 그대로 통과한다(요청 본문·지시 변경 없음) |

유료 호출은 하지 않는다. 합성 함수로만 확인한다.

## 수정 허용 파일

`src/rag/gen_eval/judge.py`(`run_all`과 호출 두 곳), `configs/judge/deepseek_go.yaml`, `configs/judge/deepseek_openrouter.yaml`(같은 키를 두는 대안 경로), `tests/test_gen_eval.py`, `docs/DECISIONS.md`, `docs/slices/31-judge-retry.md`, `CLAUDE.md`(바뀌는 호출법이 있으면), `docs/PLAN.md`·`docs/PLAN-done.md`

## 범위 밖

- 생성의 실패 처리(`rag.gen_eval.generate`). 이미 전체를 돌린 뒤 실패를 모아 멈추고 다시 실행하면 이어 쓴다
- 호출 대기 시간, SDK 재시도 수, 동시 수 변경
- judge 지시·판정표·요청 본문(D-49 동결)
- 질의 안의 단계별 재시도

## 결과 (2026-11-02)

커밋: 구현 0350477

- `uv run pytest -q`, `uv run ruff check .` 통과
- 합성 함수 테스트로 완료 기준 2\~4를 확인했다. 유료 호출은 없다
- slice-verifier: 완료 기준 1\~5 통과. protocol-auditor: 위반 없음
