# 코드 리뷰 2026-10(생성 평가): 기준과 결과

지난 전체 리뷰(`docs/reviews/2026-10-code-review.md`, 2026-10-21) 뒤 생성 평가 모듈을 S14c\~S27에서 완성했다. 그 뒤로 `src/`가 38커밋·약 1,200줄 바뀌었고 대부분 `src/rag/gen_eval/`이다. 조각마다 slice-verifier(완료 기준)와 protocol-auditor(평가 프로토콜)를 거쳤지만 일반 버그 리뷰는 거의 하지 않았다. 생성 EXP(H10 등)의 판정이 모두 이 모듈 위에서 나오고 judge 지시·집계는 동결돼 있어(D-49), 실험을 쌓은 뒤 채점 버그가 나오면 베이스라인과 이미 판정한 후보를 모두 다시 채점해야 한다. H10 착수 전에 한 번 본다.

리뷰는 지적 목록만 낸다. 고칠 항목은 사용자가 고르고, 수정은 리팩터링 SLICE(A 흐름)로 나눠 PR을 따로 낸다.

## 목적

1. 채점이 조용히 틀리는 곳: 기준 문서(`docs/gen-eval-criteria.md`)·SPEC "생성 단계 평가"와 코드의 어긋남, 분모·제외·형식 오류 처리
2. 판정 경로의 일관성: 실행 하나의 집계(`report`)와 두 실행의 판정(`compare`)이 같은 질의 단위 정의를 쓰는지
3. 재현과 동결: 생성·judge 기록의 레시피와 캐시 키가 결과를 바꾸는 입력을 모두 잡는지, 동결 대상(D-49)이 조용히 바뀔 수 있는지
4. 실행 안정성: 동시 실행, 재시도·중단, 이어 쓰기에서 기록이 빠지거나 섞이는 곳

## 범위

- 대상: `src/rag/gen_eval/`의 `judge`, `checks`, `report`, `compare`, `common`, `generate`, 생성 경로 `src/rag/generate.py`, `src/rag/index.py`의 생성이 기대는 부분(`require_env`, 경로·지문 함수), 이 모듈들의 테스트(`tests/test_gen_eval.py`, `tests/test_gen_eval_freeze.py`, `tests/test_generate*.py`), 관련 config(`configs/judge/`, `configs/prompt/`, `configs/generator/`, `configs/config.yaml`의 `gen_eval`·`paths.gen_*`, `configs/eval/gen_v1.yaml`)
- 파일 전체를 읽되 2026-10-21 이후 바뀐 부분을 먼저 본다(`git diff 810bff0 HEAD -- <파일>`. 810bff0은 지난 리뷰 기준 커밋)
- 대상 밖: `gen_eval/blind.py`(블라인드 확인 중단, D-51), `gen_eval/review.py`(일회성 비교 도구, 지난 리뷰 C-16), 검색 모듈(`retrieve`, `search`, `conditions`, `rerank`, `rewrite`. 지난 리뷰 뒤 작은 수정뿐이고 검색 단계가 끝났다, D-39), `notebooks/`, `.claude/`(하네스는 F 흐름), `src/rag/multidoc/`
- 보호 경로·동결 대상: `src/rag/eval/`(compare가 부르는 `paired_bootstrap`·`load_gold`), `configs/eval/`, judge 지시 `j_v8`과 집계 규칙(D-49, `tests/test_gen_eval_freeze.py`)은 읽고 지적하되 수정은 사용자 승인과 DECISIONS 기록을 거친다. 동결 대상을 고치는 지적은 영향 칸에 다시 채점해야 하는 범위(베이스라인 330질의 등)를 적는다
- 하지 않는 것: 코드 수정, 외부 API·Colab 호출, 생성·judge 재실행, test 분할 읽기, `data/`의 질의·라벨 원문 읽기. judge 결과 파일은 형식·필드 확인에 필요한 만큼만 읽고(질의 원문 출력 금지), 수치 재현이 필요하면 기존 결과로 `rag.gen_eval.report`·`compare`를 돌린다(`doppler run --`)

## 영역

영역마다 서브에이전트 하나가 읽기 전용으로 리뷰한다(동시 3개). 영역 사이 경계(질의 단위 정의, 레시피 키)는 메인이 결과를 받아 직접 읽어 정리한다.

