# S5 dense 검색과 평가

S4의 512/64 인덱스로 dev-small·dev-full 질의를 검색해 순위 파일을 만들고 `rag.eval.score`로 채점한다. 이 점수가 베이스라인이다. 결과를 노트북으로 정리한 뒤, 그 노트북을 근거로 SPEC 미결 2(수치 목표)를 사용자가 정한다.

## 만드는 것

- `src/rag/search.py`: dev-small 전용이던 검색을 `index.scope=full`(dev-full 질의)까지 넓히고, dev 질의 파일 내보내기와 질의 임베딩만 하는 실행 방식을 더한다
- `notebooks/05_01_베이스라인검색.ipynb`: dev-full 베이스라인 점수와 세부 분석. 결정 기록보다 먼저 쓴다

## 규칙

### 검색 방식

- naive 단계는 numpy 전수 검색(exact kNN)을 쓴다(사용자 결정 2026-10-01). 질의마다 모든 청크와 내적을 계산한다. ANN·벡터 DB는 배포 단계나 별도 실험에서 정한다
- 범위와 평가 층의 대응: `index.scope=dev-small` → dev-small 질의, `index.scope=full` → dev-full 질의. `test` 질의는 읽지 않는다
- 전체 인덱스는 118,039청크(float32 약 480MB)다. 질의를 `retriever.query_batch`개씩 나눠 내적한다. 256개면 점수 행렬이 약 120MB로 로컬 RAM 8GB에 들어간다

### 문서 순위와 `chunk_pool`

- 문서 순위는 S4와 같다. 청크 점수 내림차순에서 문서가 처음 나온 순서로 상위 `retriever.top_k`개 문서를 고른다
- 전체 청크를 정렬하지 않고 점수 상위 `retriever.chunk_pool`개 청크만 정렬해 문서를 고른다. 그 안에서 서로 다른 문서가 `top_k`개보다 적으면 그 질의만 전체 청크를 정렬한다. 그래서 `chunk_pool`은 속도에만 영향을 주고 결과는 전체 정렬과 같다(점수가 정확히 같은 청크가 경계에 걸리는 경우는 제외)
- 값은 200으로 점수를 보기 전에 정한다. 전체 인덱스에서 문서당 청크는 중앙값 3, 최대 95라 상위 200청크에 서로 다른 문서 10개가 없는 질의는 드물 것으로 본다. 전체 정렬로 넘어간 질의 수를 출력한다

### 질의 임베딩

- dev-full 질의 3,016건은 Colab T4에서 임베딩한다(사용자 지시, D-07). 질의가 짧아 L4가 필요 없다. 정밀도는 dev-small 질의(로컬 CPU)와 같은 `float32`로 둔다
- `search.mode`로 실행 방식을 고른다
  - `run`(기본): 검색과 순위 파일 쓰기. 질의 임베딩 캐시가 없거나 질의 목록이 다르면 로컬에서 임베딩한다
  - `export-queries`(로컬): dev 질의를 `paths.queries_dev`(`data/processed/queries_summary_q.dev.jsonl`)로 내보낸다. jsonl에 `qid`·`query` 키만 쓰고(답변 등 다른 필드는 VM에 보내지 않는다) dev-full 채점 순서(`load_gold`)를 따른다. `test` 질의는 들어가지 않는다
  - `embed-queries`(VM): `paths.queries_dev`만 읽어 임베딩하고 `paths.query_emb`에 저장한다. 원본 질의 파일과 분할 파일을 읽지 않아 VM에 둘 필요가 없다. `index.scope=full`에서만 쓴다
- VM에 올리는 입력은 `queries_summary_q.dev.jsonl` 하나다. `colab_job.py upload`가 모든 `qid`가 dev인지 확인한다. 코퍼스·인덱스는 올리지 않는다
- 캐시는 `data/index/{임베딩}/queries-{범위}.npz`다. dev-small 캐시(`queries-dev-small.npz`)는 경로가 그대로라 S4 결과를 다시 쓴다
- Colab 절차는 meet-rag 스킬 E절을 따른다. T4 요율은 사용자가 실행 때 웹 화면에서 확인해 알려 준다

### 출력

- 순위 파일: `data/runs/{인덱스 이름}-{평가 층}.csv`(`qid`, `rank`, `doc_id`). dev-small 파일 이름은 S4와 같다
- 채점: `rag.eval.score --layer dev-full --out data/runs/{인덱스 이름}-dev-full.json`

### 노트북과 결정 순서

