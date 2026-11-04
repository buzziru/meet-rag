# S32 잘못 귀속 안전 조건과 judge 지시 j_v13

잘못 귀속은 사실 관계가 틀린 답변이라 치명적인데 종합 지표 평균에 묻힌다(D-67). 생성 판정에 발언자 불일치 비율의 안전 조건을 더하고, 충돌하는 관련성 규칙을 고친다. 규칙 문장은 `docs/SPEC.md` "생성 단계 평가 > 판정"과 D-68이다.

## 만드는 것

- `rag.gen_eval.report.per_query`: 질의 단위 값에 `speaker_mismatch`를 더한다. 이유 첫머리가 "발언자 불일치"인 진술 수 / 진술 수이고, 진술이 없거나 충실성을 계산하지 않은 질의는 NaN이다. report 기준 표에 값과 진술·질의 수를 낸다. report와 compare가 같은 함수를 쓴다(리뷰 G2-6) 이후 변경: 이슈 #201 처리 PR부터 report는 j_v9 이전 지시의 결과에 불일치 비율을 내지 않고 해당 없음으로 적는다
- `rag.gen_eval.compare`: `METRICS`에 더하고, `gen_verdict`에서 차이의 95% 구간 상한이 `spec.speaker_mismatch_max`를 넘으면 안전 조건 실패로 낸다. 짝지은 값이 0개이면 지금처럼 멈춘다(리뷰 G2-1)
- 입력 전제: 발언자 판정이 없는 지시(j_v9 이전 `verdicts`)로 채점한 결과를 비교하면 값이 0으로 조용히 통과하므로, 지시 버전을 보고 멈춘다. 사례: j_v8 결과끼리 compare → 원인을 적고 멈춘다. 기존 EXP-019·EXP-020을 다시 판정하려면 결과 파일 비교 자체는 j_v10 이후 되지만, 판정을 바꾸지 않는다(결정 사항 2)
- `configs/eval/gen_v1.yaml`: `speaker_mismatch_max: 0.02`(보호 경로, 초안 승인으로 받음)
- `configs/judge/prompt/j_v13.yaml`: j_v12에서 `relevance` 규칙 2·3 두 문장. 동결 테스트에 해시, "relevance만 다름" 테스트
- `configs/exp/exp019_j13.yaml`(새 파일): `exp019`를 직접 상속하고 지시 파일을 j_v13으로 합친다. EXP-019 생성 기록을 j_v13으로 채점한다. `tests/test_exp_configs.py`가 DECISIONS 머리 줄에서 별칭 대상 이름을 찾으므로 머리 줄에 `EXP-019_j13`로 적는다. 별칭 `current`와 DECISIONS 머리 줄을 그쪽으로 옮긴다
- 문서: 초안을 SPEC·기준 문서로 옮기고 D-68, 앞 결정 표시. `exp-judgment` 스킬과 `exp-judge`가 새 조건을 보고하게 고친다(ADR은 0082 이후, 0080\~0081은 하위 세션이 쓴다)
- 기준선 재채점(`relevance`만 새로 부름, 약 300회, 어림 $0.3, 약 10분, 사용자 승인 2026-11-03): j_v12 결과와 같은 생성 기록으로 비교해 재검증한다(D-65)

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | `tests/test_gen_eval.py`의 compare 진입점 테스트 | 불일치 비율 상한이 0.02를 넘는 합성 기록에서 `compare.main`이 안전 조건 실패를 낸다. 넘지 않으면 이 조건으로 걸리지 않는다. 비교 코드를 망가뜨린 사본(조건 제거, 부호 뒤집기)에서 실패한다 |
| 3 | `tests/test_gen_eval_freeze.py`, `tests/test_speakers.py` | j_v13 해시가 고정되고 `relevance`만 다르다. 기존 기대값은 그대로다 |
| 4 | `rag.gen_eval.report +exp=<기준 config>` | 불일치 비율이 나오고 `notebooks/42_01_잘못귀속_안전조건.ipynb`의 값과 같다 |
| 5 | 기준선 재채점 뒤 j_v12와 비교 | 관련성 차이가 D-50 어림 반폭 안인지 보고, 바뀐 질의를 사례 대조한다. 위원 말만 전한 답변이 답함으로 오르지 않는지 본다. 넘으면 멈추고 보고한다 |
| 6 | `/code-review` | `compare.py`·`report.py`를 바꾸므로 병합 전에 돌린다(사용자 결정 2026-11-03) |

유료 호출은 5의 재채점뿐이다. 앞 결과 파일은 덮어쓰지 않는다.

## 수정 허용 파일

`src/rag/gen_eval/report.py`, `src/rag/gen_eval/compare.py`, `configs/eval/gen_v1.yaml`, `configs/judge/prompt/j_v13.yaml`(새 파일), `configs/exp/`의 새 기준 config와 `current.yaml`, `tests/test_gen_eval.py`, `tests/test_gen_eval_freeze.py`, `tests/test_speakers.py`, `docs/SPEC.md`, `docs/gen-eval-criteria.md`, `docs/DECISIONS.md`, `docs/drafts/spec-attribution-safety.md`, `docs/PLAN.md`, `docs/PLAN-done.md`, 이 문서, `notebooks/42_01_잘못귀속_안전조건.ipynb`, `.claude/skills/exp-judgment/SKILL.md`, `.claude/agents/exp-judge.md`, `docs/harness/adr/`

## 범위 밖