| 영역 | 모듈 | 주로 보는 기준 |
| --- | --- | --- |
| G1 채점 | `gen_eval/judge.py`, `gen_eval/checks.py`, `configs/judge/` | 1, 3(캐시·동결) |
| G2 집계·판정 | `gen_eval/report.py`, `gen_eval/compare.py`, `gen_eval/common.py`, `configs/eval/gen_v1.yaml` | 1, 2 |
| G3 생성·실행 | `generate.py`, `gen_eval/generate.py`, `index.py`의 해당 부분, `configs/prompt/`·`configs/generator/` | 3(생성 레시피), 4 |

테스트(기준 5)는 영역마다 자기 모듈의 테스트를 본다.

## 기준

### 1. 채점 정확성

- 1a 기준 정의와 코드: 충실성(뒷받침된 진술 수 / 전체 진술 수), 관련성(1·0.5·0), 핵심 답변 포함도(답변에 담긴 핵심 진술 수 / 핵심 진술 수, 정답 청크 경계 `chunk_key_min`), 항목 평가(정보 상태 × 처리 → 결과, D-41)가 기준 문서·SPEC과 같은지
- 1b 거부 처리: 전체·부분 거부 판별, 지정 문구 없는 거부, 부분 거부에서 거부 문장을 뺀 충실성(S14b), `filler_phrases`의 쓰임
- 1c 제외와 분모: 계산하지 않은 기준(전체 거부, 참조 사용 불가, 진술 없음, 형식 오류)이 0점으로 섞이지 않는지, 분모 0, 과잉 거부율의 판정 대상 항목(모호·회피 제외)
- 1d 형식 오류: judge 응답이 깨졌을 때 점수로 들어가지 않고 오류로 세지는지, 오류율이 보고되는지

### 2. 판정 경로의 일관성

- 2a 질의 단위 정의: `report.criterion`과 `compare.per_query`가 같은 질의를 같은 이유로 빼는지(예: "진술 없음"), 종합 지표·과잉 거부율 정의가 SPEC(D-53)과 같은지
- 2b 짝지은 제외와 구간: 기준마다 두 실행에 모두 값이 있는 질의만 쓰는지, 회의 단위 bootstrap의 묶음과 질의가 어긋날 수 없는지
- 2c 입력 확인: 사람이 넣는 파일·인자(경로, 층, judge 설정)의 전제를 읽는 시점에 확인하는지(구현 원칙 "사람이 넣는 입력"). 이미 정한 범위(S27 판단할 곳: judge 모델·지시·채점 규칙만 멈춤, 이어진 파일 인정)는 지적하지 않는다

### 3. 재현과 동결

- 3a 생성 레시피: 결과를 바꾸는 입력(프롬프트, 생성 모델·제공자·파라미터, 검색 설정, 조건 추출, 재정렬 점수 파일, 근거 조건 `contexts`)이 레시피에 다 있는지, 이어 쓰기(`done_qids`)가 다른 레시피를 섞지 않는지
- 3b judge 캐시 키와 레시피: 지시·단계 파라미터·반복 번호·입력(답변·근거)이 바뀌면 캐시가 맞지 않는지, 저장 응답 재사용이 다른 입력에 잘못 쓰일 수 없는지
- 3c 동결 보호: D-49 동결 대상(지시 해시, 집계 규칙)을 테스트가 실제로 막는지, 동결 뒤 바뀐 코드가 동결된 집계를 조용히 바꿨는지
- 3d 산출물 보존: `data/` 쓰기 경로가 `write_guarded`·`refuse_existing`을 거치는지(구현 원칙, protocol-guard P10)

### 4. 실행 안정성

