# S19 조건 목록 결합 설정의 잘못된 조합을 시작할 때 막기

코드 리뷰 2026-10(`docs/reviews/2026-10-code-review.md`) 낮음 B-8 중 잘못된 조합의 오류만 고친다(사용자 선택 2026-10-21, 안 (a)). 검색 순위는 바뀌지 않아야 한다.

| 리뷰 ID | 위치 | 고치는 것 |
| --- | --- | --- |
| B-8 일부 | `src/rag/retrieve.py:379-383` | `conditions.fuse: false`와 `fusion.method: rrf` 조합이 첫 질의에서 `KeyError: 'cc'`로 끝난다. `Retriever`를 만들 때 이 조합이면 이유를 적고 멈춘다 |

## 만드는 것

- `conditions.fuse: false`(EXP-016)는 조건 목록을 결합에 넣지 않고 최다 일치 문서를 결합 목록 `named["cc"]` 뒤에 붙인다. `cc` 목록은 점수 결합(`fusion.method: score`, EXP-015)일 때만 있다
- `Retriever.__init__` 앞부분, 인덱스를 읽기 전에 본다: hybrid이고 조건 목록을 쓰며(`conditions.enabled`) `conditions.fuse`가 false인데 `fusion.method`가 `score`가 아니면 "conditions.fuse=false는 fusion.method=score에서만 쓴다(EXP-016)"로 멈춘다
- 예: `rag.search +exp=exp014 +retriever.conditions.fuse=false` → 지금은 첫 질의에서 `KeyError: 'cc'`. 고친 뒤에는 인덱스를 읽기 전에 멈춘다
- 테스트: 이 조합이면 멈춤, `configs/exp/exp016.yaml`(점수 결합 + `fuse: false`)은 지금처럼 만들어짐. 합성 인덱스로 한다

## 하지 않는 것

- B-8의 나머지(분기마다 EXP 주석, 기각 분기를 작은 함수로 떼기): 결과를 바꾸지 않는 정리이지만 기각·보류 실험(EXP-007·013·015·016)의 재현 경로를 건드려 확인 비용이 커서 하지 않는다(사용자 선택)
- 분기를 지우지 않는다. 기각·보류 실험도 config로 재현할 수 있게 남겨, 새 변수가 생겼을 때 다시 검토하고 같은 실패를 반복하지 않게 한다(`.claude/rules/git.md` 브랜치 절)

## 결정 사항

없음.

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. 멈춤: 위 예의 조합이 인덱스를 읽기 전에 멈춘다(테스트로 확인)
3. 기존 exp 17개 조합 테스트(`tests/test_exp_configs.py`)가 그대로 통과한다. 이 조합을 쓰는 exp가 없으므로 검색 순위 파일 재실행은 하지 않는다

## 수정 허용 파일

- `src/rag/retrieve.py`
- `tests/test_fusion.py`
- `docs/slices/19-cond-fuse-guard.md`, `docs/PLAN.md`, `docs/reviews/2026-10-code-review.md`(진행 표시)

## 범위 밖

- B-8 나머지와 다른 낮음 항목(B-9, B-10, B-11 등)

## 결과 (2026-10-21)

- 구현 커밋 cfc3469. 테스트 251 → 252개, `uv run pytest -q`·`uv run ruff check .` 통과(exp 17개 조합 포함, EXP-016 설정은 그대로 만들어짐)
- 멈춤: `uv run python -m rag.search +exp=exp014 +retriever.conditions.fuse=false index.scope=dev-small` → "conditions.fuse=false는 fusion.method=score에서만 쓴다(EXP-016)"(인덱스를 읽기 전)
