# S9 다중 정답 채점과 기준선 측정

G3 동결 세트(`paths.multidoc_frozen`, 600건, D-15)를 SPEC "보조 관찰: multi-doc 질의" 절대로 채점하는 모듈을 만들고, 베이스라인 dense 검색(512/64 전체 인덱스)의 multi-doc 점수를 낸다. 판정 라벨은 붙이지 않는다. 완료 후 `src/rag/eval_multi/`는 수정 금지 대상이다.

## 만드는 것

- `src/rag/eval_multi/metrics.py`: 동결 세트 읽기, 순위 파일 읽기·검증, 질의별 Recall@k·Complete@k·Hit@k, 유형별 표
- `src/rag/eval_multi/score.py`: 순위 파일 하나를 채점하는 명령
- `src/rag/eval_multi/compare.py`: 기준·후보 순위 파일의 지표 차이를 묶음 단위 paired bootstrap 구간으로 내는 명령
- `src/rag/search.py`: 검색할 질의 세트를 고르는 `search.queries`(`summary_q` 기본, `multidoc`)를 더한다
- `notebooks/09_01_multidoc기준선.ipynb`: 기준선 점수와 세부 분석. k 수정 의견의 근거다

`src/rag/eval/`은 고치지 않는다. 가져다 쓰는 것은 `rag.eval.bootstrap.paired_bootstrap` 하나다.

## 입력

### 동결 세트

`paths.multidoc_frozen`(jsonl). 쓰는 필드는 `qid`, `type`, `pool_id`, `gold_doc_ids`이고, 검색에서만 `query`를 읽는다. 노트북은 분석에 `pool_doc_ids`와 실패 사례 몇 건의 `query`도 읽는다. `answer`·`elements`는 검수하지 않은 자료라 읽지 않는다(D-15 단서). 정답 문서 수는 2개 391건, 3개 143건, 4개 50건, 5개 16건이다.

### 순위 파일

CSV, 열 `qid`, `rank`, `doc_id`. 검증 규칙은 S3와 같다.

- 같은 `qid`에서 `doc_id`가 여러 번 나오면 가장 작은 `rank`만 남기고 1부터 다시 매긴다
- 다음은 오류로 멈춘다: 동결 세트의 `qid`가 순위 파일에 없음, 동결 세트에 없는 `qid`가 있음(summary_q 순위 파일을 잘못 준 경우 포함), 중복 제거 후 서로 다른 문서가 `max(ks)` 미만인 질의, 같은 `qid`에서 `rank` 중복

## 규칙

### 지표

파라미터는 `configs/config.yaml`의 `multidoc.eval`에서 읽는다(`ks: [5, 10]`, `breakdowns: [type]`). 보호 경로 `configs/eval/`에 두지 않는 것은 기준선을 본 뒤 k를 바꿀지 정하기 때문이다. S9 완료 후에는 이 값도 바꾸지 않는다.

질의 `q`의 정답 집합을 `G`, 상위 k 문서 집합을 `R_k`라 하면

- Recall@k = `|G ∩ R_k| / |G|`의 평균
- Complete@k = `G ⊆ R_k`인 질의의 비율
- Hit@k = `|G ∩ R_k| ≥ 1`인 질의의 비율

표는 전체 한 줄과 `breakdowns` 열 값마다 한 줄이고, 각 줄에 질의 수와 지표를 적는다. 정답 문서가 5개인 질의는 k=5에서 다섯 개가 모두 상위 5위에 있어야 Complete가 된다(`max_gold` 5, D-14).

### 비교

SPEC은 multi-doc을 판정에 쓰지 않으므로 `compare`는 채택·기각·보류를 내지 않는다.

