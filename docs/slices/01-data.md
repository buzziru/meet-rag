# S1 데이터 적재

라벨 zip(`data/{Training,Validation}/02.라벨링데이터/*.zip`)에서 검색 코퍼스와 평가 질의 파일을 재생성한다. 형식과 `doc_id` 규칙은 `docs/data.md` §16을 따른다.

## 만드는 것

- `data/processed/corpus_context.jsonl`: 고유 `context` 하나당 한 줄
- `data/processed/queries_summary_q.jsonl`: 질의응답쌍(라벨 json) 하나당 한 줄

## 규칙

- 입력은 라벨링데이터만 읽는다. 원천데이터(TS/VS)와 SbL은 읽지 않는다(`docs/data.md` §5)
- zip을 풀지 않고 `zipfile`로 읽는다. 라벨 json 파일은 `LAB_` 접두 `.json`만 대상으로 한다
- 정제는 `context` 완전 일치 중복 제거 하나뿐이다. 텍스트를 바꾸지 않는다(공백 정규화 없음, 짧은 문서 제거 없음)
- `doc_id = {conference_number}-{sha1(context, utf-8) 앞 10자리}`
- `qid = {conference_number}-{question_number}`. 전체에서 유일해야 하고, 중복이면 실패한다
- 코퍼스 메타데이터(`date`, `meeting_name`, `generation_number`, `committee_name`, `meeting_number`, `session_number`, `agenda`, `original`)는 그 문서를 정답으로 갖는 레코드 중 `qid`가 가장 작은 레코드에서 가져온다
- `splits`는 그 문서를 가진 레코드의 AI Hub 분할(`Training`/`Validation`)을 정렬한 목록, `n_qa`는 레코드 수
- 질의 필드: `qid`, `doc_id`, `split`, `qna_type`, `query`(=`context_summary.summary_q`), `answer`(=`summary_a`), `question_comment`, `answer_comment`
- 출력은 코퍼스는 `doc_id`, 질의는 `qid` 오름차순으로 쓴다. `ensure_ascii=False`, UTF-8
- 경로는 `configs/config.yaml`의 `paths.raw_dir`, `paths.corpus`, `paths.queries`를 쓴다

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run python -m rag.ingest` | 종료 코드 0, 두 파일 생성 |
| 2 | 코퍼스 줄 수, 고유 `doc_id` 수 | 둘 다 38,516 |
| 3 | 질의 줄 수, 고유 `qid` 수 | 둘 다 39,633 |
| 4 | 코퍼스 `splits` 분포 | `["Training"]` 34,139 / `["Validation"]` 4,206 / 둘 다 171 |
| 5 | 코퍼스 `n_qa` 합, 질의의 `doc_id`가 모두 코퍼스에 있는지 | 39,633, 모두 있음 |
| 6 | 1을 두 번 실행해 두 파일 SHA-256 비교 | 일치 |
| 7 | `uv run pytest -q` | 통과. 테스트는 합성 zip만 쓰고 `data/`를 읽지 않는다 |
| 8 | `uv run ruff check .` | 통과 |

## 수정 허용 파일

- `src/rag/__init__.py`, `src/rag/ingest.py`
- `tests/test_ingest.py`
- `CLAUDE.md` "명령" 절(적재 명령 한 줄 추가)
- `docs/PLAN.md` S1 체크, 이 문서

## 범위 밖

- 평가 분할(S2), 질의 필터(G1), 청킹(S4)
- 원천 xlsx·SbL 파싱, `date` 파싱, `keyword` 분해
- 발언이 자기 `context`에 없는 169건 처리. 문서 단위 정답은 성립하므로 그대로 둔다
