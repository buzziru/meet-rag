# S15 산출물 지문과 덮어쓰기 방지

코드 리뷰 2026-10(`docs/reviews/2026-10-code-review.md`)의 "산출물 지문·덮어쓰기" 묶음을 고친다. 이미 있는 산출물을 만든 설정과 대조하지 않고 읽거나 덮어쓰기 방지 없이 쓰는 곳이다. 지금 기록이 틀렸다는 뜻이 아니라, 다음에 설정을 바꾸거나 다시 실행할 때 오류 없이 결과가 바뀔 수 있는 곳이다. 검색 순위와 생성 결과는 바뀌지 않아야 한다.

| 리뷰 ID | 위치 | 고치는 것 |
| --- | --- | --- |
| A-1 | `src/rag/index.py:139` | 청크·임베딩을 다시 쓰기 전에 인덱스 지문을 대조한다 |
| A-2 | `src/rag/index.py:80`, `src/rag/retrieve.py:183` | 조각 행 수와 청크·임베딩 행 수를 대조한다 |
| A-3 | `src/rag/splits.py:70-79` | 분할 파일을 덮어쓰기 방지로 쓴다 |
| B-1 | `src/rag/retrieve.py:134`, `src/rag/generate.py:140` | 재정렬 점수 파일에 지문을 두고 읽을 때 대조한다 |
| B-2 | `src/rag/rerank.py:51`, `:76`, `:124`, `:138` | 재정렬 점수·지연 파일을 덮어쓰기 방지로 쓴다 |
| C-1 | `src/rag/generate.py:103-120` | 생성 레시피에 조건 추출 설정과 재정렬 점수 파일 해시를 넣는다 |
| C-4 | `src/rag/gen_eval/common.py:47-60`, `judge.py:228-230` | 생성 이어 쓰기와 judge의 레시피 비교 규칙을 맞춘다 |
| C-5 | `src/rag/gen_eval/judge.py:70-78`, `report.py:94` | judge 레시피에 코드 판정 설정과 커밋을 넣고 report가 그 값을 쓴다 |
| C-8 | `src/rag/gen_eval/review.py:86-88` | 사람 검수 CSV를 덮어쓰지 않는다 |

## 만드는 것

### 덮어쓰기 방지 함수 위치

`write_guarded`를 `rag.search`에서 `rag.index`(ROOT, `load_cfg`가 있는 공용 모듈)로 옮긴다. `rag.splits`·`rag.rerank`·`rag.gen_eval.judge`가 검색 실행 모듈을 불러오지 않고 쓰게 한다. 멈출 때의 안내 문구(지금은 `search.overwrite=true`)를 호출하는 쪽이 넘긴다. 과거 코드를 위한 재수출은 두지 않는다. 다른 공용 함수(`split_thought` 등)의 위치는 다음 묶음(검색·생성 규칙, B-7)에서 정한다.

### 인덱스 지문 (A-1, A-2)

- `rag.index`가 인덱스 디렉터리에 `basis.json`을 쓴다. 담는 것: `embedding.model_name`, `embedding.revision`, 청킹 설정(`name`, `chunk_tokens`, `overlap_tokens`), `index.scope`, `index.max_docs`, `index.shard_size`, 코퍼스 SHA-256, dev-small이면 `dev_small_docs` SHA-256
- `basis.json`이 있으면 지금 설정으로 만든 값과 대조하고, 다르면 청크·임베딩을 건드리기 전에 멈춘다. 다른 설정으로 다시 만들려면 디렉터리를 지우거나 경로를 바꾼다
- `chunks.jsonl`이 있는데 `basis.json`이 없으면(지금 있는 인덱스 전부) 멈춘다. `adopt_basis=true`를 주면 지금 설정으로 `basis.json`을 쓰고 이어 간다(결정 사항 1)
- 있는 임베딩 조각을 건너뛸 때 조각의 행 수가 그 조각에 들어갈 청크 수와 같은지 본다(`np.load(mmap_mode="r")`). 다르면 멈춘다. `shard_size`를 바꿔 재개한 경우가 여기서 걸린다
- `rag.retrieve.load_dense`는 인덱스마다 청크 수와 임베딩 행 수가 같은지 보고, `Retriever`는 인덱스를 읽기 전에 `basis.json`의 임베딩 모델·revision·청킹·범위가 지금 config와 같은지 본다. 다르거나 `basis.json`이 없으면 멈춘다. 코퍼스 해시는 읽을 때 대조하지 않는다(인덱스를 만들 때만 본다)

