# S53 judge 변형 시험

직접 만든 생성 평가기(judge)가 알려진 유형의 오류를 잡는지 본다. 답변을 일부러 망가뜨리고 같은 judge로 다시 채점해 점수가 그만큼 나빠지는지 잰다(원칙 문서 SPEC 원칙의 평가기 멈춤 기준 3번). 회고에서 judge 정확도를 검증하지 않은 것을 성과 주장의 약점으로 꼽았고, 사람 평가는 평가자가 한 명이라 근거가 되지 않아 남는 수단으로 사용자가 골랐다(사용자 2026-11-06, `docs/retrospective/project-rag.md` 11절). 결과는 회고의 성과 주장 범위에 반영한다. 평가 프로토콜, 기준 설정, judge 지시와 설정은 바꾸지 않는다.

## 만드는 것

- `src/rag/gen_eval/perturb.py`(새 모듈): `+exp=current`의 gen-full 생성 기록과 그 judge 기록을 읽어, 표본 답변을 세 가지로 망가뜨린 사본을 만들고 기존 `judge_record`로 채점한다. judge 코드는 고치지 않는다
  - `unsupported`: 답변 끝에 근거에 없는 사실 문장 하나를 근거 번호와 함께 붙인다. 기대: 충실성이 떨어진다
  - `speaker_swap`: 답변에 나온 답변자 이름을 같은 근거의 질의자 이름으로 바꾼다. 기대: 발언자 불일치 비율이 오른다
  - `off_topic`: 답변을 표본 안 다른 질의의 답변으로 바꾼다. 기대: 답변 관련성이 떨어진다
