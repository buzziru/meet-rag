# S8 multi-doc 질의 생성·검사

S7 후보 집합(`data/multidoc/pools.jsonl`)마다 정답 문서가 2\~3개인 질의를 하나 만들고, 생성과 다른 모델로 검사해 통과한 것만 남긴다. 이 조각은 파일럿 30건(유형별 10)까지 실행한다. 본 생성(300\~500건)과 사람 검수는 G3에서 한다.

## 용어

- 시작 묶음: 질의 하나의 근거가 되는 문서 2\~3개(D-13). `law`는 `pools.jsonl`의 `seed_doc_ids`, `conf`·`questioner`는 생성 에이전트가 고른다
- 요소: 답에 들어가야 하는 사실 하나. 검사 쪽은 요소마다 그 요소를 담은 문서와 근거 문장(원문 인용)을 낸다
- 정답 문서: 검사 결과 요소를 하나 이상 담은 문서. 후보 집합의 나머지 문서는 무관이다

## 역할과 모델 (2026-10-05 사용자 결정, 이 조각 끝에 DECISIONS 기록)

| 단계 | 누가 | 입력 | 출력 |
| --- | --- | --- | --- |
| 준비 | `rag.multidoc.prepare` | `pools.jsonl`, 코퍼스 | 후보 집합별 생성 입력 |
| 생성 | Claude Code Sonnet 에이전트(`multidoc-writer`) | 생성 입력, 생성 지시 | 시작 묶음, 질의, 기대 답, 문서별 근거 인용. 또는 포기와 이유 |
| 검사 | `rag.multidoc.check`, OpenRouter `openai/gpt-6-luna` | 질의, 후보 집합 전체 원문 | 요소별 근거 문서·인용, 답할 수 있는지 |
| 판정 | `rag.multidoc.check`(코드) | 생성·검사 결과 | 통과·불통과와 사유 |

- 같은 모델로 생성·검사하면 같은 편향이 두 단계에 겹치므로 모델 계열을 나눴다
- 생성 에이전트 정의(`.claude/agents/multidoc-writer.md`)는 하네스 변경이라 이 조각과 분리해 F 흐름(`chore/` 브랜치, ADR)으로 만든다. 에이전트 정의에는 입출력 경로와 도구 제한만 두고, 생성 지시 본문은 이 조각의 `configs/multidoc/prompt/gen_v1.yaml`에 둔다. 지시를 고칠 때 하네스를 건드리지 않고 버전으로 남기기 위해서다
- 에이전트 도구는 Read·Write로 제한하고, 읽기는 생성 입력·지시 파일, 쓰기는 생성 출력 경로로 한정한다

## 입력 제한

- 생성·검사 입력은 코퍼스의 `context`와 메타데이터(`date`, `committee_name`, `meeting_name`, `meeting_number`, `session_number`, `agenda`), 라벨의 질의자 이름·직위(`questioner_name`, `questioner_position`), 후보 집합 키(`law` 값 등)만이다. 질의자 정보는 코퍼스에 없어 라벨 zip에서 이 두 필드만 읽는다(v2, 아래 "파일럿 1차와 v2")
- 평가 질의(`summary_q`), 답변 라벨, 검색 결과(순위·점수)는 넣지 않는다(SPEC 누수 방지, D-13 감사 지적). `rag.multidoc.prepare`는 질의 파일과 `data/runs/`를 읽지 않는다
- `pools.jsonl`이 `test` 회의를 이미 뺐으므로(D-13) `test` 문서는 들어가지 않는다. `prepare`에서 한 번 더 확인한다

## 만드는 것

### 1. 준비 `rag.multidoc.prepare`

