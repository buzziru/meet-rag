# S30 테스트 리뷰 수정

테스트 리뷰 `docs/reviews/2026-10-test-review.md`(PR #184)에서 사용자가 고른 높음 6건과 중간 4건을 고친다(PLAN 생성 평가 "테스트 리뷰 수정(SLICE)", H22 전). 판정·동결 코드가 깨지면 실패하는 테스트를 더하고, 전체 테스트 시간을 줄인다. 기준 설정의 동작은 바꾸지 않는다.

흐름: A. 지시서 확인 뒤 구현한다. 외부 API·Colab 호출은 없다.

대상: 높음 T1-4, T2-1, T2-3, T3-1, T3-2, T3-4, 중간 T1-1, T1-2, T1-3(T2-6 포함), T2-4. T3-3과 낮음 전부는 범위 밖이다(리뷰 문서 "고칠 항목").

## 만드는 것

| ID | 만드는 것 | 바뀌는 파일 |
| --- | --- | --- |
| T3-1 | `test_score_and_compare_out_are_guarded`의 compare 실행에 `diff`(런 a·b로 계산한 값), `primary`(config에서 읽음), `verdict` 단언을 더하고, 두 질의를 같은 회의에 둔 사례로 재표본 단위가 회의 열인지 본다 | `tests/test_eval.py` |
| T3-2 | multi-doc compare의 `diffs` 부호(base·cand 순서) 단언과, 합성 single 비교 JSON으로 `--single` 경로를 끝까지 도는 테스트 | `tests/test_eval_multi.py` |
| T3-4 | G3 동결 세트를 읽을 때 sha를 D-15 값과 대조해 다르면 멈춘다(결정 사항 1). `rag.multidoc.freeze.main`은 `write_guarded`로 쓴다. 두 동작의 테스트 | 결정 사항 1에 따라 정함, `src/rag/multidoc/freeze.py`, 테스트 |
| T2-1 | 동결 테스트 `request_shas`가 `object.__new__(Judge)` 대신 `Judge(cfg, session)`를 부른다. `require_env`·`OpenAI`·캐시 경로만 바꾼다. 기대 sha(`FROZEN_REQUEST_SHA256`)는 그대로 | `tests/test_gen_eval_freeze.py` |
| T2-3 | 생성 compare `check_inputs`의 judge 설정 섞임·qid 중복 사례 | `tests/test_gen_eval.py` |
| T2-4 | judge `main`이 생성 레시피 여럿, `check_prompt`, `check_speakers`에서 `Judge` 생성 전에 멈추는 테스트(합성 `gen_runs`, tmp 코퍼스) | `tests/test_gen_eval.py` |
| T1-4 | 합성 인덱스 위에서 `search(cfg)`를 직접 불러 순위 파일 행이 `explain`과 같은지, rerank-pairs 모드가 쓴 쌍이 fused 앞 depth개인지 본다 | `tests/test_exp_configs.py` 또는 `tests/test_search.py` |
| T1-1 | `rag.rerank`의 `torch`·`sentence_transformers` import를 `load_model`·`latency` 안으로 옮긴다(`rag.index`와 같은 방식). 동작은 같다 | `src/rag/rerank.py` |
| T1-2 | `test_meta_prefix_makes_metadata_searchable`의 `Kiwi()` 두 곳을 `shared_kiwi()`로 | `tests/test_bm25.py` |
| T1-3 | `tests/conftest.py`에 override별 config 세션 캐시를 두고(돌려줄 때 복사본, 테스트 사이 상태가 섞이지 않게), `test_revisions`·`test_exp_configs`와 T2 테스트의 반복 조립에 쓴다. git 값을 단언하지 않는 레시피 테스트는 `git_state`를 바꿔 끼운다. `test_revisions.py`는 CLAUDE.md가 가리키는 D-46 테스트라 파일을 합치지 않는다 | `tests/conftest.py`(새 파일), 해당 테스트 파일 |

## 완료 기준

1. `uv run pytest -q` 전부 통과, `uv run ruff check .` 통과
2. 판정 변형이 테스트에 걸린다: 리뷰에서 쓴 변형 사본(검색 compare의 diff 부호 뒤집기, 주지표 `mrr@10`, 재표본 단위를 질의로, multi-doc base·cand 순서 바꾸기)을 같은 방식(pytest 플러그인으로 사본을 끼움, 저장소 파일은 고치지 않음)으로 다시 돌리면 각각 1개 이상 실패한다
3. 동결 테스트 범위: `Judge.__init__`에서 `self.extra`를 `None`으로 바꾼 사본을 끼우면 `tests/test_gen_eval_freeze.py`가 실패한다. 바꾸지 않으면 기대 sha 그대로 통과한다
4. G3 동결 대조: 합성 동결 파일의 sha가 기대값과 다르면 읽는 쪽이 원인을 적고 멈추고, 같으면 지나간다. `freeze.main`을 같은 출력에 내용이 다르게 두 번 돌리면 두 번째에서 멈춘다
5. 생성 compare: 한 파일에 judge 설정이 두 가지면 "섞여 있다"로, qid가 중복이면 질의 불일치로 멈춘다
6. 시간: `uv run pytest -q --durations=0`과 `--collect-only`를 리뷰 측정과 같은 방식으로 재서 결과 절에 전후를 적는다(목표 수치는 두지 않는다)
7. 기준 설정 불변: `+exp=current`의 생성 레시피와 검색 config 조립 결과가 구현 전후 같다(`git_commit`·`git_dirty` 제외)

## 결정 사항 (구현 전 확인)

1. T3-4 동결 sha를 대조하는 위치. 동결 세트를 읽는 곳은 `src/rag/eval_multi/score.py:29`, `compare.py:90`(보호 경로), `src/rag/search.py:86`, `src/rag/conditions.py:172` 넷이다
   - (a) 넷 모두에서 대조(추천): sha를 `configs/config.yaml`의 `multidoc.frozen_sha256`(새 키, `multidoc.eval` 밖)에 두고, 읽는 함수 하나(`rag.eval_multi.metrics`에 둠)를 네 곳이 부른다. 채점·비교까지 막는다. 보호 경로 `src/rag/eval_multi/`를 고치므로 사용자 승인과 DECISIONS 기록이 필요하다
   - (b) 보호 경로 밖(검색·조건)에서만 대조: `eval_multi`는 고치지 않는다. 동결 세트가 바뀌면 새 순위는 막히지만, 이미 있는 순위 파일을 바뀐 세트로 채점·비교하는 것은 막지 못한다
   - 예: `queries_g3.jsonl`을 다시 만들어 한 줄이 달라지면 (a)는 `rag.eval_multi.score`가 "G3 동결 세트 sha가 D-15와 다르다"로 멈추고, (b)는 `rag.search search.queries=multidoc`만 멈추고 score는 그대로 채점한다
2. T2-1 동결 테스트 수정의 기록. 기대값(요청 본문 sha)과 동결 대상(j_v8, `fr_v1`, `OUTCOMES`·`item_outcome`)은 바꾸지 않고 테스트가 만드는 `Judge`의 경로만 바꾼다. protocol-guard가 위반으로 보는 것은 동결 대상과 기대값을 고친 경우다(`.claude/skills/protocol-guard/SKILL.md:106`)
   - (a) DECISIONS에 새 결정 없이 이 SLICE 결과 절과 D-49 점검 줄의 `보강` 표시로 남긴다(추천). 보호 범위가 넓어지기만 한다
   - (b) 새 결정으로 적는다
3. T3-1·T3-2는 보호 코드(`src/rag/eval/`, `src/rag/eval_multi/`)를 고치지 않고 그 테스트에 단언만 더한다. `tests/`는 보호 경로가 아니라 승인 대상으로 보지 않는다. 다르게 보면 알려 달라

## 수정 허용 파일

- `tests/` 아래 테스트 파일과 새 `tests/conftest.py`
- `src/rag/rerank.py`(import 위치만), `src/rag/multidoc/freeze.py`
- 결정 사항 1이 (a)면 `src/rag/eval_multi/metrics.py`·`score.py`·`compare.py`, `src/rag/search.py`, `src/rag/conditions.py`, `configs/config.yaml`(`multidoc.frozen_sha256` 키 하나), `docs/DECISIONS.md`. (b)면 `eval_multi`와 DECISIONS를 뺀다
- 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`

## 범위 밖

- T3-3(검색 판정 config 고정 테스트)과 리뷰 낮음 전부
- `src/rag/eval/`(보호 경로), judge 동결 대상의 내용과 기대값
- 하네스 테스트(`.claude/`)
- 리뷰 문서의 범위 밖 관찰(`eval_multi/metrics.py` 중복, 확인용 파일의 `write_guarded` 미사용)
