# S11 질의 조건 추출기

H14(D-19)가 질의에서 회의를 지목하는 조건을 뽑아 문서 메타데이터와 대조할 수 있도록, 질의 텍스트에서 조건을 뽑는 규칙·사전 추출기를 만든다. 검색에는 아직 넣지 않고, 추출이 얼마나 맞는지만 잰다(검색 점수는 보지 않는다).

## 만드는 것

- `src/rag/conditions.py`: 질의 텍스트 하나에서 조건을 뽑는 `extract`와, 질의 세트 전체의 조건을 파일로 쓰는 명령 `uv run python -m rag.conditions [search.queries=summary_q|multidoc]`
- `configs/config.yaml`: 출력 경로 `paths.conditions`(`data/conditions/{세트}.jsonl`), 이름 경계 규칙에 쓰는 값(`conditions.*`)
- `notebooks/13_01_조건추출.ipynb`: 추출 정확도와 오추출 유형. 규칙을 고칠지 정하는 근거다

## 규칙

### 입력

- 질의 텍스트(`query`)와 값 사전(`paths.meta_dict`, S10)만 쓴다. 질의 파일의 다른 필드, 정답 문서, `qid`에서 얻는 회의 번호는 쓰지 않는다(protocol-guard P9)
- 질의 세트는 `search.queries`와 같다. `summary_q`는 dev 분할 질의만 읽고(`paths.queries_dev`), `multidoc`은 G3 동결 세트(`paths.multidoc_frozen`)의 `query`만 읽는다. test 질의는 읽지 않는다

### 조건 필드

출력 값은 코퍼스 필드와 같은 형식으로 맞춰, H14가 문서 값과 그대로 비교할 수 있게 한다.

| 조건 | 방법 | 대조할 문서 필드 |
| --- | --- | --- |
| `date` | 정규식: `YYYY년 M월 D일`, `YYYY년 M월`, `YYYY년`(공백 유무 허용). 연·월·일 중 있는 것만 담는다. `YYYY년도`(회계연도)는 뽑지 않는다(D-21) | `date`(`1996년7월20일(토)`를 파싱) |
| `generation_number` | 정규식: `제NN대 국회`, `NN대 국회` | `generation_number` |
| `meeting_number` | 정규식: 세 자리 `제NNN회`(회기, 코퍼스 180\~402. D-21) | `meeting_number` |
| `session_number` | 정규식: `제N차` | `session_number` |
| `committee_name` | 사전 값의 부분 문자열 일치. 긴 값부터 맞추고 겹친 짧은 값은 버린다. 약칭은 값에서 `원회`를 뺀 형태(`국방위원회` → `국방위`)를 함께 맞춘다 | `committee_name` |
| `meeting_name` | 사전 값 5종의 부분 문자열 일치, 긴 값 우선(`예산결산특별위원회` 안의 `특별위원회`는 버린다) | `meeting_name` |
| `names` | 사전 이름의 부분 문자열 일치에 경계 규칙을 둔다. 앞은 질의 시작이나 한글 밖 문자, 뒤는 질의 끝, 한글 밖 문자, 직함(`ingest.name_titles`), 조사(`conditions.name_suffixes`) 중 하나일 때만 인정한다. 사전 값 중 한글 밖 문자가 있거나 직함으로 끝나거나 `conditions.name_exclude`에 있는 값은 이름으로 쓰지 않는다(D-21) | `questioners`·`answerers`의 `name` |

- 안건·법안(`agenda`, QA의 `law`)과 직위만으로 된 조건(`장관이 답변한`)은 뽑지 않는다. 안건은 H14에서 항목 단위 색인으로 다룬다(D-19)
- 출력은 질의마다 `{qid, conditions: {필드: [값...]}}` 한 줄이다. 뽑힌 것이 없는 필드는 넣지 않는다

### 정확도 측정

추출기에는 정답을 넣지 않는다. 측정할 때만 정답 문서 메타데이터를 기대값으로 쓴다.

- multi-doc(G3 600건): 유형(`conf`·`law`·`questioner`)×조건 필드마다 다음을 낸다
  - 발화율: 그 필드가 하나 이상 뽑힌 질의 비율
  - 정밀도: 뽑힌 값 중 정답 문서 중 하나 이상의 메타데이터와 맞는 값의 비율
  - 적중률: 정답 문서 메타데이터와 맞는 값이 하나 이상 뽑힌 질의 비율