- `multidoc.gen.n_per_type`(파일럿 10)만큼 유형마다 `order` 순서로 후보 집합을 꺼낸다
- 후보 집합마다 `data/multidoc/gen_in/{pool_id}.json`: `pool_id`, `type`, `key`, 문서 목록(`doc_id`, 메타데이터, `speakers`(질의자 이름·직위 목록), 개요). `law`는 `seed_doc_ids`를 함께 넣는다
- 개요는 `context` 앞 `multidoc.gen.overview_chars`(제안 300)자다. 전체 원문은 `data/multidoc/docs/{doc_id}.txt`로 따로 쓴다. 생성 에이전트는 개요로 문서를 고른 뒤 고른 문서의 원문만 읽는다(D-13 "후보 집합 개요에서 고른다")

### 2. 생성 (에이전트)

메인이 `multidoc-writer`를 후보 집합 10개 안팎씩 묶어 부른다. 생성 지시(`gen_v2`)의 요지:

- `conf`·`questioner`: 개요를 보고 주제가 이어지는 문서 2\~3개를 고른다. 이어지는 문서가 없으면 포기하고 이유를 적는다. `law`: 주어진 시작 묶음을 쓴다
- `conf`: 쟁점을 고른 뒤 개요를 다시 훑어 같은 쟁점의 문서가 4개 이상이면 다른 쟁점을 고르고, 질의에 고른 문서에만 있는 사실(조항, 기관 입장 등)을 넣어 범위를 좁힌다. 무관한 법안·사안 둘을 이어 붙인 질의는 쓰지 않는다
- `law`: 시작 묶음 문서가 같은 법안의 서로 다른 조항을 다루면 회의를 날짜·위원회로 특정한 열거형("2017년 ○○소위와 2019년 △△소위에서 각각 논의된 쟁점")을 쓸 수 있다. 회의를 특정하지 않으면 후보 집합의 다른 문서도 정답이 된다
- `questioner`: 질의자 메타데이터(`speakers`)로 인물 중심 질의를 쓸 수 있다. 입장 변화형("a 위원이 ㄱ 사안에 대해 각 회의에서 밝힌 입장")과 열거형("a 위원이 ○○위원회에서 지적한 사업들")을 허용한다. 이름은 메타데이터에서 가져오고, 답의 내용은 원문에 있어야 한다
- 질의는 고른 문서 모두가 있어야 완전히 답할 수 있게 쓴다. 국회 회의록을 찾는 사용자가 쓸 만한 문장으로 쓰고, `doc_id`나 "문서 1" 같은 표현은 쓰지 않는다. 날짜·위원회·법안 이름은 써도 된다
- 출력 `data/multidoc/gen_out/{pool_id}.json`: `pool_id`, `status`(`ok`·`skip`), `seed_doc_ids`, `query`, `answer`(기대 답), `evidence`(문서마다 `doc_id`와 원문 그대로의 근거 인용 1개 이상), `skip_reason`

### 3. 검사·판정 `rag.multidoc.check`

검사 호출은 생성 쪽의 `seed_doc_ids`·`answer`·`evidence`를 보지 않는다. 질의와 후보 집합 전체 문서(번호를 붙인 원문과 메타데이터, 질의자 이름·직위)만 보낸다(`check_v2`). 질의자를 문서 머리에 넣어야 인물 중심 질의에서 어느 문서가 그 사람의 발언인지 판정할 수 있다.

- 검사 출력(structured outputs JSON 스키마): `answerable`(후보 집합 문서로 답할 수 있는가), `elements`(요소마다 `fact`와 `support`. `support`는 그 요소를 담은 모든 문서의 `doc_id`와 원문 인용)
- 코드 판정. 아래를 모두 만족하면 통과다
  1. 생성 쪽 `evidence`와 검사 쪽 `support`의 인용이 모두 해당 문서 `context`에 있다(공백을 한 칸으로 줄인 뒤 부분 문자열 대조)
  2. `answerable`이 참
  3. 정답 문서(검사 쪽 `support`에 나온 문서의 합집합)가 2개 이상
  4. 필요성: 정답 문서마다 그 문서만 `support`에 있는 요소가 하나 이상 있다(다른 문서로 대신할 수 없다)
  5. 정답 문서 집합이 생성 쪽 `seed_doc_ids`와 같다
