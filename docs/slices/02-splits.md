# S2 평가 분할

S1 산출물에서 SPEC "분할"·"평가 층" 절의 분할 파일 두 개를 만든다. 완료 후 `data/splits/`는 수정 금지 대상이다.

## 만드는 것

- `data/splits/queries.csv`: `qid`, `conference_number`, `split`(`dev`/`test`). 분할에 들지 않은 질의는 넣지 않는다
- `data/splits/dev_small_docs.txt`: dev-small 문서 `doc_id`, 한 줄에 하나, 오름차순

## 규칙

입력은 `paths.queries`(`qid`, `doc_id`, `qna_type`)와 `paths.corpus`(`doc_id`, `conference_number`, `meeting_name`)다. 질의 텍스트는 읽지 않는다.

### dev·test 배정

SPEC 문장 "seed로 회의를 섞은 뒤, 회의구분 비율을 유지하면서 회의를 차례로 배정한다"를 다음 절차로 구체화한다.

1. 회의 목록을 `conference_number` 오름차순으로 정렬하고 `random.Random(seed).shuffle`로 섞는다
2. 섞인 순서를 유지한 채 회의구분별 대기열로 나눈다
3. 목표 비율 `p_k`는 전체 질의에서 회의구분 `k`가 차지하는 비율이다
4. 현재 분할에 배정된 질의 수를 `c_k`라 할 때, 대기열이 남은 회의구분 중 `c_k / p_k`가 가장 작은 `k`를 고른다(같으면 회의구분 이름 오름차순). 그 대기열의 맨 앞 회의를 배정한다
5. 분할의 질의 수가 최소 질의 수 이상이 되면 멈춘다. dev를 먼저 채우고, 남은 대기열에서 이어서 test를 채운다. 남은 회의는 쓰지 않는다

`c_k / p_k`는 회의구분 `k`가 목표 대비 얼마나 채워졌는지를 뜻하므로, 가장 덜 채워진 회의구분부터 회의를 가져가 비율을 유지한다. 비율은 회의 수가 아니라 질의 수 기준이다(평가 지표가 질의 평균이므로).

### dev-small 문서

dev 회의를 `conference_number` 오름차순 정렬 후 `random.Random(seed).shuffle`로 섞고, 앞에서부터 회의 단위로 그 회의의 문서를 모두 넣는다. 문서 수가 최소 문서 수 이상이 되면 멈춘다.

### 파라미터

`seed`는 `configs/config.yaml`의 `seed`(20260929)를 쓰고, 나머지 값은 같은 파일의 `splits` 절에 둔다: `dev_min_queries: 3000`, `test_min_queries: 3000`, `dev_small_min_docs: 1000`.

### 기록

실행하면 분할별 질의 수·회의 수, 회의구분·`qna_type` 분포를 전체 분포와 나란히 출력한다. test는 건수 분포만 출력하고 질의 텍스트나 점수에는 손대지 않는다. 두 파일의 SHA-256과 분포 표를 `docs/DECISIONS.md`에 적는다.

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run python -m rag.splits` | 종료 코드 0, 두 파일 생성, 분포 출력 |
| 2 | `queries.csv`에서 회의 하나가 두 분할에 걸치는지 | 0건 |
| 3 | 분할별 질의 수 | dev ≥ 3,000, test ≥ 3,000. 각각 마지막 회의를 빼면 3,000 미만 |
| 4 | `dev_small_docs.txt`의 문서 | 모두 dev 회의 문서. 수 ≥ 1,000이고 마지막 회의를 빼면 1,000 미만. 포함된 회의의 문서는 전부 들어 있다 |
| 5 | `queries.csv`의 `qid`가 모두 `paths.queries`에 있고 중복이 없는지 | 예 |
| 6 | 1을 두 번 실행해 두 파일 SHA-256 비교 | 일치 |
| 7 | `uv run pytest -q` | 통과. 테스트는 합성 입력만 쓰고 `data/`를 읽지 않는다 |
| 8 | `uv run ruff check .` | 통과 |

## 수정 허용 파일

- `src/rag/splits.py`, `tests/test_splits.py`
- `configs/config.yaml`(`splits` 절 추가)
- `docs/DECISIONS.md`(분할 파일 SHA-256, 분포)
- `CLAUDE.md` "명령" 절(분할 명령 한 줄 추가), `docs/PLAN.md` S2 체크, 이 문서

## 범위 밖

- 질의 필터(G1)
- 평가 모듈(S3), dev-small 검색 실행
- 보호 경로 훅 설정(STATUS "사용자 확인 필요"의 결정 사항)
