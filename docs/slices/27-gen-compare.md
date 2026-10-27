# S27 생성 설정 비교

두 생성 설정의 judge 결과를 받아 SPEC "생성 단계 평가 > 판정"(D-53)대로 채택·보류·기각을 내는 명령을 만든다(PLAN 생성 평가 "생성 설정 비교", 이슈 #156). 지금 생성 평가 모듈에는 실행 하나의 report만 있고, 기준과 후보를 짝지어 비교하는 계산은 노트북(`notebooks/37_01_SPEC개정_판단재료.ipynb`의 `per_query`·`half_width`)에만 있다. 생성 EXP(H10 등)를 판정하려면 이 명령이 먼저 있어야 한다.

흐름: A. 지시서 확인 뒤 구현한다. 새 API 호출은 없다(기존 judge 결과만 읽는다).

## 결정 사항 (구현 전 확인)

사용자 결정(2026-10-27): 1은 (a). 판정은 gen-full 결과로 하고, judge 설정이 다르면 멈춘다(메인이 정한 것 2·3 확인). 기각과 안전 조건의 순서는 검토해 보고한다(메인이 정한 것 6).

1. 판정 기준값(δ 0.02, 하락 허용폭 충실성 −0.05·관련성 −0.035, δ_r 0.02)을 둘 곳
   - (a) 새 파일 `configs/eval/gen_v1.yaml`(추천): 검색 판정 기준값(`configs/eval/spec_v1.yaml`의 `min_gain` 등)과 같은 곳이라 평가 프로토콜 값이 한 디렉터리에 모인다. `configs/eval/`은 보호 경로라 새 파일을 만드는 데 사용자 승인이 필요하고, 승인을 DECISIONS에 적는다(PR 위험도 단방향). 이후 실험 중 값이 바뀌지 않게 보호된다
   - (b) `configs/config.yaml`의 `gen_eval.compare`: 승인 없이 만들 수 있지만, 보호 경로 밖이라 실험 config가 값을 덮어써도 감사가 막지 않는다
   - 예: (a)에서 EXP config가 `gen_eval.compare.min_gain=0.01`을 넣어도 기준값은 `configs/eval/gen_v1.yaml`에서 읽어 판정이 바뀌지 않는다. (b)에서는 그 override로 판정 선이 0.01로 내려간다

## 메인이 정한 것 (PR에서 확인)

1. 명령은 검색 판정(`rag.eval.compare`)과 같은 모양으로 judge 결과 파일 두 개를 받는다: `uv run python -m rag.gen_eval.compare --base <기준 judge.jsonl> --cand <후보 judge.jsonl> [--out <결과.json> [--overwrite]]`. `+exp` override로 경로를 만들지 않는 것은 기준과 후보가 서로 다른 실험 config에서 나오기 때문이다
2. 판정은 gen-full(판정용 330질의)에서만 한다. 두 파일의 qid 집합이 `eval_qids`(gen_eval 기본 설정)의 gen-full 표본과 같지 않으면 원인을 적고 멈춘다. 검색 판정이 dev-full 고정인 것과 같다(gen-small은 작동 확인용, SPEC)
3. 읽을 때 확인하고 어긋나면 멈추는 것(구현 원칙 "사람이 넣는 입력"): 두 경로가 같은 파일, S22 이전 형식(`require_s22`), judge가 다름(`judge_recipe`의 `name`·`model`·`base_url`·`params`·`extra_body`·`step_params`·`prompt_version`·`prompt_sha256`과 judge 쪽 코드 판정 설정 `filler_phrases`·`check_patterns`·`chunk_key_min`·`item_eval`), 한 파일 안에서 이 값이나 거부 문구가 섞임. judge가 다르면 차이가 생성 설정이 아니라 채점 방식에서 나온다. 거부 문구(`refusal`)는 생성 프롬프트에서 오는 값이라 프롬프트 실험에서 바뀔 수 있어 멈추지 않고 차이를 출력한다. 커밋·생성 레시피는 한 파일 안에서 섞여도 된다(근거가 같은 질의에 기준 결과를 쓰는 S26 방식). 감사 지적으로 구현에 맞춰 고침: 처음 지시서는 `filler_phrases` 등도 차이만 낸다고 적었다
4. 질의 단위 값은 노트북 `per_query`와 같게 계산한다. 종합 지표는 질의마다 충실성·관련성 평균이고, 둘 중 하나라도 없는 질의는 NaN이다. 기준마다 두 실행 모두 값이 있는 질의만 쓴다(짝지은 제외, D-47 결정 6). 과잉 거부율은 질의마다 `over_refusal / judged`이고 `judged`가 0인 질의는 두 실행에서 함께 뺀다
5. 구간은 `rag.eval.bootstrap.paired_bootstrap`을 그대로 부르고, 재표본 단위·반복·seed·alpha는 `configs/eval/spec_v1.yaml`의 `bootstrap`을 읽는다(SPEC: 검색 판정과 같은 회의, 10,000회, seed 20260929). 회의는 `load_gold(cfg, "dev-full")`의 `conference_number`다
6. 판정 함수는 순수 함수(`gen_verdict`)로 두고 테스트한다. 채택: 종합 지표 하한 > 0, 점 추정 ≥ δ, 충실성 하한 ≥ −0.05, 관련성 하한 ≥ −0.035, 과잉 거부율 상한 ≤ δ_r. 기각: 종합 지표 상한 < 0. 그 밖은 보류이고, 보류이면 걸린 조건(종합 지표 구간, 점 추정 < δ, 충실성 하락, 관련성 하락, 과잉 거부)을 함께 낸다
   - 기각과 안전 조건의 순서(사용자 요청으로 검토): 순서에 따라 판정이 달라지는 경우가 없다. 기각(종합 지표 상한 < 0)과 채택(종합 지표 하한 > 0)은 같은 구간에서 함께 성립할 수 없고, 안전 조건은 채택 조건에만 들어 있어 채택과 보류만 가른다. 그래서 기각이면 안전 조건 결과와 관계없이 기각이고, 안전 조건에 걸린 것은 기각 판정에도 걸린 조건으로 함께 낸다(판정은 바꾸지 않음). 기각은 예외 채택 대상이 아니다(ADR-0037). 예: 관련성 −0.06 [−0.09, −0.03], 충실성 +0.02일 때 종합 지표 −0.02 [−0.035, −0.005]면 기각이고 관련성 하락 조건도 걸린 조건으로 표시한다
7. 출력: 기준별(충실성, 답변 관련성, 종합 지표, 핵심 답변 포함도(보조), 과잉 거부율) 기준·후보 평균, 차이, 95% 구간, 계산한 질의 수와 판정, 걸린 조건. `--out`은 `write_guarded`로 쓴다(같은 입력이면 같은 내용, 구현 원칙). 결과에 두 파일의 SHA-256과 gen-full qid 집합의 해시를 남긴다

## 만드는 것

- `configs/eval/gen_v1.yaml`(결정 사항 1 (a)일 때) 또는 `configs/config.yaml`의 `gen_eval.compare`
- `src/rag/gen_eval/compare.py`: 위 명령과 `per_query`·`gen_verdict`
- `tests/test_gen_eval.py`: 합성 judge 기록으로 짝지은 제외, 과잉 거부 분모 0 제외, 판정 갈래(채택, 기각, 보류의 걸린 조건 다섯 가지), 입력 확인(같은 파일, judge 다름, qid 집합 다름)
- CLAUDE.md "명령"에 호출법 한 줄

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | `rag.gen_eval.compare --base <S25 베이스라인 …-j_v8-n330.jsonl> --cand <그 파일을 임시 디렉터리에 복사한 것>` | 모든 차이 0, 판정 보류(종합 지표 구간 하한 0) |
| 3 | `--cand`에 베이스라인 330행 중 S26 오라클 11질의(`…-oracle-…-j_v8.jsonl`)를 바꿔 넣은 임시 파일(S26과 같은 비교 방식) | 끝까지 나온다. 관련성은 노트북 36_01과 같이 차이 0(0.871 → 0.871)이고, 포함도 계산 질의는 258이다(노트북은 짝짓기 전 258 → 263. 오라클에서 새로 계산된 5질의는 기준에서 빠져 짝지은 제외로 함께 빠진다) |
| 4 | 같은 명령 두 번, `--out`(임시 디렉터리) | 같은 내용(두 번째는 그대로 둠) |
| 5 | `--cand`에 S24 반복(100질의, `…-j_v8-r1.jsonl`) 파일 | qid 집합이 다르다고 멈춤 |

임시 파일은 `data/` 밖(검증 세션의 임시 디렉터리)에 만들고, `data/` 안의 파일은 읽기만 한다. judge가 다른 경우는 실제 330질의 파일이 없어(비교용 judge 설정은 100질의만 채점) 테스트의 합성 기록으로 확인한다.

## 수정 허용 파일

`configs/eval/gen_v1.yaml`(새 파일, 결정 사항 1 (a)) 또는 `configs/config.yaml`(`gen_eval.compare`), `src/rag/gen_eval/compare.py`, `tests/test_gen_eval.py`, `CLAUDE.md`(명령 한 줄), `docs/DECISIONS.md`(결정 사항 1 (a)의 보호 경로 승인), 이 문서, `docs/PLAN.md`·`docs/PLAN-done.md`

## 범위 밖

- 생성 EXP 판정 스킬·exp-judge 갈래: PLAN "하네스 생성 평가 반영"(F 흐름)
- multi-doc 보조 관찰: 필요한 실험에서 정한다(D-53 결정 7)
- judge 지시·판정표(D-49 동결), `src/rag/eval/`(읽기만)
- 생성·judge 반복이 여러 개인 결과의 평균 비교: SPEC 판정은 실행 하나씩이다

## 결과 (2026-10-27)

- 커밋: 구현 8a3a3fc. `uv run pytest -q` 322 passed, `uv run ruff check .` 통과
- slice-verifier: 완료 기준 1\~5 통과. 복사본 비교는 모든 차이 0·보류, 오라클 11질의를 바꿔 넣은 330행은 보류(충실성 −0.0039 [−0.0085, −0.0004], 관련성 0, 종합 지표 −0.0020 [−0.0060, +0.0013], 포함도 n 258), `--out` 두 번 같은 내용, 100질의 파일은 멈춤. 임시 파일은 `data/` 밖에 만들었다
- protocol-auditor: 위반 없음. 지시서 "메인이 정한 것" 3이 구현과 어긋난 것을 지시서 쪽에서 고쳤다
