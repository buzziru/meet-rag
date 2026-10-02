# S4 청킹·임베딩·인덱스

코퍼스를 고정 토큰 길이로 나누고 KURE-v1로 임베딩해 인덱스로 저장한다. dev-small에서 청크 크기 후보 네 개를 비교해 `chunk_tokens`·`overlap_tokens`를 정하고, 정한 설정으로 전체 코퍼스 인덱스를 만든다. 임베딩은 Colab L4에서 하고, 할당이 실패하면 T4로 바꾼다(meet-rag 스킬 E절).

## 만드는 것

- `src/rag/chunking.py`: 문서 하나를 토큰 길이 기준 청크로 나눈다
- `src/rag/index.py`: 범위(`dev-small`·`full`)의 문서를 청킹·임베딩해 인덱스 디렉터리에 저장한다. 중간에 끊겨도 이어서 만든다
- `src/rag/search.py`: 평가 층 질의를 임베딩하고 인덱스를 전수 검색해 순위 파일을 쓴다(dev-small 전용)
- `src/rag/chunk_sweep.py`: 후보별 순위 파일을 채점해 비교표를 출력한다

## 규칙

### 청킹

- 토크나이저는 `embedding.model_name`의 것을 쓴다. 특수 토큰을 뺀 본문 토큰으로 길이를 센다
- 청크 `i`는 토큰 `[i·s, i·s + chunk_tokens)`이고 `s = chunk_tokens − overlap_tokens`다. 마지막 청크가 문서 끝을 덮으면 멈춘다
- 청크 텍스트는 토큰 offset으로 원문 `context`를 잘라 얻는다. 토큰을 다시 문자열로 바꾸면 공백·문자가 원문과 달라질 수 있어서다
- 문서가 `chunk_tokens` 이하이면 청크 하나다

### 후보

| 후보 | `chunk_tokens` | `overlap_tokens` |
| --- | ---: | ---: |
| 256 | 256 | 32 |
| 512 | 512 | 64 |
| 1024 | 1024 | 128 |
| 자르지 않음 | 8192 | 1024 |

- overlap은 크기의 1/8로 고정한다. overlap 비교는 백로그 H3에서 한다
- "자르지 않음"은 KURE-v1 최대 길이 8,192를 청크 크기로 둔 것이다. 8,192 토큰을 넘는 문서(코퍼스 0.45%, `docs/data.md` §8)는 잘라 버리지 않고 같은 규칙으로 나눈다. 뒷부분을 버리면 그 안의 질의응답이 검색되지 않기 때문이다
- 후보 목록은 `configs/config.yaml`의 `chunk_sweep` 절에 둔다

### 임베딩과 저장

- `embedding.normalize: true`로 정규화한 벡터를 저장해 내적이 코사인 유사도가 되게 한다
- 배치는 토큰 수 상한(`embedding.max_batch_tokens`)으로 묶는다. 청크를 길이순으로 정렬한 뒤 `배치 크기 × 배치 안 최대 길이`가 상한을 넘지 않게 자른다. 8,192 토큰 청크를 고정 배치 크기로 묶으면 L4(24GB)에서도 메모리가 부족하다. 상한은 GPU에 맞춰 명령에서 바꾼다
- 장치·정밀도는 `embedding.device`, `embedding.dtype`으로 정한다. 로컬은 `cpu`·`float32`, Colab은 명령에서 `embedding.device=cuda embedding.dtype=float16`으로 바꾼다
- 인덱스 디렉터리는 `paths.index_dir`에 범위를 더한 경로다(`data/index/{임베딩}-{청킹}-{크기}-{overlap}/{범위}/`). 담는 것
  - `chunks.jsonl`: `chunk_id`, `doc_id`, `start`, `end`(원문 문자 offset), `n_tokens`, `text`(청크 원문. Colab에서 코퍼스를 다시 읽지 않고 S6 생성에도 쓴다)
  - `emb/part-NNNNN.npy`: 청크 `index.shard_size`개씩 나눈 임베딩. 이미 있는 조각은 건너뛰어 재개한다
  - `meta.json`: 모델, 청킹 설정, 범위, 청크 수, 차원, 장치·정밀도, 소요 시간
