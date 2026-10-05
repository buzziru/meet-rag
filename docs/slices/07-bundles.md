# S7 multi-doc 묶음 구성

SPEC "보조 관찰: multi-doc 질의" 절의 문서 묶음을 메타데이터로 만든다. S8이 이 묶음으로 질의를 생성하고 검사한다. LLM 호출과 검색기 점수를 쓰지 않는다.

## 용어

- 후보 집합: 같은 메타데이터 키를 공유하는 문서 전체. S8의 완전성 검사가 이 안의 문서를 모두 정답·무관으로 판정하고, S9의 bootstrap 재표본 단위가 된다
- 시작 묶음: 후보 집합에서 고른 문서 2\~3개. S8 생성 에이전트는 이 문서만 읽고 질의를 쓴다

## 만드는 것

- `data/multidoc/pools.jsonl`: 한 줄에 후보 집합 하나. `pool_id`, `type`, `key`, `order`(유형 안 처리 순서), `doc_ids`(후보 집합 전체, 오름차순), `seed_doc_ids`(시작 묶음)
- 실행하면 유형별 후보 집합 수, 크기 분포, 시작 묶음 크기 분포, 유형 사이 문서 겹침 수를 출력한다

## 입력

- 라벨 zip(`paths.raw_dir`, `rag.ingest.iter_labels`): `conference_number`, `question_number`, `context`(`doc_id` 계산), `law`, `questioner_ID`, `committee_name`만 쓴다. 질의(`summary_q`)·답변·발언 원문은 쓰지 않는다
- `paths.splits`: `test` 회의를 뺀다
- `paths.corpus`: 모든 `doc_id`가 코퍼스에 있는지 확인한다

`law`와 `questioner_ID`는 `data/processed/` 파일에 없어 라벨 zip에서 읽는다(약 10초).

## 유형

제안이다. 노트북을 본 뒤 확정한다("노트북과 결정의 순서").

| 유형 | 키 | 조건 | 사전 측정(`test` 회의 제외) |
| --- | --- | --- | --- |
| `conf` 회의 내 | `conference_number` | 문서 2개 이상 | 2,184개. 크기 중앙값 14, 90% 18, 최대 60 |
| `law` 법안 | `law`(빈 값 제외) | 회의 2개 이상 | 437개. 중앙값 4, 90% 24, 최대 1,679 |
| `questioner` 질의자·위원회 | (`questioner_ID`, `committee_name`) | 회의 2개 이상 | 4,330개. 중앙값 5, 90% 15, 최대 101 |

뺀 키와 이유

- 질의자 단독: 중앙값 15, 90% 95로 범위가 넓어 완전성 검사가 어렵다
- 위원회 단독: 위원회 하나가 수백 개 문서라 같은 이유
- 질의자·법안: 670개, 중앙값 3으로 작지만 대부분 법안 유형의 부분집합이다

`law`는 질의응답쌍 단위 값이라 한 문서에 값이 여럿일 수 있다(7건). 그런 문서는 각 법안 후보 집합에 들어간다.

## 규칙

1. `test` 분할 회의의 문서는 넣지 않는다
2. 후보 집합 크기가 `pool_max_docs`(제안 20)를 넘으면 쓰지 않는다. 완전성 검사가 후보 집합 전체를 읽으므로 입력이 문서 수에 비례한다(문서당 약 1,600토큰으로 추정)
3. 유형마다 후보 집합을 키 오름차순으로 정렬하고 `random.Random(seed)`로 섞은 뒤 앞에서 `n_pools_per_type`(제안 250)개를 고른다. `order`는 섞인 순서다. S8은 앞에서부터 쓴다. 난수 생성기는 하나를 `conf` → `law` → `questioner` 순으로 이어 쓴다
4. 시작 묶음 크기 k는 `seed_sizes`(제안 [2, 3])에서 같은 난수 생성기로 고른다. 후보 집합에서 고를 수 있는 수가 k보다 작으면 그 수로 줄인다
   - `conf`: 문서를 그 문서의 가장 작은 `question_number` 순(발언 순서)으로 정렬하고, 무작위 시작 위치에서 연속 k개를 고른다. 인접 구간이 같은 안건을 다룰 가능성이 커서다
   - `law`·`questioner`: 회의를 무작위로 k개 고르고 회의마다 문서 하나를 무작위로 고른다. 시작 묶음이 서로 다른 회의에 걸치게 한다
5. 한 문서가 여러 유형의 후보 집합에 들어가는 것은 허용하고 수를 출력한다

### 파라미터

`configs/config.yaml`에 `multidoc` 절(`types`, `pool_max_docs`, `n_pools_per_type`, `seed_sizes`)과 `paths.multidoc_pools`를 둔다. `seed`는 기존 값(20260929)을 쓴다.

## 노트북과 결정의 순서

1. 제안값으로 구현하고 실행한다
2. `notebooks/07_01_묶음구성.ipynb`: 유형별 후보 집합 크기 분포, `pool_max_docs`별 남는 후보 집합 수, 시작 묶음 예시 몇 개(메타데이터와 `context` 앞 200자)
3. 사용자가 노트북을 보고 유형, `pool_max_docs`, `n_pools_per_type`, `seed_sizes`를 정한다
4. 값을 반영해 다시 실행하고 DECISIONS에 값과 `pools.jsonl` SHA-256을 적는다. 그 뒤 PR

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run python -m rag.multidoc.pools` | 종료 코드 0, `pools.jsonl` 생성, 분포 출력 |
| 2 | `pools.jsonl`의 문서 회의를 `queries.csv`와 대조 | `test` 회의 문서 0건 |
| 3 | 모든 `doc_id`가 `paths.corpus`에 있는지 | 예 |
| 4 | 후보 집합 검사 | 크기 2 이상 `pool_max_docs` 이하, `seed_doc_ids` ⊂ `doc_ids`, 시작 묶음 크기가 `seed_sizes` 범위. `law`·`questioner`의 시작 묶음은 서로 다른 회의, `conf`의 시작 묶음은 발언 순서상 연속 |
| 5 | 유형별 후보 집합 수 | min(`n_pools_per_type`, 조건을 만족하는 후보 집합 수) |
| 6 | 1을 두 번 실행해 SHA-256 비교 | 일치 |
| 7 | `pools.jsonl` 필드 | 위 "만드는 것"의 여섯 개뿐. 질의·발언 텍스트 없음 |
| 8 | `uv run pytest -q` | 통과. 합성 입력만 쓰고 `data/`를 읽지 않는다 |
| 9 | `uv run ruff check .` | 통과(노트북 포함) |
| 10 | 노트북 처음부터 실행 | 오류 없음 |
| 11 | 문서 기록 | `CLAUDE.md` "명령"에 묶음 명령, PLAN S7 체크, DECISIONS에 확정값과 SHA-256 |

## 수정 허용 파일

- `src/rag/multidoc/__init__.py`, `src/rag/multidoc/pools.py`, `tests/test_multidoc_pools.py`
- `configs/config.yaml`(`multidoc` 절, `paths.multidoc_pools`)
- `notebooks/07_01_묶음구성.ipynb`
- `docs/DECISIONS.md`, `docs/PLAN.md` S7 체크, `CLAUDE.md` "명령" 절, 이 문서

## 범위 밖

- 질의 생성·검사, 생성 입력 파일 형식(S8)
- 다중 정답 채점(S9)
- `src/rag/eval/`, `configs/eval/`, `data/splits/` 수정