노트북은 프로젝트 결정의 근거 자료이므로 결정을 기록하기 전에 쓴다(PR #15 사용자 코멘트).

1. 검색·채점이 끝나면 `notebooks/05_01_베이스라인검색.ipynb`를 쓴다
   - 데이터: dev-full 질의 수, 회의 수, 회의구분·`qna_type` 분포
   - 검색: 질의 하나의 상위 5개, `chunk_pool` 전체 정렬로 넘어간 질의 수, 질의 일부에서 전체 정렬 결과와 같은지
   - 평가: Recall@1·5·10, MRR@10, 회의구분·`qna_type`별 표, 정답 순위 분포, Recall@5 회의 단위 bootstrap 95% 구간
   - 실패 사례: 정답이 상위 10위 밖인 질의 몇 건의 질의·정답 문서·1위 문서(질의 원문은 소량만 출력)
   - dev-small 점수는 별도 표로 둔다. SPEC에 따라 dev-full과 비교하지 않는다
2. 노트북을 사용자에게 보이고 SPEC 미결 2(수치 목표)를 정한다. 정하는 것은 사용자다
3. `docs/DECISIONS.md`에 검색 방식(전수 검색, `chunk_pool`)과 수치 목표를 기록한다. SPEC 미결 절의 해결 표시는 사용자 승인 후 한다

## 명령

```
uv run python -m rag.search index.scope=full search.mode=export-queries            # 로컬
uv run python -m rag.search index.scope=full search.mode=embed-queries embedding.device=cuda   # VM
uv run python -m rag.search [index.scope=dev-small|full]                              # 로컬 검색
uv run python -m rag.eval.score --run data/runs/kure-v1-fixed-512-64-dev-full.csv --layer dev-full --out data/runs/kure-v1-fixed-512-64-dev-full.json
```

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q` | 통과. 합성 입력만 쓴다. 포함: `chunk_pool`을 쓴 문서 순위가 전체 정렬 결과와 같음(무작위 점수, 전체 정렬로 넘어가는 경우 포함), 질의 배치 크기가 결과를 바꾸지 않음 |
| 1a | `rag.search index.scope=full search.mode=export-queries` | `queries_summary_q.dev.jsonl` 3,016행, 모든 `qid`가 dev, 순서가 `load_gold(dev-full)`와 같음 |
| 1b | Colab에서 만든 `queries-full.npz` | 행 수 3,016, `qids`가 1a 순서와 같음, 노름 1, NaN 없음 |
| 2 | `uv run ruff check .` | 통과(노트북 포함) |
| 3 | `rag.search index.scope=dev-small` | 순위 파일 SHA-256이 S4 결과(`1102ce66…29a8`)와 같음 |
| 4 | `rag.search index.scope=full` | 순위 파일이 `rag.eval.score --layer dev-full` 검증을 통과(질의 3,016건, 질의당 문서 10개) |
| 5 | 4와 채점을 두 번 실행 | 순위 파일 SHA-256과 채점 결과 일치 |
| 6 | 노트북 처음부터 실행 | 오류 없음, 수치가 5의 채점 결과와 같음 |
| 7 | 문서 기록 | DECISIONS에 검색 방식과 수치 목표, `CLAUDE.md` "명령"에 dev-full 검색, PLAN S5 체크. 이 문서 "실행 기록"에 Colab 세션 시간·compute unit·VM 패키지 버전과 로컬 검색 시간 |

## 실행 기록

| 날짜 | 작업 | GPU·장치 | 세션·실행 시간 | compute unit | 비고 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-02 | dev-full 질의 3,016건 임베딩(`embed-queries`, float32) | Colab T4 | 세션 약 6분(15:44:31~15:50:18, setup 1분 미만, 임베딩은 모델 로드 포함 2분 이내) | 요율 1.04 CU/시간 환산 약 0.10 | `uv sync --extra cu126`: Python 3.12.3, torch 2.13.0+cu126, transformers 5.14.1, sentence-transformers 5.6.1. 업로드는 `queries_summary_q.dev.jsonl`(`qid`·`query`, 635KB) 하나 |
| 2026-10-02 | dev-full 검색 | 로컬 CPU | 18~19초(두 번), 전체 정렬로 넘어간 질의 0건 | - | 순위 파일 SHA-256 `f1568843…bbe2` 두 번 일치, 채점 결과 일치 |

## 수정 허용 파일

- `src/rag/search.py`, `tests/test_search.py`
- `configs/config.yaml`(`paths.query_emb`·`paths.queries_dev`, `search` 절), `configs/retriever/dense.yaml`(`chunk_pool`, `query_batch`)
- `notebooks/05_01_베이스라인검색.ipynb`
- `docs/DECISIONS.md`, `docs/PLAN.md` S5 체크, `CLAUDE.md` "명령" 절, 이 문서
- `docs/SPEC.md` 미결 2 해결 표시(사용자 승인 후에만)

## 범위 밖

- ANN 인덱스·벡터 DB, 재순위화, 하이브리드 검색(백로그)
- 코퍼스 재임베딩(Colab은 질의 임베딩에만 쓴다)
- `test` 분할 검색·채점
- `configs/eval/`, `src/rag/eval/`, `data/splits/` 수정
- 생성(S6)