- single-doc(dev summary_q): 같은 세 값을 낸다. single-doc 질의는 본문에서 만들어져 조건이 드물 것으로 본다(PR #49 사용자 코멘트). 조건이 뽑히면 H14의 약한 필터가 정답과 다른 회의 문서를 올릴 수 있어 정밀도를 함께 본다
- "맞는다"의 기준: `date`는 뽑힌 연·월·일이 문서 날짜와 모두 같음, 문자열 필드는 정확히 같음

### 규칙을 G3로 다듬을 수 있는가 (사용자 결정: 권고안, 2026-10-12)

G3는 EXP-003(H14)의 multi-doc 판정 세트다. G3 질의를 보고 추출 규칙을 고치면 추출 정확도와 H14의 multi-doc 점수가 실제보다 좋게 나온다. G3 밖의 multi-doc 통과 질의는 제외된 `law` 38건뿐이라, 규칙을 다듬을 별도 세트가 없다.

- (권고) 첫 규칙은 위 표처럼 코퍼스 필드 형식과 사전만 보고 정한다. G3 측정은 한 번 하고, 그 뒤 고치는 것은 원래 규칙이 의도와 다르게 동작한 결함(정규식 오류, 경계 규칙 누락 등)만으로 한다. 고칠 때마다 무엇을 고쳤고 G3에서 바뀐 질의 수가 몇인지 DECISIONS에 적는다. EXP-003 문서에는 추출 규칙이 G3 오류를 본 뒤 고쳐졌다는 단서를 적는다
- G3 오류를 보고 규칙을 자유롭게 고친다. 추출 정확도는 높아지지만 EXP-003의 multi-doc 점수에 그만큼 낙관 편향이 생긴다
- 규칙을 고치지 않는다. 첫 측정 결과를 그대로 H14에 쓴다

### 노트북과 결정 순서

1. 추출기와 명령을 만들고 두 세트의 조건 파일을 쓴다
2. `notebooks/13_01_조건추출.ipynb`를 쓴다. 질의 원문은 오추출 유형마다 몇 건만 보이고, 대량으로 출력하지 않는다(D-10)
   - 위 정확도 표(유형×필드)
   - 정밀도를 깎은 오추출 유형별 건수(이름 경계, 위원회 약칭, 날짜 형식 등)
   - 적중하지 못한 질의 중 조건 표현이 있는데 놓친 경우의 유형(표본 확인)
3. 노트북을 사용자에게 보이고, 고칠 결함이 있으면 고친 뒤 다시 측정한다. 결정은 DECISIONS에 기록한다

## 완료 기준

1. `uv run python -m rag.conditions search.queries=multidoc`가 600줄, `search.queries=summary_q`가 dev 질의 수만큼 줄을 쓴다
2. 같은 명령을 두 번 실행한 출력 SHA-256이 같다
3. 추출 코드가 질의 텍스트와 값 사전 밖의 값을 읽지 않는다(`query` 밖 필드, `gold_doc_ids`, `qid` 파싱이 없다)
4. 조건 필드마다 단위 테스트를 둔다. 테스트 질의는 G3·평가 질의가 아니라 직접 쓴 문장이다. 경계 규칙(이름 앞뒤, 약칭, 긴 값 우선)의 통과·거부 사례를 포함한다
5. `uv run pytest -q`, `uv run ruff check .` 통과

## 수정 허용 파일

- `src/rag/conditions.py`(새 파일), `tests/test_conditions.py`
- `configs/config.yaml`의 `paths.conditions`, `conditions.*` 추가(기존 값은 바꾸지 않는다)
- `notebooks/13_01_조건추출.ipynb`
- `docs/DECISIONS.md`(규칙 수정 기록), `docs/PLAN.md`(S11 체크), `CLAUDE.md` 명령 한 줄

## 범위 밖

- 조건을 검색 순위에 반영하는 것(결합 방식, 가점 크기), 안건 항목 단위 색인: H14(EXP-003)
- 직위·소속 조건, 법안 이름 조건
- 응답자·직위로 회의를 지목하는 multi-doc 질의 유형 추가: G4
