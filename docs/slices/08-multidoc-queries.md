# S8 multi-doc 질의 생성·검사

S7 후보 집합(`data/multidoc/pools.jsonl`)마다 정답 문서가 여러 개(2개 이상, v3부터 상한 `max_gold` 5)인 질의를 하나 만들고, 생성과 다른 모델로 검사해 통과한 것만 남긴다. 이 조각은 파일럿 30건(유형별 10)까지 실행한다. 본 생성(300\~500건)과 사람 검수는 G3에서 한다.

## 용어

- 시작 묶음: 질의 하나의 근거가 되는 문서(D-13은 2\~3개, v3부터 2\~`max_gold`개). `law`는 `pools.jsonl`의 `seed_doc_ids`, `conf`·`questioner`는 생성 에이전트가 고른다
- 요소: 답에 들어가야 하는 사실 하나. 검사 쪽은 요소마다 그 요소를 담은 문서와 근거 문장(원문 인용)을 낸다
- 정답 문서: 검사 결과 요소를 하나 이상 담은 문서. 후보 집합의 나머지 문서는 무관이다

## 역할과 모델 (2026-10-05 사용자 결정, 이 조각 끝에 DECISIONS 기록)

| 단계 | 누가 | 입력 | 출력 |
| --- | --- | --- | --- |
| 준비 | `rag.multidoc.prepare` | `pools.jsonl`, 코퍼스 | 후보 집합별 생성 입력 |
| 생성 | Claude Code Sonnet 에이전트(`multidoc-writer`) | 생성 입력, 생성 지시 | 시작 묶음, 질의, 기대 답, 문서별 근거 인용. 또는 포기와 이유 |
| 검사 | Claude Code Sonnet 에이전트(`multidoc-checker`, S8c에서 OpenRouter `openai/gpt-6-luna`를 대체) | 질의, 후보 집합 전체 원문(`rag.multidoc.check --prepare`가 만든 검사 입력) | 요소별 근거 문서·인용, 답할 수 있는지 |
| 판정 | `rag.multidoc.check`(코드) | 생성·검사 결과 | 통과·불통과와 사유 |

- 같은 모델로 생성·검사하면 같은 편향이 두 단계에 겹치므로 모델 계열을 나눴다. S8c에서 사용자가 편향보다 검사 성능을 택해 검사도 Sonnet으로 바꿨다(`docs/slices/08c-checker-agent.md`, D-14)
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

메인이 `multidoc-writer`를 후보 집합 10개 안팎씩 묶어 부른다. 아래는 `gen_v2`의 요지이고, 이후 바뀐 규칙은 "파일럿 2차와 v3", "파일럿 3차와 v4"에 있다:

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
  1. 생성 쪽 `evidence`의 인용이 모두 해당 문서 `context`에 있다. 인용은 공백을 한 칸으로 줄여 원문에 그대로 있으면 인정하고, 그대로 없으면 Jev로 같은 의미가 있는지 판정해 확률이 `quote_semantic.min_prob` 이상일 때 인정한다(`docs/slices/08b-quote-semantic.md`). 인정한 인용은 고치지 않고 그대로 출력한다. 검사 쪽 `support`의 인용을 인정하지 못하면 그 근거를 빼고 판정한 결과와 두고 판정한 결과의 통과 여부를 비교해, 다르면 `quote_dependent`로 불통과하고 같으면 그 결과를 쓴다(인정하지 못한 수 `dropped_quotes`). 2026-10-06 변경, D-14
  2. `answerable`이 참
  3. 정답 문서(검사 쪽 `support`에 나온 문서의 합집합)가 2개 이상
  4. 필요성: 정답 문서마다 그 문서만 `support`에 있는 요소가 하나 이상 있다(다른 문서로 대신할 수 없다)
  5. 정답 문서 집합이 생성 쪽 `seed_doc_ids`와 같다
