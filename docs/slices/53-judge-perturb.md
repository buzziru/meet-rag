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