- 표본: 기준 judge 기록에서 충실성이 계산된(전체 거부가 아닌) 질의 중 seed로 n개. `speaker_swap`은 답변에 근거 머리 줄의 답변자 이름이 나오고 같은 근거에 다른 질의자 이름이 있는 질의만 쓴다
- 출력: 변형별 채점 기록과 요약(변형마다 표본 수, 기준과 변형의 평균, 기대 방향으로 나빠진 비율). 다시 만들면 값이 달라지는 judge 출력이라 시작할 때 `refuse_existing`으로 멈춘다(`src/CLAUDE.md`)
- config: `gen_eval.perturb`(n, seed, 변형 목록, 붙일 문장)와 출력 경로 `paths.gen_perturb`

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .` 통과
- 합성 입력 테스트(`main`을 지나 결과를 단언한다, `tests/CLAUDE.md`)
  - 세 변형 함수가 같은 입력에 같은 결과를 내고, 원래 답변을 바꾸지 않는다
  - 요약이 기대 방향으로 나빠진 비율을 맞게 센다(가짜 judge로 나빠진 것과 안 나빠진 것을 섞은 입력)
  - 출력 파일이 있으면 judge를 부르기 전에 멈춘다
  - test 분할로는 돌지 않는다(`gen_eval.queries`가 dev-full이 아니면 멈춘다)
- 망가뜨린 사본 확인: 요약의 비교 방향을 뒤집은 사본에서 테스트가 실패한다
- 실행: `LANGSMITH_TRACING=false doppler run -- uv run python -m rag.gen_eval.perturb +exp=current`로 gen-full 표본을 한 번 채점하고 요약을 결과 절에 적는다

## 수정 허용 파일

- `src/rag/gen_eval/perturb.py`(새 파일), `tests/test_gen_eval_perturb.py`(새 파일)
- `configs/config.yaml`의 `gen_eval.perturb`와 `paths.gen_perturb`
- `docs/slices/53-judge-perturb.md`, `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/retrospective/project-rag.md`, `docs/retrospective/harness-and-operations.md`, `CLAUDE.md` 명령 절(호출법 한 줄)

## 범위 밖

- `src/rag/gen_eval/judge.py`, `compare.py`, `report.py`, `checks.py`와 judge 지시·설정(동결 대상)
- 기준 설정, 평가 프로토콜, SPEC 판정 규칙. 결과로 judge를 고치지 않는다(D-82)
- test 분할. 생성 test는 S46에서 마쳤다(D-90)
- 사람 일치도(평가자 한 명, 사용자 결정 2026-11-06), 외부 벤치마크

## 결정 사항

- 실행과 비용은 사용자가 미리 승인했다(2026-11-06 "부재 중 지시서 확인 및 비용 승인을 할 수 없어서 미리 승인"). judge는 opencode Go 구독 한도에서 차감되고 허용 처리처의 judge 용도다(D-38)
- 표본 n은 50, 변형 셋. judge 호출은 변형된 답변마다 새로 부르는 단계(항목 평가, 충실성 두 단계, 관련성, 포함도)만이고 핵심 진술·근거 청크 판정은 질의가 같아 저장된 응답을 쓴다. 약 150답변 × 5호출 = 약 750호출, 동시 8로 약 10\~20분 [추론]

## 노트북과 결정의 순서

결정을 내리는 조각이 아니다. 결과는 회고의 성과 주장 범위에 사실로 적는다. 결과로 judge나 기준을 바꾸지 않는다.

## 결과 (2026-11-06)

커밋: 구현 5f4fafd, 감사 반영 cb70640

실행: `PYTHONUTF8=1 LANGSMITH_TRACING=false doppler run -- uv run python -m rag.gen_eval.perturb +exp=current`(gen-full, judge j_v13). judge API 호출 723회(모두 200), 저장된 응답 415회. 출력 `paths.gen_perturb`와 같은 이름의 `.summary.json`

| 변형 | 본 지표 | 표본 | 채점 | 기준 평균 → 변형 평균 | 나빠짐 / 같음 / 나아짐 |
| --- | --- | ---: | ---: | --- | --- |
| unsupported | 충실성 | 50 | 49 | 1.000 → 0.686 | 49 / 0 / 0 |
| speaker_swap | 발언자 불일치 비율 | 50 | 50 | 0.007 → 0.753 | 50 / 0 / 0 |
| off_topic | 답변 관련성 | 50 | 50 | 0.91 → 0.00 | 50 / 0 / 0 |

- 세 유형 모두 놓친 것이 없다. 표본 50이라 검출률 95% 구간(Wilson) 하한은 약 93%다
- 충실성은 근거 없는 진술 하나로 평균 0.31 떨어졌다. 같은 설정 재실행 반폭(0.031, D-53)의 약 10배다
- unsupported에서 채점되지 않은 1건은 judge가 `verdicts` 형식을 재요청 뒤에도 맞추지 못한 경우다(`verdicts 형식 오류`). 오류를 놓친 것이 아니다
- 표본 대상: 충실성·관련성이 계산된 기준 질의 321개, 그중 speaker_swap이 가능한 질의 216개
- 보여 주지 못한 것: 변형이 일부러 뚜렷하다. 미묘한 오류(숫자 하나, 부정 뒤집기, 근거 일부만 옮기기)의 검출률과 맞는 답을 깎는 비율은 모른다. 해석과 성과 주장 범위는 `docs/retrospective/project-rag.md` 3.4·11절(PR #248)

검증

- `uv run pytest -q` 585 passed(감사 반영 뒤 새 테스트 8개 포함), `uv run ruff check .` 통과
- `slice-verifier`: 실행 항목 외 완료 기준 통과. 망가뜨린 사본(비교 방향 부호를 뒤집는 pytest 플러그인)에서 요약 테스트가 실패했다
- `protocol-auditor`: 위반 없음. 보고 둘(요약 파일을 시작할 때 보지 않음, n이 대상보다 크거나 1이면 표본이 조용히 줄거나 off_topic이 자기 답변을 넣음)을 cb70640에서 고쳤다

### 실행 중 있었던 일

첫 실행 명령을 `doppler run -- env PYTHONUTF8=1 LANGSMITH_TRACING=false uv run …`으로 써서 전역 거부 규칙 `doppler run -- env:*`(비밀 값 출력 방지)에 세 번 걸렸다. 메인이 원인을 확인하지 않고 판정기 탓으로 추론해 사용자에게 권한 완화를 권했고, 사용자 지적으로 설정을 확인해 원인을 찾았다. 환경 변수를 `doppler` 앞에 두는 CLAUDE.md 형태로 실행했다. 경위는 `docs/retrospective/harness-and-operations.md` "Claude가 저지른 큰 실수 두 가지"(PR #248)