### 분할 파일 (A-3)

`rag.splits`가 `data/splits/queries.csv`와 `dev_small_docs.txt`를 `write_guarded`로 쓴다. 덮어쓰기 옵션은 두지 않는다. 보호 경로라 바꾸려면 사용자 승인을 받고 파일을 지운 뒤 다시 실행한다. 채점 결과에 분할 해시를 남기는 것은 보호 경로(`src/rag/eval/`)라 이 조각에서 하지 않는다.

### 재정렬 점수 (B-1, B-2)

- `rag.rerank`가 점수 파일 옆에 `<점수 파일>.basis.json`을 쓴다. 담는 것: `backend`, cross-encoder면 `model`·`revision`·`max_length`·`device`·`dtype`, jev면 `jev.model`·`instructions`·`levels`, 후보 쌍 파일 SHA-256
- 점수·지연 파일과 지문을 `write_guarded`로 쓴다. 덮어쓰려면 `search.overwrite=true`(후보 쌍 파일과 같은 옵션)
- `read_rerank_scores`가 지문을 대조한다. 대조하는 것은 `backend`, 모델·revision·`max_length`(jev는 모델·지시·등급), 후보 쌍 SHA-256이다. `device`·`dtype`은 기록만 하고 대조하지 않는다. EXP-017 점수는 Colab cuda·float16으로 만들었고 `configs/exp/exp017.yaml` 기본값은 로컬 지연 측정용 cpu·float32라, 대조하면 로컬 검색이 멈춘다. 지문이 없으면 멈추고, `adopt_basis=true`로 `rag.rerank`를 실행하면 채점하지 않고 지문만 쓴다(결정 사항 1)

예: `retriever.rerank.model`만 바꾸고 `rag.rerank`를 다시 돌리지 않은 채 `rag.search`를 실행하면 지금은 EXP-017 점수로 순위를 낸다. 바꾼 뒤에는 "재정렬 점수 지문이 지금 설정과 다르다(model)"로 멈춘다.

### 생성 레시피 (C-1)

`rag.generate.recipe`에 `conditions`(최상위 `cfg.conditions` 전체), `name_titles`(`cfg.ingest.name_titles`), 재정렬을 쓰면 `rerank_scores_sha256`(점수 파일 SHA-256)을 더한다. 기존 생성 기록 파일에는 이 키가 없어 같은 경로에 이어 쓰면 "다른 레시피"로 멈춘다. 이어 쓸 S14·S14b 기록은 없다(생성 베이스라인은 새 실행).

### judge 레시피 (C-4, C-5)

- `judge_recipe`에 `gen_eval.refusal`, `filler_phrases`, `chunk_key_min`, judge 실행 시점 `git_commit`, 생성 기록들의 커밋 목록(`gen_commits`)을 더한다. `gen_recipe_sha256`은 `stable()`(커밋 제외)로 계산한다
- `judge.main`의 "레시피가 여럿이다" 검사를 `stable()` 비교로 바꾼다(결정 사항 2)
- `rag.gen_eval.report`는 경계값 `chunk_key_min`을 judge 기록의 `judge_recipe`에서 읽는다

### 검수 파일 (C-8)

`rag.gen_eval.review`는 출력 CSV가 있으면 멈춘다. 덮어쓰려면 `search.overwrite=true`(judge 결과와 같은 옵션).

### 테스트

- 인덱스: 지문이 다르면 멈춤(`max_docs`를 바꾼 경우), 지문 없는 기존 인덱스는 멈추고 `adopt_basis`면 이어 감, `shard_size`를 바꿔 재개하면 멈춤, `load_dense`의 행 수·지문 대조(A-11 일부)
- 분할: 같은 내용이면 그대로, 다르면 멈춤
- 재정렬: 지문 쓰기와 대조(모델이 다르면 멈춤, dtype만 다르면 통과, 후보 쌍이 바뀌면 멈춤), adopt
- 생성 레시피: 조건 설정·재정렬 점수 파일이 바뀌면 레시피가 달라짐(C-17 일부)
- judge 레시피: 판정 설정이 들어감, 커밋만 다른 생성 기록은 함께 채점됨
- review: 출력이 있으면 멈춤

