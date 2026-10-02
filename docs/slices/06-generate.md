# S6 생성

질의 하나를 받아 전체 인덱스에서 검색하고, 상위 문서의 근거 청크를 넣은 프롬프트로 Gemma 4 31B(Google AI Studio OpenAI 호환 엔드포인트, D-01)를 호출해 답변과 근거 URL(`original`)을 낸다. 이 조각으로 naive RAG 파이프라인(청킹 → 검색 → 생성)이 끝난다.

답변 평가 기준은 아직 정하지 않았다(SPEC 범위 밖, 검색 단계 이후 개정). 나중에 답변이 근거에 기반했는지 평가할 수 있게 호출마다 질의·근거·답변을 한 기록으로 남긴다. 이 조각에서는 직접 쓴 질의로 동작만 확인하고 정량 평가는 하지 않는다.

## 만드는 것

- `src/rag/generate.py`: 질의 → 질의 임베딩(로컬 CPU) → 전수 검색 → 근거 구성 → 프롬프트 → 생성 호출 → 답변·근거 출력과 기록 저장
- `configs/generator/gemma.yaml`: 모델 ID, 넣을 문서 수, 출력 길이, 프롬프트
- `notebooks/06_01_생성확인.ipynb`: 저장된 기록을 불러와 질의별 근거와 답변을 보여 준다. 노트북에서 API를 호출하지 않는다

## 규칙

### 검색과 근거

- 검색은 S5와 같다(`rag.search.rank_with_pool`, 512/64 전체 인덱스). 질의 하나라 질의 임베딩은 로컬 CPU에서 하고 캐시하지 않는다
- 근거는 상위 `generator.context_docs`(5)개 문서마다 점수가 가장 높은 청크 하나다(D-05). 5는 주지표 Recall@5에 맞춘 값이고 데이터를 보고 정한 값이 아니다
- 근거마다 번호 `[1]`\~`[5]`, 회의 정보(`date`, `committee_name`, `meeting_number`·`session_number`), 청크 원문을 프롬프트에 넣는다. `original` URL은 프롬프트에 넣지 않고 출력의 근거 목록에만 붙인다(토큰 절약, 모델이 URL을 지어내지 않게)

### 프롬프트와 호출

- 시스템 지시: 근거 안의 내용으로만 한국어로 답하고, 문장마다 근거 번호를 `[n]`으로 붙이며, 근거로 답할 수 없으면 그렇다고 말한다. 문구는 config에 두고 `generator.prompt_version`(v1)으로 구분한다
- 호출은 `openai` SDK로 `generator.base_url`에 보낸다. 키는 `.env`의 `GOOGLE_API_KEY`(`generator.api_key_env`). `temperature` 0, 출력 상한 `generator.max_tokens`
- 모델 ID(`generator.model`, 지금 `???`)는 엔드포인트의 모델 목록(`/models`)에서 Gemma 4 31B 항목을 찾아 정한다. 목록 조회에는 질의를 보내지 않는다
- 무료 등급 한도(2026-10-02 사용자 화면): Gemma 4 31B RPM 30, TPM 16K, RPD 14.4K. 근거 5개(약 2,500 KURE 토큰)와 지시를 합치면 요청 하나가 수천 토큰이라 분당 몇 번이 한도다. 확인 호출은 한 번에 하나씩 하고, 한도 오류(429)는 다시 시도하지 않고 그대로 보고한다

### 질의 제한

- 평가 질의(`summary_q`)는 이 경로로 보내지 않는다(CLAUDE.md 금지, D-01). `rag.generate`는 질의 파일을 읽지 않고 명령 인자로 받은 질의만 쓴다
- 확인용 질의는 직접 쓴다(아래 완료 기준 4·5). 데이터셋 질의를 옮겨 쓰지 않는다

### 기록

- 호출마다 `paths.generate_dir`(`data/runs/generate/`)에 JSON 하나를 쓴다: 질의, 모델 ID, `prompt_version`, 인덱스 이름, 근거 목록(번호, `doc_id`, `chunk_id`, 점수, 청크 원문, 회의 정보, `original`), 답변, 토큰 사용량, 시각
- 나중의 근거 기반 평가는 이 기록만으로 할 수 있어야 한다. `data/` 아래라 커밋하지 않는다

### 노트북과 결정 순서

S6에서 정하는 값(모델 ID, 문서 수 5, 프롬프트 v1)은 데이터나 점수를 보고 정하는 값이 아니다. 그래도 확인 결과를 노트북(`06_01`)으로 먼저 남기고 사용자에게 보인 뒤 DECISIONS에 기록한다.

## 명령

```
uv run python -m rag.generate "query=질문 문장"
```

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q` | 통과. API를 부르지 않는다. 포함: 문서별 최고 점수 청크 선택, 근거 번호·회의 정보가 들어간 프롬프트, URL이 프롬프트에 없고 근거 목록에 있음, 기록 JSON 필드 |
| 2 | `uv run ruff check .` | 통과(노트북 포함) |
| 3 | 모델 목록 조회 | Gemma 4 31B 모델 ID를 찾아 `generator.model`에 적음 |
| 4 | `rag.generate`로 회의록 주제 질의 3개(직접 작성) | 종료 코드 0, 답변이 비어 있지 않음, 근거 5개와 `original` URL 출력, 기록 JSON 저장 |
| 5 | `rag.generate`로 회의록과 무관한 질의 1개 | 종료 코드 0, 기록 저장. 답변이 근거 부족을 밝히는지는 관찰해 노트북에 적는다(통과 기준 아님) |
| 6 | 4의 질의 하나를 다시 실행 | 근거 목록(`doc_id`, `chunk_id`)이 같음. 답변 문구는 같지 않아도 된다 |
| 7 | 노트북 처음부터 실행 | 오류 없음, 4·5의 기록을 보여 줌 |
| 8 | 문서 기록 | `CLAUDE.md` "명령"에 생성 명령, PLAN S6 체크, DECISIONS에 모델 ID·근거 문서 수·프롬프트 v1, 이 문서 "실행 기록"에 호출 수·토큰 사용량 |

## 실행 기록

| 날짜 | 질의 | 모델 ID | 입력·출력 토큰 | 소요 시간 | 비고 |
| --- | --- | --- | --- | --- | --- |

## 수정 허용 파일

- `src/rag/generate.py`, `tests/test_generate.py`
- `configs/generator/gemma.yaml`, `configs/config.yaml`(`paths.generate_dir`)
- `notebooks/06_01_생성확인.ipynb`
- `docs/DECISIONS.md`, `docs/PLAN.md` S6 체크, `CLAUDE.md` "명령" 절, 이 문서

## 범위 밖

- 답변 품질·근거 기반 여부의 정량 평가(SPEC 개정 후)
- 생성 컨텍스트 단위 비교(H10), 재순위화·하이브리드 검색
- 한도 대기·재시도, 스트리밍, 대화 기록, 웹 UI·배포
- LangSmith 트레이싱
- `summary_q`를 넣는 생성 호출