- 디버그용 `index.max_docs`(기본 `null`)를 주면 앞에서부터 그 수만큼만 처리한다. 로컬 사전 확인에 쓴다

### 검색 (dev-small)

- 질의 임베딩은 로컬 CPU `float32`로 한 번 만들어 `data/index/{임베딩}/queries-dev-small.npz`에 두고 후보끼리 다시 쓴다. 질의를 Colab에 올리지 않는다
- dev-small 청크는 최대 1만 개 안팎이라 질의마다 모든 청크와 내적을 계산한다(전수 검색). 청크 순위에서 문서가 처음 나온 순위를 문서 순위로 써 상위 `retriever.top_k`개 문서를 순위 파일로 쓴다. 전수 검색이라 `chunk_pool`(S5)이 결과에 끼어들지 않는다
- 순위 파일은 `data/runs/{인덱스 이름}-dev-small.csv`(`qid`, `rank`, `doc_id`)

### 비교와 결정

`chunk_sweep`이 후보별 순위 파일을 `rag.eval.metrics`로 검증·채점한다.

- 주지표: Recall@5. 보조 지표: Recall@1·5·10, MRR@1·5·10. 지표 목록은 `chunk_sweep` 절에 두고 `configs/eval/`은 바꾸지 않는다
- 표: 후보별 주지표·보조 지표 전부와 청크 수, 문서당 평균 청크 수. 회의구분·`qna_type`별로도 같은 지표를 낸다
- 저장: 표와 후보별 질의 단위 결과(질의마다 각 후보의 정답 순위)를 `data/runs/chunk_sweep.json`에 남긴다. 나중에 한 문서를 여러 크기로 나눠 함께 쓰는 실험(백로그 H9)에서 어느 질의를 어느 크기가 맞히는지 비교하는 자료로 쓴다. dev-small 네 후보 인덱스도 지우지 않는다
- 잡음 범위: Recall@5가 가장 높은 후보를 기준으로 다른 후보와의 차이를 `rag.eval.bootstrap.paired_bootstrap`(회의 단위, `configs/eval/spec_v1.yaml`의 반복·seed·alpha)으로 구한다
- 결정 규칙(점수를 보기 전에 정함): Recall@5 최고 후보를 고른다. 95% 구간이 0을 포함하는 후보가 있으면 그중 청크 수가 가장 적은(크기가 큰) 후보를 고른다. 보조 지표는 판단 근거로 함께 보고하고, 주지표 규칙과 다른 결론을 가리키면 사용자에게 알려 정한다
- 결정은 `configs/chunking/fixed.yaml`에 적고, 전체 지표 비교표·세부 표·근거를 `docs/DECISIONS.md`에 기록한다

dev-small은 방해 문서가 약 1,000개라 전체 코퍼스(38,516)에서 순위가 달라질 수 있다. 이 한계를 DECISIONS에 함께 적고, 전체 규모 확인은 H3에서 한다.

## 실행 순서

1. 로컬: 합성 테스트, `index.max_docs=20`으로 네 후보 인덱스 생성, 끊었다가 다시 실행해 재개 확인, 질의 임베딩, 검색
2. Colab L4(E2 승인 후): dev-small 네 후보 임베딩. 소요 시간과 compute unit을 기록한다
3. 로컬: 내려받은 인덱스로 검색, `chunk_sweep`, 결정 기록
4. Colab L4(E2 승인 후, 2의 처리량으로 예상치 산정): 정한 설정으로 전체 코퍼스 인덱스. 소요 시간과 compute unit을 기록한다

## 명령

```
uv run python -m rag.index index.scope=dev-small|full chunking.chunk_tokens=N chunking.overlap_tokens=M [embedding.device=cuda embedding.dtype=float16] [index.max_docs=K]
uv run python -m rag.search chunking.chunk_tokens=N chunking.overlap_tokens=M
uv run python -m rag.chunk_sweep
```