1. 두 순위 파일을 각각 채점해 질의별 지표 값을 얻는다
2. 지표마다 질의별 차이 `c_i - b_i`를 `paired_bootstrap(diff, groups=pool_id, ...)`에 넣는다. `n_resamples`, `seed`, `alpha`는 `configs/eval/spec_v1.yaml`의 `bootstrap`에서 읽는다(SPEC "반복 횟수와 seed는 판정 절과 같다"). 같은 절의 `unit`(`conference_number`)은 single-doc 판정용이라 읽지 않는다
3. 전체와 유형별로 점 추정과 95% 구간을 낸다

재표본 단위는 SPEC대로 질의를 만든 묶음(`pool_id`)이다. 동결 세트는 후보 집합 하나에서 질의를 하나만 만들어(600건, `pool_id` 600개) 이 단위는 질의 단위와 같다.

### 출력

- `score`: 지표 표를 마크다운으로 출력하고 `--out`이면 JSON으로 저장한다
- `compare`: 두 실행의 전체 지표, 지표별 차이와 95% 구간을 출력하고 `--out`이면 JSON으로 저장한다
- 출력에 순위 파일과 동결 세트의 SHA-256을 함께 적는다

### 검색

- `search.queries=multidoc`은 `index.scope=full`에서만 쓴다. 정답 문서가 dev 회의 전체에 걸쳐 있어 dev-small 인덱스로는 채점할 수 없다
- 질의 목록과 순서는 동결 세트 파일 순서다. 질의 임베딩 캐시는 `paths.query_emb_multidoc`(`data/index/{임베딩}/queries-multidoc.npz`)에 두고 다시 쓴다
- Colab 임베딩은 S5와 같은 `search.mode`를 쓴다. `export-queries`가 동결 세트의 `qid`·`query`만 `paths.queries_multidoc_vm`에 쓰고, VM의 `embed-queries`가 그 파일만 읽어 캐시를 만든다
- 순위 파일은 `data/runs/{인덱스 이름}-multidoc.csv`다. 문서 순위·`top_k`·`chunk_pool`은 S5와 같다
- 기본값 `summary_q`의 동작과 출력 파일은 바뀌지 않는다

### 질의 임베딩 (사용자 결정)

600건(평균 약 100자)을 어디서 임베딩할지 정한다.

- (권고) 로컬 CPU `float32`. dev-small 질의도 로컬 CPU로 임베딩했고(S4), Colab 승인·업로드가 필요 없다. 질의가 짧아 GPU 이점이 작다. 소요 시간은 측정하지 않았다
- Colab T4. dev-full 질의(D-07)와 같은 방식이다. 이 경우 `colab_job.py upload`의 dev 검사가 summary_q 분할을 기준으로 하므로 `md-` `qid`를 어떻게 확인할지 따로 정해야 한다

summary_q dev-full 질의는 T4 `float32`로 임베딩했다. 정밀도가 같아 어느 쪽이든 결과 차이는 수치 오차 수준으로 본다.

### 노트북과 결정 순서

1. 검색·채점이 끝나면 `notebooks/09_01_multidoc기준선.ipynb`를 쓴다
   - 데이터: 유형별 질의 수, 정답 문서 수 분포
   - 평가: 전체·유형별 Recall·Complete·Hit@5·10, 정답 문서 수별 표, 지표 수준의 95% 구간(질의 값 자체를 `paired_bootstrap`에 넣는다), 정답 문서의 순위 분포(10위 밖 비율)
   - `law`: 한 번만 재판정한 71건과 두 번 판정한 81건을 나눈 표(D-15 단서)
   - 실패 사례: Hit@10이 0인 질의 몇 건의 유형·정답 문서·1위 문서(질의 원문은 소량만 출력)
2. 노트북을 사용자에게 보이고 기준선 점수와 k 수정 의견을 보고한다. k를 바꾸면 SPEC 지표 절 수정이라 사용자 승인 후 SPEC·config·DECISIONS를 함께 고친다
3. 결정을 반영한 뒤 검증·감사를 거쳐 PR을 올린다

## 명령

