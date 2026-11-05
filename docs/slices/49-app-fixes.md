# S49 앱 점검 수정

전체 파이프라인 점검(기준 커밋 de0db7a)이 앱 쪽 4건을 넘겼다(사용자 결정 2026-11-05, S41 앞). S40이 같은 파일을 고치기 전에 고쳐, 검색 경로의 판단이 멀티턴과 섞이지 않게 한다(S40 결정 사항 4).

## 만드는 것

- **R1-1 BM25 0점 문서**: `rank_docs`가 점수와 무관하게 `fusion.depth`개 문서를 채워, 맞는 토큰이 없는 자유 질의(`안녕`)에서 0점 문서가 RRF 점수를 받는다(`src/rag/retrieve.py:45-62`, `:452-453`). BM25 목록을 점수가 0보다 큰 문서로 자른다. 목록이 비면 `minmax`가 멈추므로 EXP-015 경로(`_convex`)도 막는다
- **R3-2 추적 전송 대기**: `chat_events`의 `get_cached_client().flush()`가 처리 칸을 쥔 채 시간 제한 없이 기다릴 수 있다(`src/rag/app.py:106`). 실제로 막힌 사례는 확인되지 않았다. 지운다. Space는 프로세스가 계속 살아 있어 백그라운드 전송이 보낸다
- **R3-9 질문 길이 상한**: 긴 글을 붙여 넣으면 처리 칸에서 Kiwi·재정렬이 돌고 긴 프롬프트가 유료 생성으로 간다. `app.max_query_chars`를 두고, 넘으면 검색과 생성을 부르지 않고 안내 문구를 답으로 보낸다. 페이지 입력칸에도 같은 길이를 건다
- **R3-12 Space 코드와 `main` 대조**: Space의 `git_commit`은 Hub 저장소 커밋이라 GitHub `main`과 대조할 수 없다(`docs/slices/38-hf-space.md:76`). 올릴 때 GitHub 커밋을 파일 `COMMIT`에 넣고, 이 파일이 있으면 그 값을 추적 메타데이터의 `git_commit`으로 쓴다. 올리는 절차를 `CLAUDE.md` Space 배포 줄에 적는다

## 결정 사항

1. **R1-1의 멈춤 조건(사용자 결정 2026-11-05)**: 고친 코드로 dev-full과 multi-doc 순위를 다시 만들어 기준 순위 파일과 바이트 단위로 대조한다. 같으면 재정렬 점수와 gen-full을 다시 돌리지 않는다. 다르면 기준 변경 결정 대상이라 멈추고 사용자에게 묻는다. `rag.search`의 `write_guarded`가 내용이 다르면 덮어쓰지 않고 멈추므로 기존 파일은 바뀌지 않는다. 평가 질의는 EXP-001에서 맞는 토큰이 없는 경우가 0건이었다(KURE 512 기준, 최소 897개)
2. **길이 상한 값(메인 판단)**: 1,000자. 평가 질의 최대 약 260자(`configs/config.yaml:160`)의 약 4배로, 실제 질문을 막지 않는다. 입력→동작: 1,001자를 API로 보내면 호출 없이 안내 문구가 오고, 페이지에서는 1,000자까지만 입력된다
3. **test 분할**: 순위 대조는 dev와 multi-doc만 한다. test 질의를 읽지 않는다
4. **외부 호출과 재시작(승인 필요)**: OpenRouter 0번. Space 재시작 1번이고, 그동안 페이지는 연결 대기에 머문다. 정상 질문 경로의 첫 호출 확인은 S40의 승인된 질의가 겸한다
5. **R3-2의 대가**: Space가 답변 직후 재시작하면 그 질의의 추적이 빠질 수 있다. 추적은 판정에 쓰지 않아 받아들인다

## 사용자 작업

| 일 | 때 | 횟수 |
| --- | --- | --- |
| 이 지시서 확인과 재시작 승인 | 구현 전 | 1번 |
| 순위가 달라지면 기준 변경 결정 | 대조 뒤, 달라질 때만 | 0\~1번 |
| PR 리뷰 | 병합 전 | 1번 |
| 화면 확인, 토큰 입력 | 없음 | 0번 |

## 노트북과 결정의 순서

순위가 같으면 데이터를 보고 정할 결정이 없어 노트북을 쓰지 않는다. 다르면 멈추고, 어떤 질의가 왜 달라졌는지 노트북을 먼저 쓴 뒤 묻는다.

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과. 맞는 토큰이 없는 질의의 BM25 목록이 비고 RRF·`_convex`가 멈추지 않는 시험, 상한을 넘으면 검색과 생성을 부르지 않는 시험, `COMMIT`을 읽는 시험이 있다 |
| 2 | `uv run python -m rag.search +exp=exp017 index.scope=full`, `… search.queries=multidoc` | 기준 순위 파일과 같다는 출력. 다르면 멈추고 묻는다. 실행 시간을 적는다 |
| 3 | 기준 설정의 재정렬·생성 경로 대조 | 순위가 같으므로 `configs/exp/current.yaml`과 기준 기록을 바꾸지 않는다 |
| 4 | Space 반영 뒤 `/config`와 `years`(값 확인, 질의 없음), 비공개 확인 | 연결되고 API가 그대로다. `COMMIT`이 올린 커밋과 같다 |
| 5 | Space에 1,001자 보내기(값 확인) | 안내 문구가 오고, 로그에 재정렬·생성 호출이 없다. 질의 원문이 로그에 없다 |
| 6 | production 페이지(Aside, 질의 없음) | 연결과 문서 열람이 된다. 콘솔 오류 없음 |