- 4a 동시 실행: 스레드 풀에서 공유하는 객체(형태소 분석기, 조건 추출기, 클라이언트, 캐시 디렉터리, 기록 쓰기)가 안전한지
- 4b 중단과 재시도: timeout·재시도(#160), 첫 실패에서 남은 채점 취소, 끝난 질의부터 저장한 기록이 이어 쓰기와 맞물리는지, 중단 뒤 다시 실행하면 빠지거나 두 번 쓰이는 질의가 없는지
- 4c 추적과 비용 기록: LangSmith 추적(구현 원칙), 토큰·지연 기록이 빠지는 경로

### 5. 테스트

- 5a 빈 곳: 결과를 조용히 바꿀 수 있는데 테스트가 없는 경로(기준 1\~4에서 찾은 곳 위주)
- 5b 동결 테스트가 보호하는 범위와 보호하지 못하는 범위

### 6. 단순성

- 한 번만 쓰는 추상화, 쓰이지 않는 매개변수·설정, 일어날 수 없는 경우의 오류 처리(사용자 전역 규칙 "단순성 우선"). 기준 1\~5와 겹치면 그쪽으로 적는다

## 지적 형식

지난 리뷰와 같다. 지적마다 한 행으로 적는다.

| 항목 | 내용 |
| --- | --- |
| ID | 영역과 번호(예: G1-3) |
| 기준 | 위 기준 번호(예: 1c) |
| 위치 | `file:line` |
| 문제 | 무엇이 어떻게 되어 있는지 한두 문장 |
| 영향 | 입력→동작 사례 하나, 또는 측정값. 동결 대상이면 다시 채점할 범위 |
| 제안 | 고치는 방향과 대략의 크기(파일 수) |
| 심각도 | 높음: 점수·판정이 틀리거나 조용히 바뀔 수 있음 / 중간: 생성 실험을 막거나 재현·유지 비용이 큼 / 낮음: 정리 |
| 확인 | 메인이 근거를 직접 확인했는지 |

## 절차

1. 영역 G1\~G3을 서브에이전트 3개에 동시에 맡긴다. 프롬프트에 이 문서 경로, 맡은 모듈, 읽을 수 있는 경로(`src/`, `tests/`, `configs/`, `docs/`), 읽지 않을 경로(`data/`의 질의·라벨 원문, `notebooks/`, `.env`), 지적 형식, 기준 커밋 810bff0을 넣는다
2. 메인이 지적을 모아 중복을 합치고, 심각도 높음·중간은 `file:line`을 직접 확인한다. 영역 사이 경계(2a, 3a·3b)를 정리한다
3. 아래 결과 절에 지적 표와 요약을 적고 사용자에게 본문으로 보고한다
4. 사용자가 고칠 항목을 고르면 리팩터링 SLICE로 묶어 지시서부터 쓴다. 동결 대상·보호 경로를 바꾸는 항목은 승인과 DECISIONS 기록, 재채점 범위를 먼저 정한다

## 결과

2026-10-27, `docs/gen-eval-review`(main 9ff6f27 기준). 영역 G1\~G3을 서브에이전트 3개가 읽기 전용으로 리뷰했다(합계 약 59만 토큰, 영역당 약 7분). 영역 사이 중복은 없었다. 심각도 높음·중간은 메인이 `file:line`을 직접 읽어 확인했다. 새 API 호출은 없고, 수치 재현은 기존 judge 결과와 `data/` 밖 임시 파일로 했다.

### 요약

- judge가 정상 형식으로 답하는 한 점수를 틀리게 내는 버그는 없다. 충실성·관련성·포함도·근거 청크 판정·항목 판정표·`item_counts`가 기준 문서·SPEC·D-41·D-47과 맞고, `report.criterion`과 `compare.per_query`는 같은 질의를 같은 이유로 뺀다. 베이스라인 n(충실성 314, 관련성 321, 종합 314, 포함도 258, 과잉 거부 307)이 SPEC 수치와 같다
- 판정이 조용히 틀리는 경로가 하나 있다(G2-1). 짝지은 질의가 0개인 기준은 구간이 NaN이 되고 `gen_verdict`가 이를 통과로 본다
- 중간은 형식 오류·잘못된 입력에서 엉뚱하게 멈추거나 다른 파일을 집계하는 경로(G1-1, G2-2, G2-3), 생성 클라이언트의 timeout·재시도 미설정(G3-1), 동결 테스트가 막지 못하는 judge 입력 렌더링(G1-3)이다
- G1-2(filler 부분 문자열로 전체 거부 오분류)는 S25 베이스라인 전체 거부 9질의 중 거부 문장 밖 문장이 있는 질의가 0개라 낮음으로 내렸다

### 높음

| ID | 기준 | 위치 | 문제 | 영향 | 제안 | 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| G2-1 | 1c, 2b | `src/rag/gen_eval/compare.py:53-63`, `:113-118`, `src/rag/eval/bootstrap.py:8-17` | 짝지은 질의가 0개인 기준은 `paired_bootstrap`이 (nan, nan, nan)을 내고, `gen_verdict`의 실패 조건(`lo <= 0`, `hi > max`, `lo < floor`)이 NaN 비교에서 모두 거짓이라 통과로 본다 | `item_eval=false`로 채점한 두 파일을 비교하면 과잉 거부 n 0, 구간 NaN인데 판정 `채택`, 걸린 조건 없음(에이전트 재현). `--out` JSON에 비표준 `NaN` | 기준별 짝지은 n이 0이면 원인을 적고 멈춘다. compare.py와 테스트 | 메인 확인(코드), 에이전트 재현 |

### 중간

| ID | 기준 | 위치 | 문제 | 영향 | 제안 | 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| G1-1 | 1d, 4b | `src/rag/gen_eval/judge.py:231-232` | 관련성 `label`을 dict 소속으로 검사해 list·dict 값이면 `TypeError`가 난다. 다른 단계는 형식 오류로 센다(P6) | `{"label": ["답함"]}` → 실행 전체가 멈추고, 응답이 캐시에 남아 다시 실행해도 같은 자리에서 멈춘다. 점수는 틀리지 않는다 | `isinstance(label, str)` 검사와 테스트. 동결 대상 아님 | 메인 확인 |
| G1-3 | 3b, 3c, 5b | `src/rag/gen_eval/judge.py:44`, `:72-74`, `:166-175`, `tests/test_gen_eval_freeze.py` | 동결 테스트는 지시 해시와 판정표만 대조한다. judge 입력 렌더링(`format_contexts`, `json.dumps`)과 관련성 점수표(1·0.5·0)는 테스트로도 레시피 키로도 막히지 않는다 | 렌더링을 바꾸면 테스트가 통과하고 judge 입력이 달라지는데, compare의 `JUDGE_KEYS`가 같아 옛 렌더링 기준과 새 렌더링 후보를 멈추지 않고 비교한다. 지금 버그가 아니라 앞으로의 위험 | 고정 합성 입력의 단계별 요청 본문 sha와 `RELEVANCE` 기대값을 동결 테스트에 더한다. D-49 기록과 함께 | 메인 확인(테스트 범위) |
| G2-2 | 1c, 1d | `src/rag/gen_eval/report.py:113-114`, `:125-126`, `src/rag/gen_eval/judge.py:288` | `item_handling` 형식 오류 기록은 `{"error", "items"}`(counts 없음)인데 `require_s22`가 이를 S22 이전 기록으로 보고 멈춘다. 지나더라도 `item_summary`가 `outcome`에서 `KeyError` | 형식 오류 한 질의로 report와 compare가 "S22 이전 judge 기록이다"로 멈춘다(합성 입력 재현). 지금 j_v8 파일에는 이 오류가 없다 | S22 판별을 다른 표지로, `error`가 있는 평가는 표에서 뺀다. report.py와 테스트 | 메인 확인 |
| G2-3 | 2c | `src/rag/gen_eval/report.py:210-216`, `configs/config.yaml:77` | judge 경로에 n이 없고 report가 qid 집합을 `eval_qids`와 대조하지 않는다 | CLAUDE.md의 `rag.gen_eval.report +exp=exp017`이 S24 100질의 파일을 집계한다(머리줄에 질의 수는 나옴) | 시작할 때 qid 집합이 다르면 경고, 또는 명령에 `-n330` 경로를 적는다 | 메인 확인 |
| G3-1 | 4b, 4c | `src/rag/generate.py:120-121`, `:194-204`, `configs/generator/openrouter.yaml` | 생성 `OpenAI()`에 `timeout`·`max_retries`가 없어 SDK 기본값(read 600초, 재시도 2회)을 쓴다. #160은 judge만 고쳤다 | 앞 질의 스트림이 멈추면 뒤에 끝난 생성을 쓰지 못한 채 최대 600초×재시도 기다리고, 그때 강제 종료하면 비용을 낸 생성이 사라진다. 재시도 대기가 `first_token_s`·`total_s`에 기록 없이 섞인다 | generator config에 timeout·재시도를 두고 넘긴다. 필요하면 재시도 수 출력 | 메인 확인(코드), 멈춘 사례는 관찰하지 않음 |

### 낮음

| ID | 기준 | 위치 | 문제 |
| --- | --- | --- | --- |
| G1-2 | 1b, 1c | `src/rag/gen_eval/checks.py:24`, `:60` | filler를 부분 문자열로 찾아 내용 문장도 filler로 볼 수 있다. 거부 문장과 함께면 전체 거부로 분류. S25 전체 거부 9질의 중 해당 0개(메인 확인). 고치면 그 질의는 재채점 |
| G1-4 | 3c, 5b | `tests/test_gen_eval_freeze.py:3-4` | docstring이 D-50의 실행 설정 동결을 반영하지 않는다. 바꾸면 compare에서 멈춰 섞이지는 않는다 |
| G1-5 | 4a, 4b | `src/rag/gen_eval/judge.py:176-178`, `:191` | 캐시를 원자적으로 쓰지 않아 동시 쓰기·강제 종료 때 잘린 파일이 남을 수 있다(추정) |
| G1-6 | 4c | `src/rag/gen_eval/judge.py:328-334` | 질의 안 사슬 동시 호출이 contextvars를 넘기지 않아 추적이 부모에 붙지 않는다(대량 실행은 추적 끔) |
| G2-4 | 1c, 1d | `src/rag/gen_eval/compare.py:117-125` | 결과에 실행별 제외 이유와 형식 오류 수가 없다(K8·P6) |
| G2-5 | 3 | `src/rag/gen_eval/compare.py:120-125` | 결과에 `gold_sha256`과 판정 기준값·bootstrap 설정이 없다 |
| G2-6 | 2a, 6 | `src/rag/gen_eval/report.py:7-8`, `:119-136` | 머리 설명이 옛 문구이고, report의 과잉 거부(합친 비율 0.020)가 D-53 정의(질의 평균 0.024)와 다르다 |
| G2-7 | 5a | `tests/test_gen_eval.py:892-946` | compare `main`의 짝지은 제외, NaN 구간, 형식 오류 경로에 테스트가 없다 |
| G3-2 | 4b | `src/rag/gen_eval/generate.py:63`, `:88`, `:93` | 마지막 `flush()`가 timeout 없는 대기라 Windows에서 Ctrl+C가 늦게 듣는다(재현) |
| G3-3 | 4c, 3d | `src/rag/generate.py:202-223` | 생성 `finish_reason`을 기록하지 않아 잘린 답변이 성공으로 남는다. 지금 기록은 `completion_tokens` 최대 451로 영향 없음 |
| G3-4 | 3a | `src/rag/generate.py:119`, `src/rag/index.py:114-118` | 생성 레시피에 코퍼스 지문이 없다(추정, 위험 작음) |
| G3-5 | 5a | `src/rag/gen_eval/generate.py:111-118` | 기본값에서 `contexts`를 레시피에 넣지 않는 규칙과 `KeyboardInterrupt` 경로에 테스트가 없다 |
| G3-6 | 6 | `src/rag/gen_eval/generate.py:111-112`, `src/rag/generate.py:87-90` | `contexts` 검사 중복, 실행될 수 없는 검사, 가려진 인자 이름 |
| G3-7 | 4c | `src/rag/gen_eval/generate.py:42-48` | 추적을 끈 실행에도 `langsmith_run_id`가 남고, `retrieve` 추적에 qid 메타데이터가 없다 |

지난 리뷰 C-14(LangSmith `flush`가 `finally` 밖)는 그대로 남아 있다(G3 관찰).

### 동결 대상이 걸린 항목

G1-3은 동결 테스트를 넓히는 것이라 점수를 바꾸지 않는다. G1-2는 `checks.py` 판별을 바꾸면 해당 질의를 다시 채점해야 하지만 S25 베이스라인에는 해당 질의가 없다. 나머지는 judge 지시·집계 규칙을 바꾸지 않는다.