- EXP-019·EXP-020 다시 채점과 다시 판정
- `verdicts` 지시와 충실성 계산 변경. 불일치 질의의 충실성을 0으로 두는 안(D-67에서 쓰지 않기로 함)
- 관련성에 근거를 주는 변경
- δ, δ_r, 기준별 하락 값 변경(재실행 반폭이 어림과 가깝다)
- H22 잘못 귀속 변형 실험(다음 EXP)

## 결정 사항

1. 초안 `docs/drafts/spec-attribution-safety.md` 승인(SPEC, `configs/eval/gen_v1.yaml`, 기준 문서, j_v13). 기록은 D-68
2. 메인이 정함(D-68 결정 4, P1): 이미 나온 compare JSON은 고치지 않는다. 지금 코드로 EXP-020을 다시 비교하면 새 조건도 걸리지만 판정 기록은 바꾸지 않는다

## 결과 (2026-11-03)

커밋: 구현 1babba5

- 검증(`slice-verifier`): 완료 기준 1\~5 통과. pytest·ruff 통과. `compare.main` 진입점 테스트가 상한 초과에서 안전 조건 실패를 내고, `gen_verdict` 조건 제거, `speaker_mismatch` 부호·분자 반전, 비교 부호 뒤집기 사본 4종에서 실패한다. report의 불일치 비율이 노트북과 같다. EXP-019·EXP-020을 새 코드로 다시 비교하면 새 조건도 걸리고 기록된 JSON은 그대로다
- 코드 리뷰(완료 기준 6, 분리된 서브에이전트): 판정 경로의 버그 없음. 지적 2건(이름 수가 다른 생성 기록에서 세어짐, 생성 기록이 없으면 report가 멈춤)은 `matching_gens`로 고쳤다
- 사용자 승인: 허용폭 0.02, 초안(화자 이름이 나온 답변 수를 보고에 더함), j_v13 사용(재검증 수용, 지시를 더 고치지 않음)
- 같은 설정 재실행(사용자 승인 2026-11-03 대화): `rag.gen_eval.generate +exp=current gen_eval.gen_rep=1` → `rag.gen_eval.judge`(같은 override), 그때 별칭은 EXP-019 설정과 j_v12, 커밋 1fa2d58, `LANGSMITH_TRACING=false`. 생성 $0.0882, judge 새 호출 1,226회, 응답 없음 0. 결과 `data/gen_eval/judge/hybrid-cond-filter-law-ms256-k20-ce-v4-dev-full-spk-head-r1-deepseek_go_mixed-j_v12.jsonl`(SHA-256 `d8c116588d5442df7b68560b2fe44a2875766f780173600453ff81fa81ad0c8a`). 답변이 글자까지 같은 질의 67/330. 반폭은 노트북 42_01과 D-68
- 기준선 재채점(커밋 1babba5): `rag.gen_eval.judge +exp=exp019_j13`, `LANGSMITH_TRACING=false`. 새 호출 302회, 저장 응답 2,100회, 응답 없음 0. 결과 `data/gen_eval/judge/hybrid-cond-filter-law-ms256-k20-ce-v4-dev-full-spk-head-deepseek_go_mixed-j_v13.jsonl`(SHA-256 `3e077d08d42b6c52c6610efcd7d492546fc479edd8454d7bbff166e5d1a738a0`). 충실성 0.872(297), 관련성 0.879(302), 불일치 비율 0.026(297질의), 이름 답변 147/330, 형식 오류 4
- 재검증: 같은 생성 기록의 j_v12 대 j_v13. 관련성 −0.002 [−0.021, +0.018](302), 종합 −0.001 [−0.011, +0.009](297), 충실성과 불일치 비율은 같다(메인이 임시로 셈, 회의 단위 10,000회). 판정 이동 30질의: 답함 → 일부 15, 일부 → 답함 7, 답하지 않음 → 일부 6, 일부 → 답하지 않음 1, 답하지 않음 → 답함 1. 분포는 답함 241 → 234, 일부 50 → 63, 답하지 않음 11 → 5
- 사례 대조(서브에이전트 판단 1회, 메인이 4질의 직접 확인): 교정 10, 부당한 강화 10, 부당한 완화 4, 경계 6. j_v13이 맞는 쪽 11, j_v12가 맞는 쪽 17, 둘 다 다름 2. 문구로 설명되는 6건 중 5건은 맞게 바뀌었고 24건은 바꾸지 않은 규칙의 적용이 달라진 것으로 보인다(추론, 반복 채점 없음). 질의자 말만 전한 7질의는 일부 5, 답함 2
- 완료 기준 5에 걸려 멈추고 보고했고, 사용자가 j_v13 사용을 정했다. 흔들림과 오판은 그전부터 감수해 온 사항이다

### 지시서와 다르게 한 것

- `speaker_mismatch_max`가 config에 없을 때 멈추는 검사를 넣지 않았다. 값이 없으면 config 오류로 멈춰 검사가 겹친다
- 화자 이름이 나온 답변 수를 report에 더했다(사용자 결정, D-68 결정 1)
- `exp-judge` 정의는 고치지 않았다. compare의 판정을 그대로 따르므로 `exp-judgment` 스킬만 고쳤다
- 안전 조건의 제외 정의: 초안은 진술이 없는 질의만 뺀다고 적었지만 SPEC은 충실성을 계산하지 않은 질의를 뺀다고 적는다(형식 오류 포함, 코드와 같음). 이번 기록에서 값 차이는 없다(297질의). 사용자가 SPEC 문구를 승인했다(2026-11-03)