```
uv run python -m rag.search index.scope=full search.queries=multidoc
uv run python -m rag.eval_multi.score --run data/runs/kure-v1-fixed-512-64-multidoc.csv [--out <결과.json>]
uv run python -m rag.eval_multi.compare --base <기준.csv> --cand <후보.csv> [--out <결과.json>]
```

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q` | 통과. 테스트는 합성 입력만 쓰고 `data/`를 읽지 않는다. 포함: 손으로 계산한 Recall·Complete·Hit@5·10, 정답 문서가 일부만 든 질의에서 세 지표가 다름, 청크 중복 `doc_id` 제거 후 재순위, 누락 `qid`·세트 밖 `qid`·문서 하한 미만·`rank` 중복은 오류, `ks`를 바꾸면 하한이 따라 바뀜, 같은 파일끼리 비교하면 차이 0·구간 [0, 0], 재표본이 `pool_id` 단위, 같은 seed로 두 번 돌리면 구간이 같음, `search.queries=multidoc`이 `index.scope=dev-small`에서 오류 |
| 2 | `uv run ruff check .` | 통과 |
| 3 | 오라클 순위 파일(정답 문서를 앞에, 나머지를 정답이 아닌 코퍼스 문서로 채움)로 `score` | 모든 지표 1.0, 유형별 질의 수 합 600 |
| 4 | 정답 문서 중 첫 번째만 1위에 두고 나머지 정답 문서는 넣지 않은 10개 순위 파일로 `score` | Hit@5·10 1.0, Complete@5·10 0.0, Recall@k는 `mean(1/|G|)` |
| 5 | `compare --base <4의 파일> --cand <3의 파일>` | Complete 차이 +1.0, 구간 [1.0, 1.0], 판정 라벨 없음 |
| 6 | 5를 두 번 실행 | 출력 일치 |
| 7 | 기준선 검색을 두 번 실행 | 순위 파일 SHA-256 일치(두 번째는 질의 임베딩 캐시 사용) |
| 8 | `score`에 summary_q dev-full 순위 파일을 넣음 | 오류로 멈춤 |

3\~6의 순위 파일은 검증 중에 동결 세트의 `gold_doc_ids`와 `paths.corpus`로 만든다. 질의 텍스트는 쓰지 않는다.

## 수정 허용 파일

- `src/rag/eval_multi/`, `tests/test_eval_multi.py`
- `src/rag/search.py`, `tests/test_search.py`
- `configs/config.yaml`(`multidoc.eval`, `search.queries`, `paths.query_emb_multidoc`, `paths.queries_multidoc_vm`)
- `notebooks/09_01_multidoc기준선.ipynb`
- `CLAUDE.md` "명령" 절(채점·비교 명령), `docs/PLAN.md` S9 체크, `docs/DECISIONS.md`(기준선·k 결정), 이 문서

## 범위 밖

- `src/rag/eval/`, `configs/eval/`, `data/splits/` 수정
- 동결 세트 수정, `answer`·`elements` 사용(생성 평가)
- dense 외 검색기의 multi-doc 점수(EXP-001부터 EXP 문서에서 함께 보고)
- `test` 분할 질의

## 실행 기록

- 질의 임베딩: Colab T4 세션 `meet-rag-s09q`, 2026-10-08 14:29\~14:34(약 5분), 커밋 53fa5e9. Python 3.12.3, torch 2.13.0+cu126, transformers 5.14.1, sentence-transformers 5.6.1. 업로드는 `data/multidoc/queries_g3.vm.jsonl`(`qid`·`query`, 600건) 하나다. compute unit은 약 0.09(T4 요율 1.04 CU/시간 × 세션 약 5분, 사용자 지시로 계산)
- 검색: 600건, 전체 정렬로 넘어간 질의 0건. 순위 파일 SHA-256 `8f14dc808c16b94afac5b4167c7e63088a27410290e1f113135d537643bf8289`
- 결과와 k 결정: D-16, `notebooks/09_01_multidoc기준선.ipynb`