## 수정 허용 파일

`src/CLAUDE.md`, `src/rag/retrieve.py`, `src/rag/bm25.py`, `src/rag/app.py`, `src/rag/index.py`, `configs/config.yaml`(`app` 절), `deploy/web/app.js`, `deploy/web/index.html`, `deploy/space/`, `tests/`의 해당 시험, `CLAUDE.md`(Space 배포 줄), 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/slices/38-hf-space.md`(`이후 변경` 표시)

## 범위 밖

- 멀티턴과 `history` 상한(S40)
- 점검의 낮음 항목 R3-3\~R3-7(고치지 않기로 함, S41 점검에서 나타나면 처리)
- 첫 토큰 3초 재측정(S41에서 1회)

## 결과 (2026-11-05)

커밋: 구현 f6699d4. Space 코드 커밋은 Hub의 457de1c(비공개, `COMMIT`은 f6699d4)

| # | 결과 |
| --- | --- |
| 1 | `uv run pytest -q` 557개 통과, `uv run ruff check .` 통과. 시험을 고친 2건은 0점 문서를 기대하던 합성 시험이다(`test_retriever_hybrid_fuses_dense_and_bm25`, `test_retriever_adds_rewrite_lists_after_original`) |
| 2 | dev-full 3,016질의 "같은 내용, 그대로 둠"(1분 53초), multi-doc 600질의 같음(46초). 해시 전후 동일(dev-full c6842e8f…, multi-doc 67e63e80…). 순위 파일은 상위 10개뿐이라 재정렬 후보 20개는 `search.mode=rerank-pairs`로 따로 대조했다. dev-full 60,320쌍(2분), multi-doc 12,000쌍(1분 8초) 모두 "같은 내용, 그대로 둠" |
| 3 | 순위가 같아 재정렬 점수, gen-full, `configs/exp/current.yaml`을 건드리지 않았다. 사용자 결정 없음 |
| 4 | 올리기 전과 후 비공개, 구성 요소 `api`뿐, API 6개, `years` 28개, `COMMIT` f6699d4 |
| 5 | 1,001자 호출: 안내 문구만 오고 근거 0개. 로그에 재정렬·생성 줄 없음, 질의 원문 없음 |
| 6 | production(Aside, 질의 없음): 연결, 문서 열람, 콘솔 오류 없음 |

OpenRouter 0번. Space 재시작 1번.

### 지시서와 다르게 하거나 더한 것

- `_convex`의 빈 목록을 막는 대신, 점수 결합(EXP-015 경로)은 지금처럼 자르지 않은 목록을 넘긴다. 자르면 BM25가 맞은 문서가 하나일 때 `minmax`가 0을 줘 그 경로의 순서가 바뀐다. 입력→동작: 맞는 토큰이 없어도 그 경로는 멈추지 않고 dense 순서가 된다
- 재작성 목록 `bm25_rw`(EXP-013 경로)도 같은 함수로 자른다. 기준 설정이 쓰지 않는 경로이고, 지난 실험은 그 커밋의 코드로 재현한다(`src/CLAUDE.md`)
- `src/CLAUDE.md`의 LLM 호출 끝 `flush` 규칙에 Space 앱 채팅 경로의 예외를 적었다. 끝나는 스크립트와 달리 Space는 계속 살아 있어 백그라운드 전송이 보낸다. 수정 허용 파일에 더했다
- 시험은 합성 인덱스의 RRF·점수 결합과 빈 목록, 상한, `COMMIT`을 본다.

### 관찰

- 정상 질문 경로의 Space 호출은 이 조각에서 보내지 않았다. S40의 승인된 질의가 겸한다. 추적 전송도 그때 LangSmith에서 본다
- 평가 질의에서 순위가 같으므로 R1-1의 효과는 맞는 토큰이 없는 자유 질의에서만 난다. 실제 인덱스에서 그런 질의의 근거가 어떻게 바뀌는지는 재지 않았다
- `COMMIT`이 있으면 git보다 먼저 읽고 `git_dirty`는 거짓으로 둔다. Space에도 git 값이 있어 git을 먼저 읽으면 Hub 커밋이 남는다. 로컬에 이 파일을 두면 생성·judge 기록의 커밋이 조용히 틀리므로 올릴 폴더에만 만든다(`.gitignore`에 넣지 않아 생기면 `git status`에 보인다)
- 상한 값 1,000이 `app.max_query_chars`, `query_too_long` 문구, 페이지 `maxlength` 세 곳에 있다. 페이지는 config를 받는 경로가 없어 값을 맞추는 시험 없이 둔다