## 결정 사항

1. **지문이 없는 기존 산출물을 어떻게 받아들일지.** 지금 `data/index/`에 인덱스 9개(기준 exp017이 쓰는 것은 `snowflake-ko-fixed-512-64`·`snowflake-ko-fixed-256-32`의 dev-small·full 4개), `data/rerank/`에 점수 파일 8개(기준이 쓰는 것은 `*-ms256-k20-cross-encoder` 3개, test 1개 제외)가 있다. 결정: (a)(사용자 결정 2026-10-21).
   - (a) `adopt_basis=true`를 명시한 실행에서만 지금 설정으로 지문을 한 번 쓴다. 기존 파일을 다시 만들지 않는다. 지문은 "이 설정으로 만들었다"는 선언이라, 실제로 다른 설정으로 만든 파일이면 틀린 지문이 붙는다. 그래서 adopt할 인덱스와 점수 파일마다 대응 EXP 문서의 실행 기록(설정, 해시)과 대조한 뒤 실행한다. 예: `rag.index +exp=exp017 index.scope=full adopt_basis=true` → `data/index/kure-v1-…/full/basis.json` 생성, 청크·임베딩은 그대로
   - (b) 지문이 없는 산출물을 모두 다시 만든다. 전체 인덱스는 Colab L4 약 21분(1.54 CU/시간, 인덱스 하나 약 0.54 CU), 재정렬 점수는 Colab T4. 결과가 같아야 하므로 얻는 것은 지문의 확실함뿐이다
   - (c) 지문이 없으면 경고만 하고 이어 간다. 지금과 같이 조용히 쓰이는 경우가 남는다
2. **생성 기록의 커밋이 서로 다를 때.** 결정: (a)(사용자 결정 2026-10-21).
   - (a) judge도 커밋을 빼고(`stable()`) 비교해 채점하고, 생성 커밋 목록을 judge 레시피에 남긴다. 예: 커밋 A에서 n=10, 문서만 바꾼 커밋 B에서 n=20으로 이어 생성 → judge가 30개를 채점하고 `gen_commits: [A, B]`를 남긴다. 코드가 바뀐 커밋 사이의 이어 쓰기도 통과하므로, 섞였는지는 커밋 목록을 보고 사람이 판단한다
   - (b) 생성 이어 쓰기에서 커밋이 다르면 멈춘다. 예: 같은 상황에서 커밋 B의 이어 쓰기가 멈추고, n=20을 처음부터 다시 생성한다(유료 호출 10회 추가). STATUS 커밋 하나에도 멈춘다

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. 결정 사항 1이 (a)면, 기준이 쓰는 인덱스 4개와 점수 파일 3개(summary_q dev-small·full, multidoc full)에만 지문을 쓴다. 각 adopt 전에 EXP 문서의 실행 기록과 설정을 대조한 결과를 진행 기록에 적는다. 로컬에서 하고 Colab은 쓰지 않는다. 나머지 인덱스·점수 파일(지난 EXP 재현용)은 지문 없이 두고, 그 EXP를 다시 돌릴 때 같은 절차로 adopt한다. test 점수 파일은 건드리지 않는다
3. 결과 불변: `uv run python -m rag.search +exp=exp017 index.scope=dev-small`, `… index.scope=full`, `… index.scope=full search.queries=multidoc`가 각각 기존 순위 파일과 "같은 내용, 그대로 둠"으로 끝난다
4. 멈춤 확인: `rag.search +exp=exp017 index.scope=dev-small retriever.rerank.model=다른모델`이 지문 불일치로 멈춘다
5. 테스트 split 질의를 읽는 명령(`rag.splits` 실행 포함)은 돌리지 않는다. A-3은 합성 입력 테스트로 확인한다. 외부 API(생성·judge)는 호출하지 않는다

## 수정 허용 파일

