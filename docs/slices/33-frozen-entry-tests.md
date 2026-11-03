# S33 동결 세트 대조를 진입점에서 검증

G3 동결 세트의 sha256 대조(D-62)는 `rag.eval_multi.metrics.frozen_path`에 있다. `tests/test_eval_multi.py:206`은 이 함수와 `read_queries`만 불러, `rag.eval_multi.score.main`, `rag.eval_multi.compare.main`, `rag.search.search`에서 대조를 없앤 사본도 테스트를 통과한다(일일 코드 리뷰 시험 지적, ADR-0081). 세트가 바뀌면 multi-doc 채점·비교·메타데이터 가설 판정이 D-16 기준선과 다른 세트로 조용히 이어진다.

## 만드는 것

- `tests/test_eval_multi.py`: `score.main`, `compare.main`이 동결 파일을 한 글자 바꾼 입력에서 "G3 동결 값" 오류로 멈추고, 맞는 입력에서는 결과를 낸다
- `tests/test_search.py`(또는 같은 파일): `search(cfg)`가 `search.queries=multidoc`에서 동결 파일이 다르면 순위 파일을 쓰기 전에 멈춘다. `Retriever`는 합성 객체로 바꿔 인덱스·모델을 불러오지 않는다. 맞는 입력의 동작은 `query_list`까지만 본다
- `src/rag/speakers.py:132-133`: 확인용 출력에서 빈 `comment`를 `found`·`repeat`에 세지 않는다. 빈 문자열은 어떤 본문에도 들어 있어 값이 부풀려진다. 사례: 답변 발언이 빈 QA → 지금 `answer.found`가 1 늘고 `repeat`도 는다, 고친 뒤 늘지 않는다. 이 값은 확인용 출력이고 `doc_spans`와 생성 입력은 바꾸지 않는다

`src/rag/eval_multi/`는 보호 경로라 고치지 않는다. 테스트만 더한다.

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | 변형 사본 3종(pytest 플러그인, 저장소 파일은 그대로): `score.main`, `compare.main`, `search`의 `query_list`에서 `frozen_path`를 대조 없는 경로 반환으로 바꿈 | 각 사본에서 새 테스트가 실패한다 |
| 3 | `tests/test_speakers.py`의 확인용 출력 테스트 | 빈 `comment`를 세지 않고, 빈 값이 아닌 발언의 수는 그대로다 |

유료 호출과 Colab은 쓰지 않는다. `data/`는 읽지 않고 합성 입력만 쓴다.

## 수정 허용 파일

`tests/test_eval_multi.py`, `tests/test_search.py`, `tests/test_speakers.py`, `src/rag/speakers.py`(확인용 출력의 두 줄), 이 문서, `docs/PLAN-done.md`

## 범위 밖

- `src/rag/eval_multi/` 코드 변경(보호 경로)
- 노트북이 동결 파일을 직접 읽는 경로(D-62 감수)
- 일일 리뷰의 다른 항목, 빠진 경계 테스트(`check_speaker_judge`의 `j_v9`, 버전 없음)

## 결과 (2026-11-03)

커밋: 구현 1626e17

- 완료 기준 1: `uv run pytest -q` 390 통과, `uv run ruff check .` 통과
- 완료 기준 2: `score.main`, `compare.main`, `search`의 `frozen_path`를 대조 없는 경로 반환으로 바꾼 사본 3종에서 해당 진입점 테스트가 모두 실패했다(저장소 파일은 그대로, pytest 플러그인). 정답 문서 하나만 바꾼 입력이라 대조가 없으면 오류 없이 이어지다 `pytest.raises`에서 실패한다
- 완료 기준 3: `tests/test_speakers.py::test_count_found_skips_empty_comment` 통과. 확인용 출력을 `count_found`로 나눴고 `doc_spans`와 생성 입력은 그대로다

### 지시서와 다르게 한 것

- search 테스트도 `tests/test_eval_multi.py`에 뒀다. 합성 동결 세트 도구를 함께 쓰기 때문이다
