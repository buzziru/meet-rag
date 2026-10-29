# 테스트 리뷰 2026-10: 기준과 결과

`tests/`는 26파일·약 4,600줄이고 `uv run pytest -q`는 352개를 약 2분에 돈다(PR #181 기준). 조각과 실험마다 테스트를 더했지만 테스트 전체를 한 번에 본 적은 없다. 그 사이 블라인드 확인 중단(D-51), 프롬프트 v3 채택(D-61), 지금 기준 별칭(ADR-0076)처럼 테스트가 기대는 설정과 단계가 바뀌었다. 생성 실험(H22 등)으로 넘어가기 전에 느린 테스트, 지난 단계를 붙잡은 테스트, 빠진 검증을 정리한다(사용자 지시 2026-10-28).

리뷰는 지적 목록만 낸다. 고칠 항목은 사용자가 고르고, 수정은 SLICE(A 흐름)로 나눠 PR을 따로 낸다.

## 목적

1. 시간 병목: 2분 중 어디에 시간이 드는지와 그 원인
2. 레거시: 없앤 기능이나 끝난 단계를 붙잡은 테스트
3. 바뀐 설정과 어긋남: 채택마다 바뀌는 값을 기대값에 고정한 곳, 지금 동작과 다른 것을 검사하는 테스트
4. 빠진 검증: 깨지면 판정이 틀려지는데 테스트가 없는 곳
5. 겹침: 같은 것을 여러 테스트가 반복 검사하는 곳

## 범위

- 대상: `tests/`의 26파일과 테스트가 부르는 `src/rag/`·`configs/`
- 대상 밖: 하네스 테스트(`.claude/hooks/`, `.claude/skills/meet-rag/scripts/`의 `test_*.py`, F 흐름), `notebooks/`
- 보호와 동결: `tests/test_eval.py`·`tests/test_eval_multi.py`는 보호 경로(`src/rag/eval/`, `src/rag/eval_multi/`)를 지키는 테스트이고, `tests/test_gen_eval_freeze.py`의 기대값은 judge 동결 대상이다(D-49·D-59). 읽고 지적하되, 지우거나 기대값을 바꾸는 지적은 영향 칸에 무엇의 보호가 약해지는지 적는다. 수정은 사용자 승인과 DECISIONS 기록을 거친다
- 하지 않는 것: 테스트·코드 수정, 외부 API·Colab 호출, test 분할 읽기, `data/`의 질의·라벨 원문 출력. 테스트가 `data/`를 읽는지는 코드로 보고, 파일 내용은 열지 않는다

## 영역

영역마다 서브에이전트 하나가 읽기 전용으로 리뷰한다(동시 3개). 실행 시간 측정은 메인이 한 번 하고 결과를 세 영역에 넘긴다(절차 1). 영역 사이의 겹침(기준 5)은 메인이 결과를 모아 정리한다.

| 영역 | 테스트 파일 | 대상 모듈 |
| --- | --- | --- |
| T1 데이터·검색 | `test_ingest`, `test_chunking`, `test_splits`, `test_meta_dict`, `test_index`, `test_bm25`, `test_fusion`, `test_conditions`, `test_rerank`, `test_rewrite`, `test_search`, `test_revisions`, `test_exp_configs` | `ingest`, `chunking`, `splits`, `meta_dict`, `index`, `retrieve`, `search`, `conditions`, `rerank`, `rewrite`, `configs/exp/` |
| T2 생성·생성 평가 | `test_generate`, `test_speakers`, `test_gen_eval`, `test_gen_eval_freeze`, `test_gen_eval_blind` | `generate`, `speakers`, `gen_eval/` |
| T3 검색 평가·multi-doc·게이트 | `test_eval`, `test_eval_multi`, `test_multidoc_check`, `test_multidoc_pools`, `test_multidoc_prepare`, `test_multidoc_review`, `test_g2`, `test_sample_review` | `eval/`, `eval_multi/`, `multidoc/`, `g2`, 검수 표본 도구 |

## 기준

### 1. 시간 병목

- 1a 느린 테스트: `--durations` 상위 테스트마다 시간이 어디에 드는지(모델·토크나이저 로딩, 코퍼스·인덱스 전체 읽기, Hydra config 반복 조립, 형태소 분석기 초기화, 큰 임시 파일 쓰기)
- 1b 반복 준비: 여러 테스트가 같은 무거운 준비를 각자 하는지(모듈·세션 단위 fixture로 한 번 만들 수 있는지). 테스트 사이 상태가 섞이지 않는지도 함께 본다
- 1c 판정에 필요한 규모: 기능 확인에 필요한 것보다 큰 입력을 쓰는지(예: 문서 몇 개로 될 것을 실제 코퍼스로 확인)

### 2. 레거시

- 2a 없는 기능을 붙잡은 테스트: 지운 옵션·함수, 쓰지 않는 config 키, 대체된 경로를 검사하는 테스트
- 2b 끝난 단계의 도구: 블라인드 확인(D-51 중단), 검수 표본 도구(G 항목 종료)처럼 단계는 끝났지만 코드와 명령이 남은 도구의 테스트. 코드가 남아 있고 `CLAUDE.md` 명령에 있으면 레거시가 아니다. 블라인드 확인 도구는 검수를 하지 않지만 코드를 남긴다(사용자 결정 2026-10-29). 그 테스트는 레거시로 보지 않고 코드 삭제도 제안하지 않는다. 다른 도구의 코드를 지울지는 이 리뷰 범위 밖이라 제안 칸에만 적는다
- 2c 과거 기록 고정과의 구분: 처음 구현 당시 설정으로 기능을 검사하는 테스트(예: `+exp=exp017` 입력)와 과거 실행의 레시피·경로를 재현하는 테스트는 레거시가 아니다(사용자 결정 2026-10-28, PR #181, protocol-guard P4 "해당하지 않음")

### 3. 바뀐 설정과 어긋남

- 3a 바뀌는 값의 리터럴: 채택마다 바뀌는 값(지금 기준 EXP, 프롬프트 버전, 기준 결과 경로)을 기대값에 리터럴로 적은 곳. 판정은 protocol-guard P4를 따른다. 예: `tests/test_generate.py:113`의 임베딩 revision 리터럴이 바뀌는 값인지, `+exp=exp017` 입력에 따라 정해지는 값인지
- 3b 지금 동작과 다른 검사: 테스트 이름·docstring이 말하는 동작과 실제 단언이 다르거나, 코드가 바뀐 뒤 단언이 우연히 통과하는 테스트
- 3c config 직접 조립: 테스트가 config 파일을 우회해 값을 직접 넣어, config가 바뀌어도 테스트가 따라가지 않는 곳

### 4. 빠진 검증

- 4a 판정 경로: 검색 판정(`rag.eval.compare`), 생성 판정(`rag.gen_eval.compare`), 집계(`report`)에서 결과를 조용히 바꿀 수 있는데 테스트가 없는 분기
- 4b 보호·동결 규칙: CLAUDE.md 금지 절과 동결 결정(D-15 G3 동결 세트, D-49 judge 동결, revision 고정)을 테스트가 실제로 막는지. 막지 못하는 범위
- 4c 산출물 보존: `write_guarded`·`refuse_existing`·`check_basis`를 거쳐야 하는 쓰기·읽기 경로에 테스트가 있는지(구현 원칙, protocol-guard P10)
- 4d 사람이 넣는 입력의 확인: 입력 전제를 확인하는 코드(구현 원칙 "사람이 넣는 입력")가 테스트로 덮였는지

### 5. 겹침

- 5a 같은 검사의 반복: 같은 함수·같은 경우를 여러 테스트가 검사하는 곳. 하나를 지워도 덮는 범위가 줄지 않는 경우만 적는다
- 5b 파라미터화: 입력만 다른 테스트 여러 개를 `pytest.mark.parametrize` 하나로 합칠 수 있는 곳(낮음)

## 지적 형식

지난 리뷰(`docs/reviews/2026-10-gen-eval-review.md`)와 같다. 지적마다 한 행으로 적는다.

| 항목 | 내용 |
| --- | --- |
| ID | 영역과 번호(예: T2-3) |
| 기준 | 위 기준 번호(예: 1a) |
| 위치 | `file:line` |
| 문제 | 무엇이 어떻게 되어 있는지 한두 문장 |
| 영향 | 입력→동작 사례 하나, 또는 측정값(시간은 초). 보호·동결 테스트면 약해지는 보호 |
| 제안 | 고치는 방향과 대략의 크기(파일 수), 줄어드는 시간 예상(측정 근거와 함께) |
| 심각도 | 높음: 판정·보호가 깨져도 테스트가 통과함 / 중간: 실행 시간을 크게 늘림(10초 이상), 기준 변경마다 테스트를 고쳐야 함 / 낮음: 정리. 10초는 측정 전에 정한 값(전체 약 2분의 8%)이고, 절차 1의 측정 분포가 다른 경계를 가리키면 메인이 근거와 함께 바꿔 결과 절에 적는다(사용자 결정 2026-10-29) |
| 확인 | 메인이 근거를 직접 확인했는지 |

## 절차

1. 메인이 `uv run pytest -q --durations=40`을 한 번 돌려 상위 테스트의 시간(setup·call 구분)과 파일별 합계를 이 문서 결과 절에 적는다
2. 영역 T1\~T3을 서브에이전트 3개에 동시에 맡긴다. 프롬프트에 이 문서 경로, 맡은 파일, 1의 측정 결과, 읽을 수 있는 경로(`src/`, `tests/`, `configs/`, `docs/`, `.claude/skills/protocol-guard/`), 읽지 않을 경로(`data/`의 질의·라벨 원문, `notebooks/`, `.env`), 지적 형식을 넣는다. 테스트는 측정에 필요한 파일 단위로만 다시 돌린다(`uv run pytest -q tests/<파일> --durations=10`)
3. 메인이 지적을 모아 겹침(5a)과 중복을 합치고, 심각도 높음·중간은 `file:line`을 직접 확인한다
4. 아래 결과 절에 지적 표와 요약을 적고 사용자에게 본문으로 보고한다
5. 사용자가 고칠 항목을 고르면 SLICE로 묶어 지시서부터 쓴다. 보호·동결 테스트를 바꾸는 항목은 승인과 DECISIONS 기록을 먼저 한다

## 결과

### 측정 (2026-10-29, 로컬 CPU, 커밋 a6fce38)

- 전체 `uv run pytest -q`: 352 passed, 109.7\~118.8초(두 번). 그중 테스트 실행(setup·call·teardown 합)은 73.9초이고 setup 0.2초다. 나머지 약 36초는 수집(테스트 모듈 import)이다. `--collect-only`만 44.6초 걸렸다
- 파일별 테스트 실행 합(초): `test_bm25` 14.7, `test_gen_eval` 11.7, `test_exp_configs` 10.2, `test_revisions` 9.7, `test_search` 6.2, `test_generate` 5.6, `test_rerank` 5.0, `test_index` 3.6, 나머지 18파일은 각 1.3 이하
- 느린 테스트(call, 초): `test_bm25::test_meta_prefix_makes_metadata_searchable` 9.5, `test_bm25::test_bm25_finds_lexical_match` 5.6, `test_index::test_index_stops_when_settings_differ_from_basis` 4.0, `test_gen_eval::test_http_counts_record_sdk_retries` 3.8, `test_index::test_adopt_checks_chunk_and_embedding_rows` 2.2, `test_gen_eval::test_run_all_does_not_wait_for_slow_earlier_item` 2.0. 그 밖에 0.5\~1.4초가 약 35개이고 `test_exp_configs`·`test_revisions`의 EXP별 parametrize가 많다
- 파일 하나만 수집할 때(새 프로세스, 초): `test_rerank` 17.2, `test_search` 7.6, `test_gen_eval_blind` 7.3, `test_speakers` 7.2, `test_exp_configs`·`test_g2`·`test_rewrite`·`test_fusion` 5.7\~5.9, `test_gen_eval`·`test_gen_eval_freeze`·`test_generate` 4.9\~5.3, 나머지 2.5\~3.9. pytest import만은 0.6초다. 파일마다 가장 무거운 import가 무엇인지는 측정하지 않았다(영역 리뷰에서 본다)
- 시간 경계: 10초를 넘는 원인 후보는 수집(약 36초), `test_bm25` 두 테스트(15초), `test_exp_configs`·`test_revisions`의 config 조립(합 20초)이다. 경계를 바꿀 근거는 없어 10초를 그대로 쓴다

### 요약

지적 34건(T1 10, T2 15, T3 9). 메인이 겹침을 합치고 심각도를 맞춘 뒤 높음 6, 중간 5, 낮음 23이다. 지금 코드의 동작이 틀린 곳은 찾지 못했다. 높음은 모두 "그 코드가 깨져도 통과하는 테스트밖에 없다"는 지적이다.

- 시간: 줄일 수 있는 큰 몫은 셋이고 합쳐 약 30\~38초다(전체 약 110초). `rag.rerank`의 torch·sentence_transformers 최상단 import(T1-1, 수집 약 14초, 실측 증분), `test_bm25`의 `Kiwi()` 직접 생성(T1-2, 약 9초, 재현 실측), Hydra config 반복 조립(T1-3·T2-6, 약 7\~15초, 추정)이다. 나머지 수집 시간(T2-9, T1-9, T3-6의 파일 단독 수집)은 다른 파일이 같은 라이브러리를 이미 불러 전체 실행에서는 거의 줄지 않는다
- 판정 경로: 검색 compare(T3-1)와 multi-doc compare(T3-2)의 `main`은 부호를 뒤집거나 주지표·재표본 단위를 바꿔도 테스트가 통과한다(변형 사본으로 실측). 순위 파일을 만드는 `search()`를 부르는 테스트가 없고(T1-4), 생성 compare의 judge 설정 섞임·qid 중복 분기도 테스트가 없다(T2-3)
- 동결: judge 동결 테스트가 `Judge.__init__`을 거치지 않아 생성자에서 요청 본문이 바뀌어도 통과한다(T2-1). G3 동결 세트는 sha를 기록만 하고 대조하지 않으며 `freeze.main`이 보호 없이 덮어쓴다(T3-4). 검색 판정 config(`configs/eval/spec_v1.yaml`, `multidoc.eval`)를 고정하는 테스트는 없다(T3-3)
- 레거시: 없는 기능을 붙잡은 테스트는 없다. 끝난 단계 도구 중 `CLAUDE.md` 명령에 없는 것은 G1·G2 도구(`rag.g2`, `sample_review.main`, T3-6)와 S14·S15 검수 도구(`rag.gen_eval.review`, T2-10)다. 기각 실험 코드(jev 재정렬, 재작성)의 테스트는 규약대로 코드를 남기므로 레거시가 아니다
- 바뀐 설정 리터럴(3a): P4 위반은 없다. `tests/test_generate.py:113`의 revision은 `+exp=exp017`이 상속하는 `configs/exp/exp009.yaml:10` 값이라 해당하지 않는다

### 심각도 조정

- T3-3: 정의로는 높음이지만 중간으로 둔다. `configs/eval/`은 처음부터 PR 감사(protocol-guard P3)로 지키도록 정했고 judge만 테스트로 동결했다(D-49). 테스트로도 고정할지는 사용자 결정이다
- T1-3과 T2-6은 같은 원인(같은 override 반복 조립)이라 합쳐 중간으로 둔다(두 영역 합 10초 이상 추정)
- 높음 6건(T1-4, T2-1, T2-3, T3-1, T3-2, T3-4)은 메인이 `file:line`을 직접 읽어 확인했다. 중간 T1-1·T1-2·T1-3은 코드를 확인했고 시간은 에이전트 측정이다

### 지적 표

| ID | 기준 | 위치 | 문제와 영향 | 제안 | 심각도 | 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| T3-1 | 4a | `src/rag/eval/compare.py:44-61`, `tests/test_eval.py:188-214` | `compare.main` 테스트는 `gold_sha256`과 덮어쓰기만 단언한다. diff를 `base - cand`로 뒤집거나 주지표를 `mrr@10`으로, 재표본 단위를 질의로 바꿔도 23 passed(변형 사본 실측). 후보 Recall@5 -0.5가 +0.5로 계산돼 채택될 수 있다 | 기존 테스트에 `diff`·`primary`(config에서 읽음)·`verdict` 단언과 같은 회의 질의 사례를 더한다. 1파일. 보호 코드를 지키는 테스트라 승인 대상 | 높음 | 메인 확인 |
| T3-2 | 4a | `src/rag/eval_multi/compare.py:104-113`, `tests/test_eval_multi.py:187-218` | base·cand 순서와 `--single` 경로를 끝까지 도는 테스트가 없다. 순서를 바꾼 변형도 19 passed. 메타데이터 가설에서 채택·기각이 뒤집힐 수 있다 | diff 부호 단언과 합성 single JSON으로 `--single` 1회 실행. 1파일, 약 1초 | 높음 | 메인 확인 |
| T3-4 | 4b, 4c | `src/rag/multidoc/freeze.py:23-36`, `src/rag/eval_multi/score.py:38`, `compare.py:98` | D-15 동결 sha(`0c385a2b…`)를 읽는 곳 어디서도 대조하지 않고 기록만 한다. `freeze.main`은 `write_guarded` 없이 덮어쓴다. `queries.jsonl`을 다시 만든 뒤 freeze를 다시 돌리면 600건 세트가 조용히 바뀌고 multi-doc 채점·판정은 멈추지 않는다 | (1) 동결 sha를 config에 두고 읽을 때 대조(보호 경로, 승인·DECISIONS) (2) `freeze.main`에 `write_guarded`와 테스트(보호 경로 아님). 2\~3파일 | 높음 | 메인 확인 |
| T2-1 | 4b | `tests/test_gen_eval_freeze.py:126-132`, `src/rag/gen_eval/judge.py:157-176` | 동결 테스트가 `object.__new__(Judge)`로 만들고 `params`·`extra`·`step` 등을 직접 넣어 `__init__`을 거치지 않는다. 생성자에서 `extra`나 params 기본값이 바뀌면 실제 요청 본문이 바뀌어도 `FROZEN_REQUEST_SHA256` 대조와 compare가 통과한다(G1-3의 남은 틈) | `Judge(cfg, session)`를 그대로 부르고 `require_env`·`OpenAI`·캐시 경로만 바꾼다. 기대 sha는 그대로. 동결 테스트 수정이라 승인·DECISIONS. 보호는 넓어진다. 1파일 | 높음 | 메인 확인 |
| T2-3 | 4a | `src/rag/gen_eval/compare.py:56-66`, `tests/test_gen_eval.py:992-1013` | judge 설정 섞임(`len(found) != 1`)과 qid 중복 분기를 지나는 테스트가 없다. 섞임 검사가 깨지면 뒷줄을 다른 judge로 채점한 후보가 `rs[0]` 기준 "같은 judge"로 판정까지 간다(G2-7 반영 뒤 남은 분기) | 기존 테스트에 두 사례를 더한다. 1파일, 약 6줄 | 높음 | 메인 확인 |
| T1-4 | 4a | `src/rag/search.py:168-226`, `tests/test_exp_configs.py:59-60` | 순위 파일을 만드는 `search()`를 부르는 테스트가 없다. test_exp_configs는 `candidates`·`final` 호출을 테스트 안에 다시 써서 비교한다. `use_rerank` 조건이 틀려 재정렬이 빠져도 통과한다. rerank-pairs 경로도 테스트가 없다 | `_world` 위에서 `search(cfg)`를 직접 부르고 순위 행이 `explain`과 같은지, pairs가 fused 앞 depth개인지 본다. 1파일 약 40줄, 1초 미만(추정) | 높음 | 메인 확인 |
| T3-3 | 4b | `configs/eval/spec_v1.yaml:1-11`, `configs/config.yaml:194-196` | 검색 판정 값(`n_resamples`, `unit`, `seed`, `alpha`, `min_gain`, `primary`, `ks`)을 고정하는 테스트가 없다. `unit: meeting_name`, `min_gain: 0.005`로 바꿔도 통과하고, 남은 보호는 PR 감사(P3)뿐이다 | `cfg.eval`·`cfg.multidoc.eval`의 sha를 상수로 고정하는 테스트 1파일(보호 값이라 P4 위반 아님). 둘지 사용자 결정 | 중간(조정) | 에이전트 |
| T1-1 | 1a | `src/rag/rerank.py:21-25`, `tests/test_rerank.py:8-9` | 최상단에서 `torch`·`sentence_transformers`를 import한다. 테스트는 모델을 쓰지 않는다. 다른 모듈을 다 불러온 뒤 더한 증분이 14.2·14.6초(실측). `rag.index`는 같은 import를 함수 안에 둔다 | import를 `load_model`·`latency` 안으로 옮긴다. src 1파일 3\~4줄. 전체 수집 약 14초 감소 | 중간 | 메인 확인(코드), 에이전트(시간) |
| T1-2 | 1a, 1b | `tests/test_bm25.py:72,74` | `Kiwi()`를 두 번 새로 만든다. 공유 인스턴스 `shared_kiwi()`(`src/rag/bm25.py:67-71`)를 쓰지 않아 call 9.4초. 공유 인스턴스로는 같은 본문이 0.45초(재현 실측) | 두 곳을 `shared_kiwi()`로. 1파일 2줄, 약 9초 감소 | 중간 | 메인 확인(코드), 에이전트(시간) |
| T1-3 (T2-6 합침) | 1b, 5a | `tests/test_revisions.py:20-22`, `tests/test_exp_configs.py:52-54`, T2 테스트의 `load_cfg` 약 40회, `src/rag/index.py` `git_state` | EXP config 19개를 두 파일이 각자 조립하고(1회 0.36\~0.41초), T2는 같은 override를 반복 조립한다(`index.scope=full` 약 18회). 레시피마다 `git_state`가 git을 두 번 부른다(0.17초, 약 14회) | `tests/conftest.py`에 override별 세션 캐시(read-only 또는 복사본)를 두고, git 값을 단언하지 않는 레시피 테스트는 `git_state`를 monkeypatch한다. 약 7\~15초 감소(추정). `test_revisions`를 합치는 안은 CLAUDE.md가 가리키는 D-46 테스트라 택하지 않는 쪽을 권한다 | 중간 | 에이전트 |
| T2-4 | 4a, 4d | `src/rag/gen_eval/judge.py:492-496`, `tests/test_gen_eval.py:560-589` | `check_prompt`·`check_speakers`는 함수 단위로만 검사하고 judge `main`이 부르는지는 검사하지 않는다. 호출이 빠지면 v3 생성 기록을 다른 거부 문구로 채점해도 통과한다 | 합성 `gen_runs`와 tmp 코퍼스로 `main`이 `Judge` 생성 전에 멈추는지 본다. 테스트 1\~2개 | 중간 | 에이전트 |
| T1-5 | 4c | `src/rag/search.py:43`, `src/rag/rerank.py:161-164`, `tests/test_rerank.py:66-74` | 후보 쌍 쓰기(`write_guarded`)와 score·jev 모드의 `refuse_existing` 출력 키 선택에 테스트가 없다. 키가 틀리면 Colab 채점을 마친 뒤에야 멈춘다 | latency 테스트를 mode로 parametrize, pairs는 T1-4에서 함께 | 낮음 | 에이전트 |
| T1-6 | 4c | `src/rag/bm25.py:86-90` | settings.json이 없는 기존 BM25 인덱스는 `adopt_basis` 없이 지금 설정을 기록하고 쓴다(대상 kiwi-v1, kiwi-meta-v1 둘). 테스트 없음 | 분기를 바꿀지는 코드 결정이라 제안만. 남기면 동작 고정 테스트 1개 | 낮음 | 에이전트 |
| T1-7 | 3c | `tests/test_fusion.py:28,62`, `tests/test_rewrite.py:79`, `tests/test_search.py:250-314` | 합성 인덱스 경로를 `"kure-v1-512"` 리터럴로 쓴다. 기본 임베딩·청크가 바뀌면 크게 실패한다(조용히 통과하지 않음). 채택마다 바뀌는 값이 아니라 P4 해당 없음 | `dense_dirs(cfg)[0]`로. 3파일 8곳 | 낮음 | 에이전트 |
| T1-8 | 5a | `tests/test_bm25.py:13-20`, `tests/test_search.py:134-181` | `rrf` 동점 사례가 두 파일에서 같은 입력으로 반복된다 | test_search로 모으고 하나를 지운다 | 낮음 | 에이전트 |
| T1-9 | 1a | `tests/test_fusion.py:3`, `tests/test_rewrite.py:6`, `tests/test_exp_configs.py:11` | 도우미를 `test_search`에서 import해 단독 실행 때 `rag.search`가 같이 올라온다. 전체 실행에는 영향 없음 | 도우미를 conftest로. 4파일, test_fusion 단독 약 3초 감소(추정) | 낮음 | 에이전트 |
| T1-10 | 3b | `tests/test_exp_configs.py:100-101` | DECISIONS 머리 줄을 `splitlines()[2]`로 읽고 `EXP-{target}` 포함만 본다. 검색 EXP-017과 생성 EXP-018이 한 줄에 있어, 별칭을 exp017로 되돌리고 생성 칸을 고치지 않아도 통과한다 | "생성 EXP-NNN"을 짚어 대조. 1줄 | 낮음 | 에이전트 |
| T2-2 | 3b, 4b | `tests/test_gen_eval.py:821-898`, `src/rag/gen_eval/judge.py:161-166` | `test_judge_configs_pass_timeout_and_retries`는 config 값만 보고 `Judge`가 `OpenAI`에 넘기는지는 보지 않는다. 빠지면 SDK 기본값(600초, 2회)으로 돌아가고 HTTP 집계가 0이 된다. 판정 값은 그대로 | T2-1의 생성자 테스트에서 `OpenAI` 인자를 단언 | 낮음 | 에이전트 |
| T2-5 | 4a | `src/rag/gen_eval/compare.py:39-46` | `gen_verdict` 경계값(하한 0, 점 추정 0.02 등) 테스트가 없다. 지금 부등호는 SPEC과 같다 | 경계 사례 parametrize | 낮음 | 에이전트 |
| T2-7 | 1a | `tests/test_gen_eval.py:883` | 실제 `time.sleep(2)`로 늘 2초 | 0.5초와 0.01초로 줄이거나 Event로. 약 1.5초 | 낮음 | 에이전트 |
| T2-8 | 1a | `tests/test_gen_eval.py:830-839` | 429에 헤더가 없어 SDK가 0.47초 기다린다 | `retry-after-ms: 1`. 약 0.45초 | 낮음 | 에이전트 |
| T2-9 | 1a | `src/rag/gen_eval/judge.py:25-29`, `blind.py:15-16`, `src/rag/generate.py:16-20` | openai·langsmith·sklearn 최상단 import로 단독 수집 5\~10초. 전체 실행에서 T2가 더하는 시간은 0.01초(실측) | 파일 단독 실행 때만 이득. T1-1을 먼저 | 낮음 | 에이전트 |
| T2-10 | 2b | `src/rag/gen_eval/review.py`, `tests/test_gen_eval.py:419-424,573-580` | S14·S15 검수 도구는 `CLAUDE.md` 명령에 없고 단계가 끝났다. 테스트는 `refuse_existing` 연결을 보아 코드가 있는 동안 유효하다 | 코드를 지울지는 범위 밖, 사용자 결정 | 낮음 | 에이전트 |
| T2-11 | 5a | `tests/test_gen_eval.py:290-309`, `tests/test_gen_eval_freeze.py:56-67` | `test_item_outcome_follows_rules`의 값은 동결 테스트 전수 검사에 모두 들어 있다 | `test_gen_eval.py` 쪽을 지운다(동결 테스트는 그대로) | 낮음 | 에이전트 |
| T2-12 | 5a | `tests/test_gen_eval.py:600-606`, `tests/test_speakers.py:117-133` | j_v8 문구·기본 지시·j_v9 한 문장 차이 단언은 sha 동결로 결과가 늘 같다. 고유 보호는 `:596-599`(j_v7, 동결 밖)뿐 | 당시 검수 기록으로 둘지 사용자 결정. `:596-599`는 둔다 | 낮음 | 에이전트 |
| T2-13 | 5b | `tests/test_gen_eval.py:441-681`, `tests/test_gen_eval_freeze.py:126-132` | `object.__new__(Judge)` 준비가 다섯 곳에 있다(T2-1과 같은 원인) | fixture 하나로. 2파일 | 낮음 | 에이전트 |
| T2-14 | 3b | `tests/test_gen_eval.py:729-732` | 판정용 세트 테스트가 `concurrency`(실행 설정)도 단언한다 | `concurrency` 단언을 뺀다 | 낮음 | 에이전트 |
| T2-15 | 4c, 4d | `src/rag/gen_eval/judge.py:463`, `compare.py:130-131`, `blind.py:221-222`, `src/rag/gen_eval/generate.py:105-111` | `judge_cases`의 `refuse_existing`, compare `--out`의 `write_guarded`, blind `main`, `concurrency`·`contexts` 검사에 테스트가 없다. 지금 코드는 맞게 막는다 | "있으면 멈춤" 테스트를 각 1개 | 낮음 | 에이전트 |
| T3-5 | 4c | `src/rag/g2.py:62,131-134,181-182`, `src/rag/multidoc/review.py:131-208` | 사람 검수 칸이 있는 파일(`g2_failures.md`, `g3_sample.md`, `g3_scope.md`)을 `refuse_existing` 없이 덮어쓴다. 판정에는 영향 없음 | 도구를 남기면 `refuse_existing`과 테스트. T3-6에서 지우면 없어짐 | 낮음 | 에이전트 |
| T3-6 | 2b | `tests/test_g2.py`, `tests/test_sample_review.py:17-26`, `src/rag/g2.py` | G1·G2는 끝났고 `rag.g2`·`sample_review` 명령은 `CLAUDE.md`에 없다. `sample_qids`는 multidoc review가 쓰므로 그 테스트는 살아 있다 | 코드를 지울지는 사용자 결정. 지우면 테스트도 함께, `sample_qids`는 남긴다 | 낮음 | 에이전트 |
| T3-7 | 1c | `tests/test_eval_multi.py:187-218`(2.08초), `tests/test_eval.py:188-214` | 덮어쓰기 확인에 실제 config의 `n_resamples` 10000을 쓴다 | override로 500. 약 1.5초(추정) | 낮음 | 에이전트 |
| T3-8 | 3b | `tests/test_eval_multi.py:62-75` | `pytest.raises(ValueError)`에 `match`가 없어 다른 ValueError로도 통과한다 | 경우마다 `match`. 1파일 | 낮음 | 에이전트 |
| T3-9 | 5b | `tests/test_multidoc_check.py:129-147` | 입력과 기대 reason만 다른 테스트 네 개 | parametrize | 낮음 | 에이전트 |

### 고칠 항목 (사용자 결정 2026-10-29)

- 고친다: 높음 T1-4, T2-1, T2-3, T3-1, T3-2, T3-4와 중간 T1-1, T1-2, T1-3(T2-6 포함), T2-4. 테스트 수정 SLICE 하나로 묶는다. 보호 경로·동결 테스트에 걸리는 T2-1, T3-1, T3-2, T3-4는 SLICE 지시서의 결정 사항에서 범위를 확인받고 DECISIONS에 기록한다
- 고치지 않고 기록으로 둔다: 중간 T3-3(검색 판정 config는 지금처럼 PR 감사 P3로 지킴)과 낮음 전부. T3-6·T2-10의 끝난 단계 도구 코드와 T2-12의 문구 단언 테스트는 그대로 둔다

### 범위 밖 관찰 (확인하지 않음)

- `src/rag/eval_multi/metrics.py`의 `sha256`·`read_run`·`metric_table`·`to_markdown`이 `eval/metrics.py`를 복제한다(보호 코드 중복, 테스트 겹침 아님)
- `rag.meta_dict.main`, `rag.conditions.main`, `rag.ingest.write_jsonl`, `search.export_queries`, `generate.save`가 `write_guarded` 없이 쓴다. P10 대상인지 판단하지 않았다
- `paired_bootstrap`이 회의 크기로 가중한 평균을 쓴다. SPEC이 가중 방식을 정하지 않아 지적하지 않았다