- `src/rag/index.py`, `retrieve.py`, `search.py`, `splits.py`, `rerank.py`, `generate.py`
- `src/rag/gen_eval/common.py`, `judge.py`, `report.py`, `review.py`
- `configs/config.yaml` (`adopt_basis: false` 키 하나)
- `tests/test_index.py`, `test_search.py`, `test_splits.py`, `test_rerank.py`, `test_generate.py`, `test_gen_eval.py`
- `docs/slices/15-artifact-guards.md`, `docs/PLAN.md`, `docs/reviews/2026-10-code-review.md`(진행 표시)

## 범위 밖

- 보호 경로(`src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`, `data/splits/`의 내용): 채점 결과의 분할 해시(A-3 일부), `--out` 덮어쓰기(D-3)
- 질의 임베딩 캐시의 지문(C-11, 낮음), BM25 옛 인덱스 분기(A-10), 다른 덮어쓰기 낮음 항목(A-7, B-12, D-4)
- 규칙 중복 정리(B-5, B-6, B-7, C-3, C-6)는 다음 묶음 SLICE
- 테스트 속도(E-1, E-2)

## 결과 (2026-10-21)

- 구현 커밋 35d521a. 테스트 197 → 210개, `uv run pytest -q`·`uv run ruff check .` 통과
- adopt(결정 사항 1): 기준 인덱스 4개(`snowflake-ko-fixed-512-64`·`snowflake-ko-fixed-256-32`의 dev-small·full)와 점수 파일 3개(`summary_q-dev-small`·`summary_q-full`·`multidoc-full`의 `ms256-k20-cross-encoder`)에 지문을 썼다. 쓰기 전에 대조한 것:
  - 인덱스: `meta.json`의 모델·`max_docs`, 청크 수와 조각 수가 `shard_size` 2048과 맞음, revision 고정(`configs/exp/exp009.yaml`, 10-13 15:09)과 코퍼스 수정(10-12)이 인덱스 생성(10-13·10-14)보다 앞섬. 512 청크는 KURE-v1 인덱스에서 복사했으므로(EXP-009) 네 인덱스 모두 청크 본문을 지금 코퍼스의 `[start:end]`와 전수 비교했다. 불일치 0, 문서 집합은 범위와 같다
  - 점수: 후보 쌍과 행 수·(qid, doc_id) 순서가 같고(20,780, 60,320, 12,000), 후보 쌍이 점수보다 먼저 만들어졌다. 모델·revision·`max_length`는 `configs/exp/exp017.yaml`, 실행 장치 cuda·float16은 EXP-017 실행 기록을 따랐다
- 결과 불변: `rag.search +exp=exp017`의 dev-small·dev-full·multi-doc 순위 파일이 모두 "같은 내용, 그대로 둠"
- 멈춤: `retriever.rerank.model=other/model` → 점수 지문 불일치(model), `embedding.revision=old` → 인덱스 지문 불일치(revision)
- 지문을 쓰지 않은 인덱스 5개와 점수 파일 5개(지난 EXP 재현용, test 1개 포함)는 그 EXP를 다시 돌릴 때 같은 대조를 거쳐 adopt한다
- judge 기록 전체(`judge.main`)를 돌리는 테스트는 두지 않았다. 질의 표본이 분할·정답 파일을 읽어 합성 입력으로 만들기 어렵다. 커밋을 뺀 비교는 `judge_recipe` 테스트로, 이어 쓰기 규칙은 기존 `done_qids` 테스트로 확인한다

### 리뷰 반영 (PR #122, 2026-10-21)

- 다시 만들면 내용이 달라지는 출력(judge 결과, 재정렬 채점·지연 측정)은 끝에서 `write_guarded`로 멈추면 작업 시간을 잃는다. 출력이 이미 있고 `search.overwrite`가 없으면 시작할 때 멈춘다(`rag.index.refuse_existing`). 검수 CSV의 확인도 이 함수로 바꿨다. 예: n=20 judge 결과가 있는 경로에 n=40으로 `rag.gen_eval.judge`를 실행하면 judge 호출 전에 "…가 있다. 덮어쓰려면 search.overwrite=true"로 멈춘다. 같은 커밋·같은 결과의 judge 재실행도 이제 멈춘다(응답이 모두 캐시에 있어 다시 돌릴 이유가 없는 경우)