- 5는 제안이다. 검사 쪽이 시작 묶음 밖 문서를 더 찾거나 시작 묶음 문서를 빼면 생성 쪽 기대 답과 정답이 어긋나므로 파일럿에서는 불통과로 두고, 어긋난 건수를 따로 센다. G3 검수 뒤 다시 정한다
- 불통과는 사유 코드(`quote_missing`, `unanswerable`, `single_doc`, `substitutable`, `seed_mismatch`, `gen_skip`)를 모두 남긴다

### 4. 출력

- `data/multidoc/check/{pool_id}.json`: 검사 요청 레시피, 원 응답, 토큰 사용량, 비용(OpenRouter 응답 `usage.cost`), 판정과 사유
- `data/multidoc/queries.jsonl`: 통과한 질의만. `qid`(`md-{pool_id}`), `pool_id`, `type`, `query`, `gold_doc_ids`, `pool_doc_ids`, `answer`, `elements`. S9의 입력이고 G3에서 동결한다
- 실행 끝에 유형별 생성 포기·통과·사유별 불통과 수, 입력·출력 토큰 합, 비용 합을 출력한다

### 재사용 (사용자 요구)

- `prepare`·`check`는 출력 파일이 이미 있는 `pool_id`를 건너뛴다. 메인도 `gen_out`이 있는 후보 집합은 에이전트에 다시 맡기지 않는다. 본 생성에서 `n_per_type`을 늘려 다시 실행하면 파일럿 30건은 다시 호출하지 않는다
- 각 출력에 생성·검사 지시 버전과 지시 내용 SHA-256을 남긴다. 파일럿 뒤 지시가 바뀌면 파일럿 결과를 버릴지 재사용할지 사용자에게 보고하고 정한다(자동으로 다시 만들지 않는다)

### 파일럿 1차와 v2 (2026-10-06 사용자 결정)

- 1차(`gen_v1`·`check_v1`): 30건 → 생성 `ok` 14 → 통과 5(`conf` 1, `law` 4, `questioner` 0). 검사 14호출 $0.0373
- 원인: `questioner` 후보 집합은 같은 의원의 서로 다른 사안 묶음이라 "같은 주제" 규칙과 맞지 않았고, 질의자 정보가 입력에 없었다. `law` `skip` 5건 중 3건은 같은 법안의 다른 조항, `conf` 불통과는 고른 쟁점을 다른 문서도 다룬 경우(`seed_mismatch`·`substitutable`)였다
- 채택하지 않은 것: 판정 규칙 1·5 완화(질의 품질을 낮춘다), 개요 길이 확대(효과 불확실)
- v2: 질의자 메타데이터 추가, 위 2절의 유형별 규칙. 생성 입력 형식이 모든 유형에서 바뀌므로 파일럿 30건을 모두 v2로 다시 한다. 1차 결과는 `data/multidoc/pilot_v1/`로 옮겨 노트북에서 비교한다
- 검색 단계에서 화자 메타데이터를 쓰는 실험은 PLAN 백로그 H12다

## 파라미터

`configs/config.yaml`의 `multidoc` 절에 더한다.

- `gen`: `n_per_type` 10, `overview_chars` 300, `prompt_version` gen_v2
- `check`: `model` `openai/gpt-6-luna`, `provider` `openai`(고정, `allow_fallbacks: false`), `seed`(기존 20260929), `reasoning_effort` medium, `max_tokens`, `prompt_version` check_v2, `api_key_env` `OPENROUTER_API`. 이 모델은 OpenRouter에서 `temperature`를 받지 않아(지원 파라미터, 2026-10-06) 넣지 않는다
- `paths`: `multidoc_gen_in`, `multidoc_docs`, `multidoc_gen_out`, `multidoc_check`, `multidoc_queries`

지시 본문은 `configs/multidoc/prompt/gen_vN.yaml`, `check_vN.yaml`(지금 v2). 기록을 남긴 버전 파일은 고치지 않고 새 버전을 만든다(S6과 같다).

## 비용과 승인

