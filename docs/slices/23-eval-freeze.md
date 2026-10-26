# S23 생성 평가 모듈 동결

생성 평가 judge의 지시와 집계 규칙을 기록하고 고정한다(PLAN "평가 모듈 동결", 기준 문서 P1·P2). 동결 뒤에는 정답과 비교하며 지시를 고치지 않는다. 고쳐야 하면 새 버전을 만들고 검증을 다시 한다. j_v8을 동결 전 마지막 지시로 확정했고(PR #145 리뷰, 2026-10-26), 판단 모델은 쓰지 않기로 했다(D-48).

동결은 두 번으로 나뉜다(PLAN). 이 조각은 지시와 집계(판정 규칙)를 고정한다. 사고 과정 설정·다수결 같은 실행 설정은 다음 항목(반복 재채점과 변동 폭 측정)에서 일관성 수치로 고른 뒤 고정한다. 그때까지 실행 설정은 지금 값(`deepseek_go_mixed`)을 기록만 하고 바꿀 수 있게 둔다.

## 만드는 것

### (a) 동결 기록 (`docs/DECISIONS.md` D-49)

기준 문서 P2가 정한 항목을 남긴다. 값은 지시서 작성 때 확인한 것이고, 구현 때 다시 확인해 적는다.

| 항목 | 값 |
| --- | --- |
| judge 모델·경로 | `deepseek-v4.1-flash`, opencode Go(`https://opencode.ai/inference/go/openai/v1`). API 모델이라 가중치 버전을 고정할 수 없어 이름과 제공자를 남긴다(D-46) |
| 지시 | `configs/judge/prompt/j_v8.yaml`, 해시(`judge_recipe`의 `prompt_sha256`) `fc8b5603…`(전체 값은 구현 때 기록) |
| 단계별 사고 과정 | `deepseek_go_mixed`: 기본 끔, `verdicts`·`key_statements`·`items`만 low. 실행 설정이라 다음 항목에서 다시 정한다 |
| temperature | 0.0 |
| `max_tokens` | 16384. 사고 과정을 high 이상으로 켰을 때 정한 값이라 실행 설정으로 보고, 변동 폭 측정 결과를 보고 바꿀 수 있다(결정 사항 2) |
| 집계 코드 | `src/rag/gen_eval/report.py`·`checks.py`, S22 병합 커밋 8eb1284 |
| 판정표(I8) | `src/rag/gen_eval/checks.py`의 `OUTCOMES`·`item_outcome` |
| 캐시 키 | 요청 본문(model, messages, params, extra_body) sha256. 반복 재채점은 다음 항목에서 반복 번호를 키에 더하되, 반복 0은 지금 키와 같게 둔다 |
| 판정용 세트 제외 | `configs/gen_eval/dev_queries.yaml`(D-47 결정 5) |

### (b) 동결 점검 테스트 (`tests/test_gen_eval_freeze.py`)

동결 지시의 해시와 판정표를 테스트로 고정한다. j_v8 파일이나 `OUTCOMES`를 고치면 테스트가 실패해, 바꾸려면 새 버전 파일을 만들고 이 기록을 함께 고쳐야 한다(D-46의 `tests/test_revisions.py`와 같은 방식).

- 기본 설정의 judge 지시 버전이 `j_v8`이고, `prompt_sha256`이 D-49에 적은 값과 같다
- `OUTCOMES`가 D-49 판정표와 같다(12쌍)
- 기대값은 테스트 파일에 상수로 두고 D-49와 같은 값이다

### (c) 보호 범위 (결정 사항 1)

결정 사항 1에서 정한다. (a)로 정해져(2026-10-26) 테스트로만 지키고 CLAUDE.md 보호 경로에는 넣지 않는다.

## 결정 사항

1. **동결한 지시를 보호 경로로 둘지.** 보호 경로는 CLAUDE.md 금지 절에 적고, 바꾸려면 사용자 승인과 DECISIONS 기록이 필요하다. protocol-auditor가 PR마다 점검한다
   - (a) 테스트만 둔다(위 (b)): 예: 누가 j_v8 문구 한 글자를 고치면 `uv run pytest`가 실패해 PR 병합 조건(테스트 통과)에서 멈춘다. 새 지시는 `j_v9.yaml`을 만들고 테스트의 기대값과 D-49를 함께 고쳐야 통과한다. CLAUDE.md와 하네스는 바꾸지 않는다
   - (b) 테스트 + 보호 경로: `configs/judge/prompt/j_v8.yaml`과 `src/rag/gen_eval/checks.py`를 CLAUDE.md 금지 절에 더한다. 테스트 기대값을 고쳐 통과시키는 것도 승인 없이는 막는다. protocol-guard의 P3 목록이 CLAUDE.md와 같은 목록이라 하네스도 고쳐야 하고, 하네스 수정은 F 흐름(ADR)으로 별도 PR이다. `src/rag/gen_eval/judge.py`는 다음 항목(캐시 키 반복 번호)에서 고쳐야 해 넣지 않는다
   - (c) 기록만 남긴다(D-49): 장치가 없어 지시 파일을 고쳐도 알아채는 것은 레시피 해시 대조(생성 기록·judge 기록)뿐이다
   - 추천은 (a)다. 바꾸려면 새 버전 파일과 테스트 기대값을 함께 고쳐야 하므로 조용히 바뀌지 않는다. (b)는 같은 효과에 승인 절차와 하네스 PR이 더 붙는다. 다만 테스트 기대값을 같이 고치면 통과하므로, PR 리뷰에서 테스트 파일 변경을 보는 것에 기댄다
2. **실행 설정(사고 과정)을 이번에 함께 고정할지.**
   - (a) 고정하지 않는다: PLAN대로 변동 폭 측정에서 사고 과정 끔·low를 반복해 일관성으로 고른 뒤 고정한다. 그 사이 judge 결과 파일 이름(`judge.name`)이 설정을 구분한다
   - (b) 지금 값으로 고정한다: 변동 폭 측정에서 설정을 비교할 수 없게 된다
   - 추천은 (a)다(PLAN 결정 2026-10-22)

결정: 1 (a), 2 (a)(사용자 결정 2026-10-26). `max_tokens`(16384)도 사고 과정을 high 이상으로 켰을 때 정한 값이라 실행 설정으로 보고, 변동 폭 측정 결과를 보고 바꿀 수 있다(같은 결정).

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. `tests/test_gen_eval_freeze.py`가 통과하고, j_v8 파일 한 글자나 `OUTCOMES` 한 쌍을 바꾸면 실패한다(임시로 바꿔 확인한 뒤 되돌린다)
3. D-49의 해시가 `judge_recipe`가 계산하는 `prompt_sha256`과 같다
4. 외부 API와 test 분할은 쓰지 않는다

## 수정 허용 파일

- `tests/test_gen_eval_freeze.py`(새 파일)
- `docs/DECISIONS.md`(D-49), `docs/gen-eval-criteria.md`(P2 점검할 곳에 D-49), `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/slices/23-eval-freeze.md`
- 결정 사항 1이 (b)면 `CLAUDE.md` 금지 절. 하네스(protocol-guard P3)는 별도 F 흐름 PR

## 범위 밖

- 실행 설정 고정, 반복 재채점 코드와 변동 폭 측정: PLAN 다음 항목
- judge 지시·코드 변경
- 블라인드 확인 일치 기준값: 블라인드 확인 전에 정한다

## 결과 (2026-10-26)

- 테스트 `tests/test_gen_eval_freeze.py` 2개: 기본 설정의 지시 버전·`prompt_sha256`, `OUTCOMES` 12쌍. `uv run pytest -q`(296개)·`uv run ruff check .` 통과
- 완료 기준 2: `j_v8.yaml` `statements` 지시에 공백 한 칸을 더하면 해시 테스트가, `OUTCOMES`의 ("없음", "다루지 않음")을 "누락"으로 바꾸면 판정표 테스트가 실패했다(각 1 failed). 두 파일은 `git checkout`으로 되돌렸고 테스트는 다시 통과한다
- 완료 기준 3: D-49와 테스트의 해시 `fc8b5603…4de8`은 `judge_recipe`와 같은 계산(`sha(OmegaConf.to_container(prompt))`)으로 얻은 값이고, S22 재채점 기록의 레시피 `prompt_sha256`과 같다
- 외부 API와 test 분할은 쓰지 않았다
- 리뷰 가이드 지적 반영: D-49는 판정표에 `item_outcome`(모호·회피 규칙)을 넣었는데 테스트는 `OUTCOMES` 12쌍만 봤다. 테스트를 판정표 전체(5 상태 × 5 처리)로 넓혔고, 모호·회피에서 "부분임을 밝히고 답함"을 상황 전달로 바꾸면 실패한다(되돌림). `report.py`는 커밋만 기록하고 동결 테스트로 막지 않는다고 D-49에 적었다
- 관찰: D-48(판단 모델 미채택, PR #147)이 아직 병합되지 않아 이 브랜치의 DECISIONS에는 D-48이 없다. 둘 다 DECISIONS 끝에 항목을 더하므로, 먼저 병합된 쪽 뒤에 다른 쪽을 맞춘다