- 5는 제안이다. 검사 쪽이 시작 묶음 밖 문서를 더 찾거나 시작 묶음 문서를 빼면 생성 쪽 기대 답과 정답이 어긋나므로 파일럿에서는 불통과로 두고, 어긋난 건수를 따로 센다. G3 검수 뒤 다시 정한다
- 불통과는 사유 코드(`quote_missing`, `unanswerable`, `single_doc`, `substitutable`, `seed_mismatch`, `quote_dependent`, `gen_skip`)를 모두 남긴다

### 4. 출력

- `data/multidoc/check/{pool_id}.json`: 검사 레시피(검사 지시 버전·SHA-256, 검사 주체), 검사 응답, Jev 인용 판정(`quote_checks`), 판정과 사유. 파일럿의 luna 기록은 토큰 사용량·비용(OpenRouter `usage.cost`)도 담았다(`data/multidoc/pilot_v4_luna/`)
- `data/multidoc/queries.jsonl`: 검사 기록(`data/multidoc/check/`) 전체에서 통과한 질의만. `n_per_type`은 새로 호출할 대상만 고르고 이 파일에는 영향을 주지 않는다(PR #30 코멘트 결정 (a)). `qid`(`md-{pool_id}`), `pool_id`, `type`, `query`, `query_form`, `gold_doc_ids`, `pool_doc_ids`, `answer`, `elements`(원문에 없는 검사 쪽 인용은 뺀 것). S9의 입력이고 G3에서 동결한다
- 실행 끝에 유형별 생성 포기·통과·사유별 불통과 수, 입력·출력 토큰 합, 비용 합을 출력한다

### 재사용 (사용자 요구)

- `prepare`·`check`는 출력 파일이 이미 있는 `pool_id`를 건너뛴다. 메인도 `gen_out`이 있는 후보 집합은 에이전트에 다시 맡기지 않는다. 본 생성에서 `n_per_type`을 늘려 다시 실행하면 파일럿 검사 기록(40개)은 다시 호출하지 않는다
- 각 출력에 생성·검사 지시 버전과 지시 내용 SHA-256을 남긴다. 파일럿 뒤 지시가 바뀌면 파일럿 결과를 버릴지 재사용할지 사용자에게 보고하고 정한다(자동으로 다시 만들지 않는다)

### 파일럿 1차와 v2 (2026-10-06 사용자 결정)

- 1차(`gen_v1`·`check_v1`): 30건 → 생성 `ok` 14 → 통과 5(`conf` 1, `law` 4, `questioner` 0). 검사 14호출 $0.0373
- 원인: `questioner` 후보 집합은 같은 의원의 서로 다른 사안 묶음이라 "같은 주제" 규칙과 맞지 않았고, 질의자 정보가 입력에 없었다. `law` `skip` 5건 중 3건은 같은 법안의 다른 조항, `conf` 불통과는 고른 쟁점을 다른 문서도 다룬 경우(`seed_mismatch`·`substitutable`)였다
- 채택하지 않은 것: 판정 규칙 1·5 완화(질의 품질을 낮춘다), 개요 길이 확대(효과 불확실)
- v2: 질의자 메타데이터 추가, 위 2절의 유형별 규칙. 생성 입력 형식이 모든 유형에서 바뀌므로 파일럿 30건을 모두 v2로 다시 한다. 1차 결과는 `data/multidoc/pilot_v1/`로 옮겨 노트북에서 비교한다
- 검색 단계에서 화자 메타데이터를 쓰는 실험은 PLAN 백로그 H12다

### 파일럿 2차와 v3 (2026-10-06 사용자 결정)

- 2차(`gen_v2`·`check_v2`): 30건 → 생성 `ok` 16 → 통과 8(`conf` 3, `law` 5, `questioner` 0). 검사 16호출 $0.0473
- 원인: 생성 `ok` 불통과 8건 중 7건은 검사가 시작 묶음과 같은 회의의 다른 문서를 더했다. 한 회의에서 한 쟁점의 논의가 여러 문서(발언 구간)로 이어지는데 생성 쪽 정답이 2\~3개로 제한돼 있었다. `questioner`는 열거형을 쓰지 않았다(공통 규칙 "무관한 사안 이어 붙이기 금지"와 충돌로 읽힘)
- v3(`gen_v3`, 검사는 `check_v2` 그대로): 정답 문서 2개 이상 `multidoc.gen.max_gold`(5)개 이하. 쟁점을 정한 뒤 같은 회의의 같은 쟁점 문서를 모두 정답에 넣는다. `law`는 시작 묶음을 모두 포함하고 같은 회의 문서만 더할 수 있다. 열거형(공통 축 안의 항목을 모두 묻는 질의)과 이어 붙이기(공통 축 없는 사안 둘)를 구분한다. 판정의 `gen_invalid`는 정답 수 2\~`max_gold`와 S7 시작 묶음 포함을 본다. 판정 규칙 1\~5는 그대로다
- 상한 5는 Complete@5가 가능한 최대값이다. 지표는 SPEC대로 유형별로 보고하고, k 값은 S9 전에 사용자가 다시 정한다
- 결론을 낼 때까지 검사(OpenRouter)는 하지 않고 생성만 다시 한다. 2차 결과는 `data/multidoc/pilot_v2/`로 옮긴다

### 파일럿 3차와 v4 (2026-10-06 사용자 결정)

- 3차(`gen_v3`, 검사 안 함): 생성 `ok` 20(`conf` 6, `law` 10, `questioner` 4). 생성 쪽 조건(정답 수, 시작 묶음 포함, 인용 대조) 위반 0
- `questioner`는 v2·v3 모두 열거형을 쓰지 않았다. 진단: 에이전트 정의에 남은 v1 선택 규칙("이어지는 문서를 고를 수 없으면 skip")이 지시와 경쟁했고, `gen_v3` 열거형 예시가 주제로 좁힌 형태와 여러 회의 범위였다. 정의는 하네스 PR #28(ADR-0018)에서 고친다
- 열거형 범위는 한 회의 안으로 한정한다(여러 회의에 걸친 열거형은 답이 메타데이터 목록에 가까워진다). `gen_v4`는 `questioner`를 절차(회의별 열거형 → 입장 변화형 → skip)로 바꾸고 `conf`·`law` 규칙은 v3와 같다
- 다시 생성하는 범위: `questioner` order 0\~9는 v3 결과를 `data/multidoc/pilot_v3/`로 옮기고 `gen_v4`로 다시 생성한다. `law`는 다시 하지 않는다. `conf`는 order 0\~9의 v3 결과를 두고 order 10\~19를 `gen_v3`로 새로 생성한다(order 0\~9가 모두 소위원회 회의라 국정감사 회의의 수율을 보려고). 유형별 지시 버전은 `multidoc.gen.prompt_version`에 둔다
- 생성 전 점검(PR #28 병합 뒤): `gen_v3`의 열거형 공통 축에 "회의"가 있어, `conf`에서 한 회의의 서로 다른 법안을 나열하는 질의가 열거형 정의와 이어 붙이기 금지 예시에 동시에 걸렸다. `conf` v3 에이전트는 금지 쪽을 따랐다(앞서 정한 방향과 같다). `gen_v4`에서 공통 축을 인물·법안·기관으로 좁히고 `conf`는 쟁점형만 쓴다고 적었다. 질의 형태 이름(쟁점형, 회의 특정 열거형, 회의별 열거형, 입장 변화형)을 정하고 출력에 `query_form`을 더했다. `gen_v4`는 아직 쓴 기록이 없어 버전을 올리지 않고 고쳤다
- `law` v3는 옛 정의의 읽기 규칙("`law`는 시작 묶음 원문만")과 v3의 같은 회의 문서 추가가 어긋났지만, 실행 기록상 에이전트는 v3를 따라 추가 후보의 원문을 읽었고 범위 밖 읽기는 없었다. 정의 충돌로 결과가 달라진 흔적이 없어 다시 생성하지 않는다
- `conf` order 10\~19는 `gen_v3`가 아니라 고친 `gen_v4`로 생성한다. `conf` 문서 선택 규칙은 v3와 같다

### 파일럿 4차와 본 생성 준비 (2026-10-06 사용자 결정)

- 4차 검사(`check_v2`, 생성은 위 v3·v4 결과): 후보 집합 40 → 생성 `ok` 31 → 통과 11(`conf` 4, `law` 4, `questioner` 3). 검사 31호출 $0.1044. 통과율 27.5%로 v2와 같아, 유형별 250개로는 본 생성이 약 225건이다(`notebooks/08_01_파일럿.ipynb` 6절)
- 생성 쪽 인용 오류는 0건이고 `quote_missing` 11건은 모두 검사 쪽 인용 1\~2개(인용 10\~29개 중)가 원문과 달랐다. 판정 규칙 1을 바꿔 검사 쪽 인용 오류는 그 근거 항목만 뺀다(위 3절). 생성 쪽 인용 대조는 그대로다. 1차 뒤 규칙 1 완화를 채택하지 않았던 것과 달리, 생성 쪽 오류 0건이라는 근거가 새로 생겼다. 새 규칙으로 통과 15(37.5%)
- 검사 모델 비교(사용자 요청): 같은 31건을 Sonnet 서브에이전트가 같은 입력으로 검사했다(진단용, 판정에 쓰지 않음). 새 규칙으로 luna 15, Sonnet 20, 갈린 5건은 모두 Sonnet만 통과다. `seed_mismatch`는 두 검사가 함께 냈고(luna 10, Sonnet 9) 차이는 주로 `substitutable`(luna 12, Sonnet 5)이다. luna가 요소마다 근거 문서를 더 많이 댄다(인용 413 대 238). 검사 모델은 luna로 두고, 갈린 5건은 G3 파일럿 검수에서 사람이 본다. 이후 사용자가 PR #31 코멘트로 검사 모델을 Sonnet 에이전트로 바꿨다(D-14, S8c)
- conf 정답 상한 축소는 채택하지 않는다. 정답이 3개 이상인 conf·law 질의가 모두 불통과였지만 쟁점 범위가 넓은 것이 원인으로 보이고, 상한만 줄이면 v2의 `seed_mismatch`가 돌아온다. 후보 집합당 conf 통과는 v2·v3 모두 3/10이다
- 후보 집합 수: `n_pools_per_type`을 유형별로 바꿔 `conf`·`questioner` 350, `law` 250(총 950)으로 늘린다. `law`를 250으로 두면 S7 난수 소비가 같아 기존 750개의 순서와 시작 묶음이 그대로다(확인함). 새 규칙 통과율로 기대 약 378건

## 파라미터

`configs/config.yaml`의 `multidoc` 절에 더한다.

- `gen`: `n_per_type` 10, `overview_chars` 300, `max_gold` 5, `prompt_version` 유형별(`conf`·`questioner` gen_v4, `law` gen_v3)
- S7 `n_pools_per_type`: 유형별 `{conf: 350, law: 250, questioner: 350}`(위 "파일럿 4차와 본 생성 준비")
- `check`: `prompt_version`(S8c부터 check_v3), `api_key_env` `OPENROUTER_API`(Jev 인용 판정), `quote_semantic`(S8b). 파일럿 검사(luna)는 `model` `openai/gpt-6-luna`, `provider` `openai`(고정), `seed` 20260929, `reasoning_effort` medium, `check_v2`로 했고 S8c에서 이 키들을 지웠다
- `paths`: `multidoc_gen_in`, `multidoc_docs`, `multidoc_gen_out`, `multidoc_check`, `multidoc_queries`

지시 본문은 `configs/multidoc/prompt/gen_vN.yaml`, `check_vN.yaml`(지금 생성 `conf`·`questioner` v4, `law` v3, 검사 v2. `conf` order 0\~9는 v3로 만든 결과를 그대로 쓴다). 기록을 남긴 버전 파일은 고치지 않고 새 버전을 만든다(S6과 같다).

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
- `src/rag/multidoc/pools.py`, `tests/test_multidoc_pools.py`: 유형별 후보 집합 수만(2026-10-06 사용자 결정)
- `configs/config.yaml`(`multidoc.gen`·`multidoc.check`·`multidoc.n_pools_per_type`, `paths`), `configs/multidoc/prompt/`
- `notebooks/08_01_파일럿.ipynb`
- `pyproject.toml`, `uv.lock`: 인용 유사도 계산용 `rapidfuzz` 추가만(2026-10-07, PR #31)
- `docs/DECISIONS.md`, `docs/PLAN.md` S8 체크, `CLAUDE.md` "명령" 절, 이 문서

## 범위 밖

- 생성 에이전트 정의(F 흐름, 별도 PR)
- 본 생성 300\~500건, 사람 검수, 세트 동결(G3)
- 다중 정답 채점과 검색 실행(S9)
- `src/rag/eval/`, `configs/eval/`, `data/splits/` 수정, `src/rag/multidoc/pools.py`의 후보 집합 구성 규칙 변경

## 실행 기록

| 단계 | 생성 | 검사 | 결과 |
| --- | --- | --- | --- |
| 동작 확인 | law-0000, `gen_v1` | 1호출, 입력 3,699·출력 3,549 토큰, $0.0022 | 통과 |
| 1차 | 30, `gen_v1`, 에이전트 3개 병렬 | `check_v1` 14호출(동작 확인 포함), 입력 176,235·출력 30,514 토큰, $0.0373 | 통과 5 |
| 2차 | 30, `gen_v2`, 에이전트 3개 병렬 8\~14분 | `check_v2` 16호출, 입력 202,972·출력 43,947 토큰, $0.0473 | 통과 8 |
| 3차 | 30, `gen_v3`(questioner는 뒤에 v4로 대체) | 하지 않음 | 생성 `ok` 20 |
| 4차 | `questioner` 0\~9 `gen_v4` 6.5분, `conf` 10\~19 `gen_v4` 19분 | `check_v2` 31호출, 입력 467,394·출력 91,967 토큰, $0.1044 | 통과 11, 새 규칙 15 |

- 검사 비용 합 $0.1890(OpenRouter `usage.cost`). 호출당 약 $0.0034(4차)
- 생성 입력(order 0\~9) SHA-256 `0697a168…64fc`, 두 번 실행 일치. `pools.jsonl`(950개) SHA-256 `d1e0f04ae92c3c0bc8cc69d571d4f226b6aed4e5952b6f51bac5bc6b0d4c2bbc`, 두 번 실행 일치, 기존 750개 레코드 그대로
- 판정 규칙 변경 뒤 `check` 재실행: 새 호출 0건, 검사 기록 전체를 저장된 응답으로 다시 판정해 `queries.jsonl` 15건. 덧붙이는 값 없이 실행한 결과와 `multidoc.gen.n_per_type=20`으로 실행한 결과의 SHA-256이 같다(`f733915a…`)
- 인용 유사도 대조 뒤(`quote_match` 0.8·15자) `check` 재실행: 새 호출 0건, 검사 쪽 인용 14개를 어절 경계에 맞춘 원문 대목으로 바꾸고 인정하지 못한 인용·`quote_dependent` 0건, 통과 15건 그대로. `queries.jsonl` SHA-256 `c56dba8e…`(인용이 원문 대목으로 바뀌어 달라짐)
- 인용을 원문 대목으로 바꾸는 처리를 빼고 유사도 계산을 rapidfuzz `partial_ratio`로 바꾼 뒤(PR #31) `check` 재실행: 새 호출 0건, 인정하지 못한 인용·`quote_dependent` 0건, 통과 15건 그대로. `queries.jsonl` SHA-256 `fba96654…bf78`(인용이 검사 모델이 쓴 그대로 돌아가 달라짐)
- Sonnet 비교 검사: 서브에이전트 6개 동시(그룹당 2\~7건, 3\~17분)와 conf-0012 재검사 1개. 결과 `_workspace/s08_sonnet_check/`(로컬)