- 파일럿 검사 입력: 후보 집합 30개 원문 합 약 43만 자(유형별 conf 14.5만, law 12.1만, questioner 16.9만, 하나의 최대 4.5만). `check --dry-run`이 호출 수와 입력 토큰 추정을 출력한다. OpenRouter 호출 전에 이 추정과 모델 단가로 예상 비용을 보고하고 승인받는다
- 생성 쪽은 Claude Code 에이전트라 API 과금이 없다. 소요 시간만 보고한다
- 검사 호출은 순차로 하고, 5xx는 OpenRouter 상태를 확인한 뒤 한 번만 다시 시도한다. 402·403은 다시 시도하지 않고 보고한다

## 노트북과 결정의 순서

1. 동작 확인: 후보 집합 1개(유형 하나)로 준비 → 생성 → 검사를 끝까지 돌린다(호출 1회. 승인 범위에 포함해 보고한다)
2. 파일럿 30건 실행
3. `notebooks/08_01_파일럿.ipynb`: 1차(v1)와 v2의 유형별 수율 비교, 유형별 생성 포기·통과·사유별 불통과, `seed_mismatch` 사례의 차이 유형, 정답 문서 수 분포, 토큰·비용과 본 생성(유형별 100\~170) 비용 외삽, 통과·불통과 예시 몇 건(질의와 요소. 원문 인용은 짧게)
4. 사용자가 노트북을 보고 판정 규칙(특히 5번)과 본 생성 진행 여부를 정한다
5. DECISIONS에 생성·검사 모델과 경로, 검사 방식, 판정 규칙, 파일럿 비용을 기록한다. 그 뒤 PR. 파일럿 사람 검수는 G3

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run python -m rag.multidoc.prepare` | 종료 코드 0, 유형별 10개 생성 입력과 문서 원문 파일 |
| 2 | 생성 입력 필드 검사 | 위 1절 필드만. 질의·답변 라벨·검색 결과 없음. 모든 문서가 `test` 밖 회의 |
| 3 | 1을 두 번 실행해 생성 입력 SHA-256 비교 | 일치 |
| 4 | `uv run python -m rag.multidoc.check --dry-run` | 호출 없이 호출 수·입력 토큰 추정 출력 |
| 5 | 파일럿 30건 생성·검사 후 `check` 재실행 | 새 호출 0건(재사용) |
| 6 | `queries.jsonl` 검사 | 통과 건만, `gold_doc_ids` 2개 이상이고 `pool_doc_ids` 안, 모든 인용이 원문에 있음 |
| 7 | `uv run pytest -q` | 통과. 판정 규칙 1\~5, 인용 대조, 건너뛰기를 합성 입력으로 시험한다. 네트워크와 `data/`를 쓰지 않는다 |
| 8 | `uv run ruff check .` | 통과(노트북 포함) |
| 9 | 노트북 처음부터 실행 | 오류 없음. API를 호출하지 않고 저장된 결과만 읽는다 |
| 10 | 문서 기록 | `CLAUDE.md` "명령"에 준비·검사 명령, PLAN S8 체크, DECISIONS 기록, 이 문서 "실행 기록"에 소요 시간·토큰·비용 |

## 수정 허용 파일

- `src/rag/multidoc/prepare.py`, `src/rag/multidoc/check.py`, `tests/test_multidoc_check.py`, `tests/test_multidoc_prepare.py`
- `configs/config.yaml`(`multidoc.gen`·`multidoc.check`, `paths`), `configs/multidoc/prompt/`
- `notebooks/08_01_파일럿.ipynb`
- `docs/DECISIONS.md`, `docs/PLAN.md` S8 체크, `CLAUDE.md` "명령" 절, 이 문서

## 범위 밖

- 생성 에이전트 정의(F 흐름, 별도 PR)
- 본 생성 300\~500건, 사람 검수, 세트 동결(G3)
- 다중 정답 채점과 검색 실행(S9)
- `src/rag/eval/`, `configs/eval/`, `data/splits/`, `src/rag/multidoc/pools.py` 수정

## 실행 기록

(실행 후 채운다)
