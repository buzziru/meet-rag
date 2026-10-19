# S13 검색 단계 종료 test 1회 실행

검색 단계를 마치며 `test` 분할로 한 번 채점한다(SPEC 평가 층, D-34). 이 조각은 그 1회 실행에 필요한 코드와 절차를 만든다. 실행은 사용자 지시를 받아 한 번만 하고, 이 조각의 구현·검증 단계에서는 `test` 질의를 읽거나 보내지 않는다.

## 지금 막혀 있는 곳

- `rag.search`는 평가 층을 `index.scope`에서 고른다(`dev-small`, `full` → `dev-full`). `test` 층을 고를 방법이 없다
- 질의 임베딩 캐시는 `paths.query_emb`(`queries-${index.scope}.npz`)라, `test`를 `full`로 돌리면 dev-full 캐시와 같은 경로가 된다. 캐시는 qid 목록이 다르면 다시 임베딩해 덮어쓴다(`query_embeddings`)
- 재정렬 후보 쌍·점수 경로(`${search.queries}-${index.scope}-…`)도 같은 이유로 dev-full 파일과 겹친다
- `colab_job.py upload`는 dev가 아닌 qid가 있으면 업로드를 막는다. 리랭커 채점은 GPU가 필요하다(결정 사항 2)
- `rag.eval.compare`는 dev-full 고정이다(보호 경로라 고치지 않는다). 채점은 `rag.eval.score --layer test --allow-test`가 이미 지원한다

## 만드는 것

- `search.queries=test`: summary_q의 `test` 분할 질의. `index.scope=full`에서만 쓰고, `search.allow_test=true`가 없으면 멈춘다. 질의 목록은 `load_gold(cfg, "test", allow_test=True)`에서 온다. 순위 파일·재정렬 쌍·점수·조건 경로가 `${search.queries}`로 갈라져 dev 파일과 겹치지 않는다
- 질의 임베딩 캐시: `search.queries=test`는 `paths.query_emb_test`(`data/index/${embedding.slug}/queries-test.npz`)를 쓴다. 로컬 CPU로 임베딩한다(snowflake-ko 질의당 약 0.3초, EXP-017 31_02. 3,000여 건에 약 15분, KURE-v1도 비슷하다고 본다(추정))
- 테스트(합성 입력): `allow_test` 없이 멈추는지, test 경로가 dev-full 경로와 다른지, 기본값(`summary_q`)의 순위 파일이 바뀌지 않는지
- 결과 노트북(실행 뒤): 설정별 test 지표, 회의 단위 paired bootstrap(평가 모듈 함수를 불러 씀, `rag.eval.compare`와 같은 10,000회·seed), dev 누적 이득의 test 유지 정도(D-35). 질의 원문은 출력하지 않는다

## 결과 불변 (구현 뒤 확인)

| 설정 | 층 | 기대 |
| --- | --- | --- |
| `+exp=exp017 index.scope=full` | dev-full | 순위 파일 SHA-256 `c6842e8f…` 그대로 |
| `+exp=exp014 index.scope=full` | dev-full | `084bc83e…` 그대로 |
| `+exp=exp017 index.scope=full search.queries=multidoc` | multi-doc | `67e63e80…` 그대로 |

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .` 통과
- 위 결과 불변 표의 해시가 같다
- `search.queries=test`를 `search.allow_test` 없이 주면 질의 파일을 읽기 전에 멈춘다
- 이 조각의 검증은 `test` 질의를 읽지 않는다(합성 입력과 dev만 쓴다)

## 1회 실행 절차 (사용자 지시 뒤)

1. 설정마다 로컬에서 test 순위(리랭커 없는 설정) 또는 후보 쌍(EXP-017)을 만든다. 질의 임베딩은 로컬 CPU
2. EXP-017 후보 쌍을 GPU로 채점한다(결정 사항 2의 방식)
3. `rag.search +exp=exp017 index.scope=full search.queries=test search.allow_test=true`로 순위를 만든다
4. `rag.eval.score --run <순위> --layer test --allow-test`로 채점하고, 결과 노트북을 쓴다
5. 순위 파일·질의 임베딩·후보 쌍의 SHA-256과 실행 커밋을 기록한다. 같은 설정으로 다시 돌리지 않는다
6. DECISIONS에 test 결과와 검색 단계 종료를 적고, PLAN·STATUS를 갱신한다

## 결정 사항 (구현 전에 사용자가 정한다)

1. test로 채점할 설정
   - (a) 세 개: S5 베이스라인(KURE-v1 dense), EXP-014(리랭커 없는 구성, 배포 대체 구성 D-36), EXP-017(기준). D-35가 요구하는 "dev 누적 이득의 test 유지"를 베이스라인 대비로 보고, 리랭커 몫을 EXP-014 대비로 본다. 초안은 (a)다
   - (b) EXP-017 하나. 유지 정도는 dev 점수와만 비교한다
2. EXP-017 test 후보 쌍(3,000여 질의 × 20쌍)의 GPU 채점 위치. D-31은 test 1회의 처리 위치를 그 실행 때 사용자 지시에 맡긴다
   - (a) Colab T4 1회: `colab_job.py upload`에 test 1회용 허용 옵션을 더한다(하네스 변경이라 F 흐름과 ADR). 채점은 EXP-017 실측으로 약 15분, 세션 30\~40분, 약 0.5\~0.7 CU(요율 환산)다
   - (b) 로컬 CPU: 외부 전송이 없다. EXP-005의 CPU 2스레드 질의당 37.1초를 쓰면 약 31시간이다. 로컬 4스레드면 줄겠지만 재지 않았다
3. 결과 기록 위치: 이 지시서 실행 기록 절과 DECISIONS(D 번호 하나). 별도 EXP 문서는 만들지 않는다. 초안은 이 방식이다

## 수정 허용 파일

- `src/rag/search.py`, `configs/config.yaml`(`search`, `paths`), `tests/test_search.py`
- 결정 사항 2가 (a)면 `.claude/skills/meet-rag/scripts/colab_job.py`와 그 테스트, ADR(F 흐름으로 따로 커밋)
- 실행 뒤: 결과 노트북, `docs/DECISIONS.md`, `docs/PLAN.md`, `docs/STATUS.md`, 이 문서

## 범위 밖

- `src/rag/eval/`, `configs/eval/`, `data/splits/`(보호 경로)
- multi-doc의 test 세트(SPEC상 없음)
- 생성 단계