인자는 Hydra override 형식이다.

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q` | 통과. 합성 입력만 쓴다. 포함: 청크 길이 ≤ `chunk_tokens`, 이웃 청크가 정확히 `overlap_tokens` 겹침, 청크들이 문서 전체를 덮음, offset으로 자른 텍스트가 원문 부분 문자열, 짧은 문서는 청크 하나, 배치의 토큰 수 ≤ 상한, 전수 검색의 문서 중복 제거·순위 |
| 2 | `uv run ruff check .` | 통과 |
| 3 | 로컬 `rag.index index.scope=dev-small index.max_docs=20`(네 후보) | 종료 코드 0. `chunks.jsonl` 행 수 = 임베딩 행 수, 벡터 노름 1, NaN 없음 |
| 4 | 3을 조각 하나만 만든 뒤 끊고 다시 실행 | 이미 있는 조각을 건너뛰고, 처음부터 한 번에 만든 결과와 임베딩이 같음(같은 장치) |
| 5 | Colab에서 만든 dev-small 네 후보 인덱스 | 각 `chunks.jsonl`이 dev-small 1,007문서를 모두 포함하고 행 수 = 임베딩 행 수 |
| 6 | `rag.search` 네 후보 | 순위 파일이 `rag.eval.score --layer dev-small` 검증을 통과(질의 1,039건, 질의당 문서 10개 이상) |
| 7 | 6을 두 번 실행 | 순위 파일 SHA-256 일치 |
| 8 | `rag.chunk_sweep` | 네 후보의 Recall@1·5·10, MRR@1·5·10, 청크 수 표와 회의구분·`qna_type`별 표, 기준 대비 Recall@5 차이·95% 구간 출력. `data/runs/chunk_sweep.json`에 표와 질의 단위 정답 순위 저장 |
| 9 | 전체 코퍼스 인덱스 | `chunks.jsonl`이 38,516문서를 모두 포함하고 행 수 = 임베딩 행 수, NaN 없음 |
| 10 | 문서 기록 | 2·4의 Colab 소요 시간과 compute unit이 이 문서 "실행 기록"에, 비교표와 결정이 DECISIONS에 있음 |

5·9는 Colab에서 내려받은 파일로 확인한다. dev-full 검색·채점은 S5다.

## 실행 기록

| 날짜 | GPU | 범위·후보 | 세션 시간 | 임베딩 시간 | compute unit | 환경 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-01 | L4 | dev-small, 256·512·1024·8192 | 약 6.5분(16:55\~17:01:30, 첫 시도 override 오타 실패 포함) | 74·47·48·55초(모델 로드 포함) | 약 0.09(사용자 추정, 월 첫 사용 기준). 요율 환산 약 0.17 | Colab 기본 Python 3.13, 미리 깔린 패키지에 `PYTHONPATH=src`. 코퍼스는 dev-small 문서만 걸러 업로드 |
| 2026-10-01 | L4 | full, 512/64(청크 118,039) | 약 32분(17:24:55\~17:57:15, 다운로드 357MB 3분 포함) | 1,253초(VM 안 nohup, 끊김 없음) | 0.73(사용자 확인). 요율 환산은 약 0.83 | 1차와 같은 방식. torch 2.11.0+cu128, transformers 5.16.1, sentence-transformers 5.7.0. 코퍼스는 gzip(73MB)으로 업로드 |

요율은 웹 화면의 활성 세션 표시(L4 1.54 CU/시간, 2026-10-01)로 환산했다.

## 수정 허용 파일

- `src/rag/chunking.py`, `src/rag/index.py`, `src/rag/search.py`, `src/rag/chunk_sweep.py`, `tests/test_chunking.py`, `tests/test_index.py`, `tests/test_search.py`
- `configs/config.yaml`(`paths`의 `index_dir`·`query_emb`·`runs_dir`, `embedding`·`index`·`chunk_sweep` 절), `configs/chunking/fixed.yaml`(결정 값)
- `docs/DECISIONS.md`(비교표·결정), `CLAUDE.md` "명령" 절, `docs/PLAN.md` S4 체크와 백로그 H9(다중 크기 청킹)·H10(생성 컨텍스트 단위) 추가, 이 문서

## 범위 밖

- dev-full 검색과 `chunk_pool`(S5), ANN 인덱스(FAISS 등)
- overlap 비교, 문장 경계 청킹(H3, H4), 다중 크기 청킹(H9)
- 생성 프롬프트에 넣을 청크 길이(S6에서 다룬다)
- `configs/eval/`, `src/rag/eval/` 수정
