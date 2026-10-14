# S12 인덱스 경로 규칙과 검색 모듈 공유

검색 설정을 config로만 고르게 하고, 평가(`rag.search`)와 생성(`rag.generate`)이 같은 검색 코드를 쓰게 한다. PR #68 코멘트 2(인덱스 규칙 점검)에서 나온 문제를 고친다. 검색 결과는 바뀌지 않아야 한다.

점검에서 나온 문제는 다음과 같다.

1. 추가 청크 인덱스의 경로를 `paths.index_dir` 템플릿이 아니라 `src/rag/search.py` `dense_chunks`가 같은 규칙으로 다시 조립한다. `extra_chunks`가 `[크기, overlap]`만 받아, 청킹 방식이 다른 인덱스(H4 문장 경계 청킹)는 섞을 수 없다
2. `rag.generate`는 기본 512 인덱스에서 dense 단독으로 검색한다(`src/rag/generate.py` `Pipeline.retrieve`). 채택한 hybrid·조건 목록·최다 일치 필터·법률명 조건(D-17\~D-27)과 256 청크(D-29)가 생성 경로에 없다
3. 순위 파일 이름의 `run_name`을 손으로 정해, 빠뜨리면 다른 설정의 실행이 기존 순위 파일을 덮어쓴다

## 만드는 것

- `src/rag/index.py` `index_path(cfg, chunking)`: 청킹 설정 하나(`name`, `chunk_tokens`, `overlap_tokens`)를 받아 `paths.index_dir` 템플릿을 그 값으로 풀어 경로를 낸다. 인덱스 경로를 만드는 곳은 이 함수 하나다. `rag.index`, `rag.search`, `rag.generate`, `rag.chunk_sweep`이 쓴다
- `retriever.extra_chunks` 형식 변경: `[크기, overlap]` 목록에서 청킹 설정 목록(`{name, chunk_tokens, overlap_tokens}`)으로 바꾼다. `configs/exp/exp011.yaml`을 새 형식으로 고친다(값은 같다)
- `src/rag/retrieve.py` `Retriever`: 인덱스(기본 + 추가 청크), BM25, 조건 색인을 한 번 읽고, 질의 하나의 dense 점수 행·BM25 토큰·조건을 받아 문서 순위를 낸다. `rag.search`의 질의별 처리(dense 문서 순위, 가중 집계, BM25, 조건 목록, RRF, 최다 일치 필터)를 옮긴 것이다. 재정렬 점수 파일과 후보 쌍 내보내기(EXP-005·006)는 평가 전용이라 `rag.search`에 남긴다
- `rag.search`: 질의 배치 내적과 순위 파일 쓰기만 하고, 질의별 순위는 `Retriever`에 맡긴다
- `rag.generate`: `Retriever`로 문서 순위를 내고 상위 `generator.context_docs`개 문서를 근거로 쓴다. 조건은 `rag.conditions`의 추출기로 질의 원문에서 뽑는다(dev 질의와 자유 질의가 같은 경로). 생성 기록에 검색 설정(`retriever` 전체)을 남긴다
- 순위 파일 덮어쓰기 방지: 같은 경로에 내용이 다른 순위 파일이 있으면 멈춘다. 덮어쓰려면 `search.overwrite=true`를 준다. 내용이 같으면 그대로 둔다
- 테스트: `index_path`, `Retriever`(dense 단독과 hybrid의 작은 합성 입력), 덮어쓰기 방지

## 규칙

### 결과 불변

리팩터링이라 순위 파일이 바뀌면 안 된다. 아래 설정으로 리팩터링 전후 순위 파일의 SHA-256을 비교한다. 리팩터링 전 파일은 지금 `data/runs/`에 있는 것이고, 리팩터링 뒤에는 덮어쓰기 방지가 내용 일치를 확인한다.

| 설정 | 층 |
| --- | --- |
| 기본(dense, S5), `+exp=exp001`\~`exp004`, `exp007`\~`exp010`. 재정렬 점수 파일이 필요한 exp005·006은 뺀다 | dev-small |
| `+exp=exp011` | dev-small, dev-full, multi-doc |

