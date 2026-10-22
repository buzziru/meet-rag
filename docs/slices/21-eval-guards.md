# S21 평가 반복 전 리뷰 항목

생성 실험에서 채점·비교·생성 평가를 반복하기 전에, 코드 리뷰 2026-10(`docs/reviews/2026-10-code-review.md`)의 세 항목을 고친다(사용자 결정 2026-10-22, 이슈 #133, PLAN 리팩터링 절). 분할을 바꿀 일은 없지만, 평가를 반복할수록 기록이 조용히 덮이거나 다른 설정의 입력이 섞일 기회가 늘어난다. 검색 순위, 채점 지표, 생성 근거는 바뀌지 않아야 한다.

- A-3 채점 결과에 분할 파일 해시가 없다(`src/rag/eval/score.py:36`). S15는 `rag.splits`의 덮어쓰기 방지만 했다
- D-3 `--out` JSON과 G1 표본 CSV를 덮어쓴다(`eval/score.py:42`, `eval/compare.py:60`, `eval_multi/score.py:38`, `eval_multi/compare.py:64`, `sample_review.py:48-50`)
- C-11 질의 임베딩 캐시의 경로와 생성 레시피에 `embedding.revision`·`query_prompt`가 없다. `rag.search`는 캐시의 qid 목록만 대조하고(`search.py:101-109`), 생성(`generate.py:96`)과 생성 평가(`gen_eval/generate.py:33`)는 대조 없이 읽는다. revision이나 접두만 바꾸면 옛 질의 임베딩을 오류 없이 쓴다

A-3·D-3의 eval 모듈은 보호 경로(CLAUDE.md 금지 절: `src/rag/eval/`, `src/rag/eval_multi/`)라 결정 사항 1의 승인을 받은 뒤 고치고 DECISIONS에 기록한다.

## 만드는 것

### (a) 채점 결과에 정답 입력 파일 해시 (A-3)

- `rag.eval.metrics`에 평가 층의 정답을 만든 파일들의 sha256을 돌려주는 함수를 둔다. 대상은 결정 사항 2
- `rag.eval.score`의 `--out` JSON과 표준 출력, `rag.eval.compare`의 결과 JSON에 `gold_sha256`(파일 경로 → sha256)을 더한다. 지표 값과 판정은 바뀌지 않는다
- `rag.eval_multi`는 이미 동결 세트 해시(`frozen_sha256`)를 남기므로 고치지 않는다

### (b) `--out` 덮어쓰기 방지 (D-3)

- 네 명령(`rag.eval.score`, `rag.eval.compare`, `rag.eval_multi.score`, `rag.eval_multi.compare`)의 `--out` 쓰기를 `rag.index.write_guarded`로 바꾼다(결정 사항 3). 같은 입력이면 같은 JSON이 나오므로(bootstrap은 config의 seed) 내용이 같으면 그대로 두고, 다르면 멈춘다. `--overwrite` 인자를 더해 그때만 덮어쓴다. 멈출 때 안내는 `--overwrite`를 가리킨다
- `rag.sample_review`(G1 검수본의 원본 표본)는 시작할 때 `refuse_existing`으로 멈춘다(결정 사항 4). 이 명령은 config override를 받지 않으므로 덮어쓰는 길은 두지 않는다. 다시 뽑으려면 파일을 직접 옮긴다

### (c) 질의 임베딩 캐시 지문 (C-11)

- 질의 임베딩 캐시(`queries-*.npz`) 옆에 지문 파일 `<캐시 이름>.basis.json`을 둔다(재정렬 점수 `.basis.json`과 같은 방식, S15). 지문은 `embedding.model_name`, `embedding.revision`, `embedding.query_prompt`다(결정 사항 5)
- 캐시를 쓰는 곳(`rag.search`의 로컬 임베딩, VM의 `embed-queries`)은 npz와 지문을 함께 쓴다. VM에서 만든 캐시는 지문 파일도 함께 내려받는다. 이 내용을 `docs/slices/05-retrieve.md`의 VM 절차 줄에 더한다
- 캐시를 읽는 곳(`rag.search.query_embeddings`, `rag.generate`의 `dev_query`, `rag.gen_eval.generate`)은 한 함수를 거쳐 `rag.index.check_basis`로 지문을 대조한다. 지문이 없거나 다르면 멈춘다. 캐시를 읽는 코드가 세 곳에 따로 있던 것(리뷰 C-11 앞부분)도 이 함수 하나로 모은다
- 지문 없는 기존 캐시는 `rag.search adopt_basis=true`로 지문만 쓴다(결정 사항 6). npz를 열거나 임베딩하지 않는다
- 생성 레시피(`rag.generate.recipe`)에 `embedding_revision`, `query_prompt`를 더한다(결정 사항 7)
- 캐시 경로 템플릿(`configs/config.yaml`의 `paths.query_emb*`)은 바꾸지 않는다(결정 사항 5)

### 테스트

- (a) 합성 분할·질의 파일로 해시 함수가 층마다 대상 파일만 돌려준다. 파일 한 바이트를 바꾸면 해시가 바뀐다
- (b) `write_guarded` 경로: 같은 내용 두 번은 "그대로 둠", 다른 내용은 멈춤, `--overwrite`면 씀. 네 명령의 인자 파싱에 `--overwrite`가 있다. `sample_review`는 파일이 있으면 질의를 읽기 전에 멈춘다
- (c) 합성 npz로: 지문이 같으면 읽음, `revision`·`query_prompt`가 다르면 멈춤, 지문이 없으면 adopt 안내와 함께 멈춤. 캐시를 새로 쓰면 지문도 쓰인다. `adopt_basis=true`는 지문이 없을 때만 쓰고 기존 지문과 다르면 멈춘다. 레시피에 두 키가 들어간다
- 기존 테스트가 그대로 통과한다

## 결정 사항

1. **보호 경로 수정 승인 (A-3·D-3).** `src/rag/eval/metrics.py`, `eval/score.py`, `eval/compare.py`, `eval_multi/score.py`, `eval_multi/compare.py`를 위 (a)·(b) 범위로 고쳐도 되는지. 지표 계산, 판정 규칙, bootstrap 설정, `configs/eval/`, `data/splits/`는 바꾸지 않는다
   - (a) 승인: 위 범위로 고치고 DECISIONS에 D-45로 승인·범위·확인 결과를 적는다(S18의 D-43과 같은 형식)
   - (b) D-3만 승인: 덮어쓰기 방지만 하고 분할 해시는 하지 않는다. A-3은 리뷰 등급 낮음으로 남긴다
   - (c) 승인하지 않음: (c) 질의 캐시 지문과 `sample_review`만 한다
   - 추천은 (a)다
2. **해시를 남길 정답 입력 파일.** `load_gold`가 읽는 파일은 분할(`paths.splits`), 질의(`paths.queries`, 정답 doc_id), 코퍼스(`paths.corpus`, 회의명 층 나누기), dev-small 문서 목록(`paths.dev_small_docs`, dev-small 층만)이다
   - (a) 분할·질의·dev-small 목록: 어느 질의가 어느 층이고 정답이 무엇인지를 정하는 파일이다. 예: `rag.splits`를 다시 돌려 dev 구성이 바뀌거나 `rag.ingest`로 질의 파일이 바뀐 뒤 채점하면 `gold_sha256`이 이전 결과와 달라 두 결과 JSON을 대조하면 드러난다. 해시 시간은 채점 한 번에 약 0.8초다(지시서 작성 때 잰 값: 분할 141KB 0.0초, 질의 80MB 0.77초)
   - (b) (a) + 코퍼스: 회의명(`meeting_name`) 층 나누기 입력까지 남긴다. 코퍼스(289MB) 해시가 채점마다 약 2.6초 더 붙는다(같은 측정). 회의명은 S1 뒤 바뀐 적이 없다
   - (c) 분할 파일만: 리뷰 문구 그대로다. 질의 파일이 바뀐 경우는 남지 않는다
   - 추천은 (a)다
3. **`--out` 덮어쓰기 방식.**
   - (a) `write_guarded` + `--overwrite`: 예: EXP-017 dev-full 채점을 같은 `--out`으로 다시 돌리면 내용이 같아 "같은 내용, 그대로 둠"으로 끝난다. 다른 순위 파일을 같은 `--out`에 쓰면 쓰기 직전에 멈춘다. 이 조각 전에 쓴 결과 JSON은 (a)의 `gold_sha256`이 없어 같은 명령을 다시 돌려도 내용이 달라 멈춘다. 새 경로를 쓰거나 `--overwrite`로 갱신한다
   - (b) `refuse_existing`(시작할 때, 파일이 있으면 무조건 멈춤): 같은 명령을 다시 돌려도 멈춘다. 채점·비교는 수 초\~수십 초라 끝에서 멈춰도 잃는 시간이 작아 (b)의 장점이 작다
   - 추천은 (a)다. 구현 원칙의 구분(같은 입력이면 같은 내용 → `write_guarded`)과 맞다
4. **`sample_review`를 이 조각에 넣을지.** G1은 끝났고(D-03) 이 명령은 CLAUDE.md 명령 목록에 없다. 검수를 채운 파일은 따로 있고(`data/review/g1_summary_q_evaluated.csv`), 이 명령이 쓰는 것은 그 원본인 빈 표본 `data/review/g1_summary_q.csv`다
   - (a) 넣는다: 시작할 때 `g1_sample` 파일이 있으면 멈춘다. 예: `g1_sample_size`나 `seed`를 바꾼 뒤 `rag.sample_review`를 돌리면 검수본과 다른 표본으로 원본을 덮어쓰는 대신 바로 멈춘다. 코드 한 줄과 테스트 하나다
   - (b) 넣지 않는다: 리뷰 표의 D-4로 남긴다. 검수본은 덮이지 않으므로 잃는 것은 검수본의 원본 표본뿐이다
   - 추천은 (a)다. 보호 경로 밖이고 비용이 작다
5. **질의 캐시 지문을 어디에 둘지.**
   - (a) 지문 파일(`queries-full.npz.basis.json` 등): 경로는 그대로다. 예: `embedding.revision`을 바꾼 config로 `rag.search`를 돌리면 캐시 지문의 revision이 달라 "지문이 지금 설정과 다르다(revision)"로 멈춘다. 지문 없는 기존 캐시 6개는 결정 사항 6으로 지문만 붙인다
   - (b) 경로에 넣는다(`queries-${index.scope}-<revision·접두 해시>.npz` 등): 설정이 다르면 다른 파일을 찾아 새로 임베딩한다. 기존 캐시 6개는 이름을 직접 바꾸거나 다시 임베딩해야 한다. full·multi-doc 캐시는 Colab GPU로 만들었다(S5·S9 실행 기록). 로컬 CPU로 다시 만들면 부동소수 연산 순서가 달라 값이 조금 바뀌고 기존 순위 파일이 재현되지 않을 수 있다(확인하지 않음, 추론). `revision: null`과 접두 문자열을 경로 템플릿에 넣을 방법도 따로 만들어야 한다
   - 추천은 (a)다. 인덱스 `basis.json`·재정렬 점수 `.basis.json`과 같은 장치라 새로 만들 것이 없다
   - 지문 키에 `query_max_tokens`, `normalize`는 넣지 않는다. 리뷰가 지적한 키가 아니고 지금까지 바꾼 실험이 없다(인덱스 지문에도 없다). 필요해지면 키만 더한다
6. **지문 없는 기존 캐시 받아들이기.** 대상은 `data/index/kure-v1/`, `data/index/snowflake-ko/`의 `queries-dev-small.npz`, `queries-full.npz`, `queries-multidoc.npz` 6개다. `queries-test.npz` 2개는 test 1회가 끝나(D-39) 다시 읽지 않으므로 지문을 붙이지 않는다
   - (a) 실행 기록과 대조한 뒤 `adopt_basis=true`로 지문만 쓴다(S15 결정 사항 1과 같은 방식): kure-v1 캐시는 S4·S5·S9의 기본 설정(revision 없음, 접두 없음), snowflake-ko 캐시는 EXP-009 설정(revision `55ec6e9…`, 접두 `query: `)으로 만들었는지 각 SLICE·EXP 문서와 커밋의 config로 확인하고 결과 절에 근거를 적는다. 명령 예: `uv run python -m rag.search +exp=exp017 index.scope=full search.queries=multidoc adopt_basis=true`는 `data/index/snowflake-ko/queries-multidoc.npz.basis.json`만 쓰고 끝난다. 지문이 이미 있으면 같은지만 본다
   - (b) 지문 없이 읽으면 경고만 내고 진행한다: 장치는 작지만 잘못된 캐시가 경고와 함께 쓰인다. S15는 이 방식을 쓰지 않았다
   - 추천은 (a)다
7. **생성 레시피에 두 키를 더할지.** 레시피는 생성 기록마다 남고, `rag.gen_eval.generate`는 같은 경로의 기존 기록과 레시피가 다르면 멈춘다(`gen_eval/common.py:51-60`)
   - (a) 더한다: 리뷰 3c(레시피에 빠진 입력)가 지적한 대로 생성 기록만 보고 질의 임베딩 설정을 알 수 있다. 대신 기존 생성 기록 `data/gen_eval/runs/hybrid-cond-filter-law-ms256-k20-ce-v1-dev-small.jsonl`(S14 표본 20건)에 같은 경로로 이어 생성하면 "다른 레시피"로 멈춘다. 예: `gen_eval.n=30`으로 늘려 10건을 더 생성하려면 `search.overwrite=true`로 새로 만들거나 경로를 바꿔야 한다. 기존 기록을 읽는 judge·report는 영향이 없다(기록 안의 레시피끼리만 대조). 판정용 세트는 D-44로 dev-full 표본으로 바뀌어 새 경로에 생성한다
   - (b) 더하지 않는다: 캐시 지문 대조가 읽는 시점에 막으므로 생성 기록의 내용은 지금과 같다. 기록만 보고는 revision·접두를 알 수 없고, 같은 `embedding.slug`에서 지문을 바꿔 다시 만든 캐시와 구분하지 못한다
   - 추천은 (a)다. 생성 베이스라인 전이라 다시 생성할 기록이 S14 표본뿐이다

결정: 1\~7 모두 추천안(사용자 결정 2026-10-22). 1 (a)로 보호 경로 수정을 위 범위로 승인받았다. 수정 허용 목록에서 뺀 S14c 파일에 필요한 작업은 결과 절에 적어 두고, S14c 작업이 끝나면 사용자에게 알린다(같은 지시).

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. 채점 불변: `main`과 이 브랜치에서 `rag.eval.score`(dev-small·dev-full, EXP-017 순위), `rag.eval.compare`(EXP-014 대 EXP-017), `rag.eval_multi.score`·`compare`(같은 쌍의 multi-doc 순위)를 `data/` 밖 임시 경로에 `--out`으로 쓰고, 새로 더한 `gold_sha256`을 뺀 내용이 같다
3. 덮어쓰기: 2의 명령을 같은 `--out`으로 다시 돌리면 "같은 내용, 그대로 둠", 다른 순위 파일을 같은 `--out`에 쓰면 멈추고, `--overwrite`면 쓴다(네 명령 모두)
4. 질의 캐시: 결정 사항 6을 마친 뒤 `rag.search +exp=exp017`의 dev-small·full·multi-doc이 기존 순위 파일과 "같은 내용, 그대로 둠". 기본 설정(kure-v1) dev-small 검색도 같다. `embedding.query_prompt`를 바꾼 override로 돌리면 임베딩 전에 지문 불일치로 멈춘다
5. 생성 근거 불변: S20 완료 기준 4와 같이 기존 생성 기록 20건의 qid로 `Pipeline.retrieve`만 불러(생성 API 호출 없음, `LANGSMITH_TRACING=false`) 근거 dict가 기록과 같다. 새 레시피에 두 키가 들어간다
6. test 분할 질의를 읽는 명령과 외부 API는 돌리지 않는다

## 수정 허용 파일

- `src/rag/eval/metrics.py`, `src/rag/eval/score.py`, `src/rag/eval/compare.py`, `src/rag/eval_multi/score.py`, `src/rag/eval_multi/compare.py` (결정 사항 1 승인 범위)
- `src/rag/sample_review.py` (결정 사항 4)
- `src/rag/index.py`, `src/rag/retrieve.py`, `src/rag/search.py`, `src/rag/generate.py`, `src/rag/gen_eval/generate.py` (`retrieve.py`는 구현 때 더했다. 캐시 읽기 함수를 생성·검색이 함께 쓰는 곳에 두었다. 감사 지적으로 목록을 맞춤)
- `tests/test_eval.py`, `tests/test_eval_multi.py`, `tests/test_sample_review.py`, `tests/test_search.py`, `tests/test_generate.py`, `tests/test_index.py`
- `docs/slices/21-eval-guards.md`, `docs/slices/05-retrieve.md`(VM 절차 한 줄), `docs/DECISIONS.md`(D-45), `docs/PLAN.md`, `CLAUDE.md`(명령 줄에 `--overwrite`)

## 범위 밖

- `src/rag/gen_eval/judge.py`·`checks.py`·`report.py`, `configs/judge/`, `tests/test_gen_eval.py` (S14c 세션이 작업 중)
- 질의 캐시의 qid 목록이 다를 때 로컬에서 다시 임베딩해 덮어쓰는 기존 동작(`query_embeddings`). Colab에서 만든 캐시가 CPU 값으로 바뀌는 경로지만 이번 리뷰 항목이 아니다. 관찰로 남긴다
- 리뷰 등급 낮음의 나머지(A-7, D-1·D-6·D-7·D-9·D-10·D-11, B-8 나머지). PLAN 결정대로 고치지 않는다
- test 질의 임베딩 캐시 2개의 지문

## 결과 (2026-10-22)

- 커밋: (a)·(b) fcca03e, (c) 46a317f. 테스트 255 → 262개, `uv run pytest -q`·`uv run ruff check .` 통과
- 채점 불변: `main`(3c6ed6f)과 이 브랜치에서 EXP-017 순위로 `rag.eval.score`(dev-small·dev-full), `rag.eval.compare`(EXP-014 대 EXP-017), `rag.eval_multi.score`·`compare`(같은 쌍의 multi-doc)를 임시 경로에 써, `gold_sha256`을 뺀 JSON 5개가 모두 같다. 기록된 해시: 분할 `091235be…`, 질의 `1643b047…`, dev-small 목록 `7803c4a7…`
- 덮어쓰기: 같은 `--out`으로 다시 돌리면 "같은 내용, 그대로 둠", 다른 순위를 같은 `--out`에 쓰면 "내용이 다른 파일이 있다. 덮어쓰려면 --overwrite"로 멈추고(종료 코드 1), `--overwrite`면 "씀"(score·compare·eval_multi compare를 실제 파일로, 네 명령 모두 합성 파일 테스트로)
- 기존 캐시 받아들이기(결정 사항 6): kure-v1 캐시 3개는 2026-10-01\~08에 만들었고, `embedding.revision`·`query_prompt` 지원은 2026-10-13 d4fbd41에서 들어왔다(그 전 `encoder`는 접두를 붙이지 않았고 모델을 revision 없이 불렀다). snowflake-ko 캐시 3개는 2026-10-13 16:27·17:26에 만들었고, `configs/exp/exp009.yaml`(revision `55ec6e9…`, 접두 `query: `)은 같은 날 15:09 5ec9de6 뒤 바뀌지 않았다. EXP-009 실행 기록(dev·G3 질의는 VM `embed-queries +exp=exp009`, dev-small은 로컬)과 맞다. 이 대조로 `rag.search [+exp=exp017] index.scope=… adopt_basis=true` 6회로 지문을 썼다(모두 "씀")
- 질의 캐시: `rag.search +exp=exp017`의 dev-small·dev-full·multi-doc이 기존 순위 파일과 "같은 내용, 그대로 둠". `embedding.query_prompt='passage: '` override는 임베딩 전에 "지문이 지금 설정과 다르다(query_prompt)"로 멈춘다. 기본 설정(kure-v1) dev-small 검색은 완료 기준 4대로 돌리지 못했다. kure-v1 인덱스에 S15 인덱스 지문(`basis.json`)이 없어 질의 캐시 전에 멈추고, 이 동작은 이 조각 전 코드(`rag.retrieve`의 인덱스 지문 대조, S15)다. 대신 kure-v1 질의 캐시 3개를 `read_query_emb`로 기본 설정에서 읽어 지문 대조를 통과하는 것을 확인했다(1,039·3,016·600행)
- 생성 근거 불변: 기존 생성 기록 20건의 근거 dict가 20/20 같다(`LANGSMITH_TRACING=false`, 생성 API 호출 없음. `Pipeline`이 클라이언트를 만들 때 읽는 키 환경 변수에는 더미 값을 넣었다). 새 레시피에 `embedding_revision`(`55ec6e9…`), `query_prompt`(`query: `)가 들어간다
- 결정 사항 7의 영향: 이 기록은 S15 전에 만들어 레시피에 `conditions`·`name_titles`·`rerank_scores_sha256`도 없다. 같은 경로에 이어 생성할 수 없는 상태는 이 조각 전(S15)부터였다
- 수정 허용에서 뺀 S14c 파일(`gen_eval/judge.py`·`checks.py`·`report.py`, `configs/judge/`, `tests/test_gen_eval.py`): 이 조각 때문에 고칠 것은 없다. judge는 생성 기록 안의 레시피끼리만 대조하고 `gen_recipe_sha256`만 남겨, 새 키가 생기면 새 생성 기록의 해시가 바뀔 뿐이다(S14c 브랜치 diff로 확인, 2026-10-22). 두 브랜치가 함께 고치는 파일은 `docs/PLAN.md`(서로 다른 줄)다
- 관찰: 질의 목록이 다른 캐시를 로컬에서 다시 임베딩해 덮어쓰는 기존 동작(범위 밖)은 그대로다
- 관찰: VM에서 만든 캐시는 `colab_job.py fetch`가 VM 디렉터리를 묶어 받으므로(`.claude/skills/meet-rag/scripts/colab_job.py:222`) 캐시 디렉터리를 받으면 지문 파일도 함께 온다. 파일 하나만 `colab download`로 받으면 지문이 빠지고, 다음 실행이 지문 없음으로 멈춘다(오염은 아님)
- 관찰: test 질의 캐시 2개에는 지문이 없어 `search.queries=test`로 읽으면 멈춘다. 생성 단계 test 1회는 검색 순위를 다시 만들지 않으면 해당하지 않고, 다시 만들 때는 그 준비에서 받아들이거나 다시 임베딩한다
