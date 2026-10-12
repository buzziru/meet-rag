# S10 화자 필드와 메타데이터 사전

H14(질의 조건 방식, D-19)가 질의에서 뽑은 조건을 문서와 대조할 수 있도록 두 가지를 만든다. 하나는 문서의 화자 필드이고, 하나는 조건 추출(S11)에 쓸 값 사전이다. 화자 정보는 문서 본문이 아니라 QA 라벨(`questioner_*`, `answerer_*`)에만 있다. 그래서 문서마다 그 문서에서 나온 QA들의 화자를 모아 문서 속성으로 붙인다(D-19, protocol-guard P9).

## 만드는 것

- `src/rag/ingest.py`: 코퍼스 문서에 화자 필드 `questioners`·`answerers`를 더한다. 질의 파일은 바꾸지 않는다
- `src/rag/meta_dict.py`: 코퍼스 파일만 읽어 값 사전을 만드는 명령 `uv run python -m rag.meta_dict`
- `configs/config.yaml`: 사전 경로 `paths.meta_dict`(`data/processed/meta_dict.json`)
- `notebooks/12_01_화자필드.ipynb`: 화자 필드와 사전의 품질 확인. 이름 정규화 규칙을 정하는 근거다

## 규칙

### 화자 필드

- 같은 문서(`doc_id`)에서 나온 QA 레코드 전부에서 모은다. QA가 여럿인 문서는 화자가 여럿이다(`n_qa`)
- `questioners`: `{name, position, affiliation}` 목록. 값은 `questioner_name`·`questioner_position`·`questioner_affiliation`
- `answerers`: 같은 형식. 값은 `answerer_name`·`answerer_position`·`answerer_affiliation`
- 각 값은 `strip()`한다. 공백 한 칸만 든 값이 있다(`docs/data.md` §9). 빈 값은 `""`로 둔다
- 세 값이 모두 같은 항목은 하나만 남긴다. 순서는 `qid` 순으로 처음 나온 순서다. 같은 입력이면 같은 출력이 나와야 한다
- `*_ID`·`*_ISNI`는 넣지 않는다. 응답자 쪽은 98%가 비어 필터 근거로 쓸 수 없다(`docs/data.md` §9)
- 이름 정규화(직함이 이름에 붙은 경우 등)는 노트북 12_01을 본 뒤 정한다. 정하기 전에는 `strip()`만 한다

### 불변 조건

- 기존 필드(`doc_id`, `context`, 회의 메타데이터, `splits`, `n_qa`)는 값과 문서 순서가 그대로다. 인덱스(`chunks.jsonl`)와 BM25 인덱스를 다시 만들지 않고 쓴다
- 질의 파일 `queries_summary_q.jsonl`은 바이트 단위로 같다
- `rag.multidoc.pools`는 원천 라벨을 직접 읽고 코퍼스에서는 `doc_id`만 읽으므로 영향이 없다

### 값 사전

- 입력은 코퍼스 파일 하나다. 평가 질의 파일, 분할 파일, multi-doc 동결 세트를 읽지 않는다(P9)
- 항목: 위원회(`committee_name`), 회의 종류(`meeting_name`), 사람 이름(`questioners`·`answerers`의 `name`), 직위(`position`), 소속(`affiliation`)
- 값마다 그 값을 가진 문서 수를 적는다. 빈 값은 넣지 않는다. 키 순서를 정렬해 같은 입력이면 같은 파일이 나오게 한다

### test 분할 회의 문서를 사전에 넣는가 (사용자 결정)

test 회의 문서의 화자 값도 그 회의 QA 라벨에서 온다. SPEC은 "설정 선택, 필터 규칙, 프롬프트 작성에 test 질의를 쓰지 않는다"고 정한다(`docs/SPEC.md:81`).

- (권고) 코퍼스 전체 문서로 만든다. 사전은 문서 쪽 속성을 모은 것이고 test 질의 텍스트나 정답을 쓰지 않는다. 검색 대상 코퍼스는 test 평가 때도 38,516건 전체이고, 위원회·회의명 같은 회의 메타데이터는 이미 모든 문서에서 쓰고 있다(EXP-002). test 문서만 빼면 test 회의 화자는 사전에 없어 조건이 뽑히지 않으므로, test 점수가 dev와 다른 조건에서 나온다
- test 회의 문서를 뺀다. SPEC 문구를 넓게 읽어 test QA 라벨에서 온 값을 쓰지 않는 쪽이다. 위의 dev와 test 사이 조건 차이가 생긴다

어느 쪽이든 문서의 화자 필드 자체는 모든 문서에 둔다.

### 노트북과 결정 순서

1. 적재와 사전을 만든 뒤 `notebooks/12_01_화자필드.ipynb`를 쓴다. 질의 원문은 출력하지 않는다
   - 필드별 빈 값 비율, 문서당 질의자·응답자 수 분포
   - 이름 값의 형식: 길이 분포, 한글 밖 문자, 직함·괄호가 이름에 붙은 경우의 수와 예시 몇 개
   - 같은 이름이 여러 직위·소속으로 나오는 경우(동명이인 또는 직위 변경)의 수
   - 사전 크기: 항목별 값 수
2. 노트북을 사용자에게 보이고 이름 정규화를 할지, 한다면 규칙을 정한다
3. 정한 규칙을 반영해 다시 만들고 DECISIONS에 기록한다

## 완료 기준

1. `uv run python -m rag.ingest` 결과 코퍼스 38,516건, 질의 39,633건
2. 질의 파일 SHA-256이 이번 변경 전과 같다
3. 코퍼스에서 `questioners`·`answerers`를 뺀 나머지가 변경 전 파일과 같다(문서 순서 포함)
4. 모든 문서에 두 필드가 있고, 항목 수 합이 1 이상이다
5. `uv run python -m rag.meta_dict`를 두 번 실행한 결과 SHA-256이 같다. 사전 코드가 코퍼스 밖 파일을 열지 않는다
6. `uv run python -m rag.search +exp=exp001 index.scope=dev-small`의 순위 파일 SHA-256이 변경 전과 같다(인덱스 재사용 확인)
7. `uv run pytest -q`, `uv run ruff check .` 통과. 화자 모으기(중복 제거, 순서, strip)와 사전 값 세기 단위 테스트를 둔다

## 수정 허용 파일

- `src/rag/ingest.py`, `src/rag/meta_dict.py`(새 파일)
- `tests/test_ingest.py`, `tests/test_meta_dict.py`
- `configs/config.yaml`의 `paths.meta_dict` 추가(기존 값은 바꾸지 않는다)
- `notebooks/12_01_화자필드.ipynb`
- `docs/data.md`(코퍼스 형식 절), `docs/DECISIONS.md`(정규화 규칙·test 포함 결정), `docs/PLAN.md`(S10 체크), `CLAUDE.md` 명령 한 줄

## 범위 밖

- 질의에서 조건을 뽑는 코드와 추출 정확도: S11
- 조건 대조를 검색에 반영하는 것, 안건 항목 단위 색인: H14(EXP-003)
- 응답자·직위로 회의를 지목하는 multi-doc 질의 유형 추가: G4
- 화자 필드를 원문 발언(`context`)에서 다시 뽑아 라벨에 없는 발언자까지 채우는 것. 지금 필드는 라벨링된 QA의 화자만 담는다(D-19 한계)