kure-v1 설정(exp001\~008)은 KURE 인덱스와 조건 파일이 로컬에 있을 때만 돌린다. 없는 설정은 건너뛰고 기록한다.

### 생성 경로의 근거 청크

문서마다 근거로 넣을 청크를 고르는 규칙은 아래 결정 1을 따른다. 생성 답변은 평가하지 않으므로(SPEC 범위 밖) 결과 불변 대상이 아니다. 확인은 dev 질의 하나로 검색 결과와 근거 목록을 보고, 생성 API 호출은 사용자 승인 뒤 1회만 한다(무료 쿼터).

### 바꾸지 않는 것

- `paths.index_dir` 템플릿 값, 인덱스 디렉터리 이름, 순위 파일 이름 규칙(D-29 기준 순위 파일 경로를 유지한다)
- BM25 인덱스 위치(`{index_dir}/bm25-{name}`). 청크 경계가 임베딩 모델의 토크나이저로 정해지므로 BM25가 그 인덱스 아래에 있는 것은 맞다. 점검 보고 3번(임베딩마다 BM25 중복)은 토크나이저가 같은 모델끼리만 중복이라 이 SLICE에서 다루지 않는다
- `src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`(보호 경로)

## 결정 사항

1. 생성 근거 청크: (b) 문서마다 512·256 전체 청크 중 dense 점수 최고 청크를 넣는다(사용자 결정 2026-10-14). 지금 파이프라인은 청크로 문서를 찾고 찾은 청크를 근거로 넣는다(D-05). 256 청크가 최고점인데 512 청크를 넣으면 근거 길이는 유지되지만 "찾은 청크를 넣는다"는 원리가 바뀐다. 256 청크가 근거가 되면 근거가 짧아질 수 있고, 그 영향은 생성 평가가 생기면 H10에서 본다
2. 덮어쓰기 방지: 넣는다(사용자 결정 2026-10-14). 이번 세션에 dense 단독 실행이 `run_name` 없이 기준 dense 순위 파일을 덮어썼다(내용은 같았다). 리팩터링 결과 불변 확인에도 쓴다

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .` 통과
- "결과 불변" 표의 설정마다 `uv run python -m rag.search <설정> index.scope=<층>`이 덮어쓰기 방지에 걸리지 않고 끝난다(같은 내용이라 통과). 다른 내용이면 실패로 본다
- `uv run python -m rag.index +exp=exp009 chunking.chunk_tokens=256 chunking.overlap_tokens=32 index.scope=dev-small`가 기존 인덱스를 찾아 임베딩을 건너뛴다(경로 함수 확인. 새 임베딩이 생기면 실패)
- `rag.generate +exp=exp011 ask.qid=<dev qid>`의 검색 단계가 같은 qid의 `rag.search +exp=exp011` dev-full 순위 상위 `context_docs`개와 같은 문서를 같은 순서로 낸다(생성 호출 전 단계까지 확인)
- 순위 파일을 다른 내용으로 덮어쓰려 하면 멈추고, `search.overwrite=true`면 쓴다(테스트)

## 수정 허용 파일

- `src/rag/index.py`, `src/rag/search.py`, `src/rag/generate.py`, `src/rag/chunk_sweep.py`, 새 `src/rag/retrieve.py`
- `src/rag/conditions.py`: 추출기 생성(`main` 안의 사전·법률명 준비)을 함수로 떼어 `rag.generate`도 쓰게 한다. 추출 규칙은 바꾸지 않는다
- `configs/config.yaml`(`search.overwrite` 추가), `configs/exp/exp011.yaml`(형식만)
- `tests/`의 해당 테스트
- `docs/slices/12-index-rules.md`, `docs/slices/06-generate.md`(검색 경로 서술), `CLAUDE.md` "명령" 절(호출법이 바뀌면), `docs/PLAN.md`(S12 줄)

## 범위 밖

- 생성 근거 단위 변경(H10), 생성 평가
- 리랭커의 온라인 추론(D-26 운영 보류). `Retriever`는 재정렬을 하지 않는다
- 인덱스 float16 저장, 256 쪽 `chunks.jsonl` 경량화
- H4 문장 경계 청킹(청킹 함수 추가는 EXP-012에서 한다)
