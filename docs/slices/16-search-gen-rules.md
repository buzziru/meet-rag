# S16 검색·생성 규칙 한 곳으로

코드 리뷰 2026-10(`docs/reviews/2026-10-code-review.md`)의 "검색·생성 규칙 한 곳으로" 묶음을 고친다. 평가(`rag.search`)와 생성(`rag.generate`)이 같은 규칙을 따로 구현해 두 결과가 우연히 같은 곳, 검색과 생성 사이 의존 방향이 거꾸로 된 곳, 생성이 설정을 무시하는 곳이다. 검색 순위와 생성 근거는 바뀌지 않아야 한다.

| 리뷰 ID | 위치 | 고치는 것 |
| --- | --- | --- |
| B-5 | `src/rag/search.py:185`, `:196-201`, `src/rag/generate.py:145-147`, `src/rag/retrieve.py:369-372` | 재정렬을 쓸지의 조건과 "후보 → 최종 top_k"를 `Retriever` 한 곳에 둔다 |
| B-6 | `search.py:26-35`, `:212`, `generate.py:51-84`, `g2.py:67-77`, `:120` | D-05 청크 선택과 청크 본문 읽기를 `rag.retrieve` 한 곳에 둔다. 청크 파일 이름도 한 곳에 둔다 |
| B-7 | `src/rag/rewrite.py:22`, `src/rag/gen_eval/judge.py:34`, `src/rag/gen_eval/checks.py:5` | 검색이 생성 모듈을, 생성 평가가 생성 모듈을 import하지 않게 한다. judge가 공유하는 조건 정규식을 judge 레시피에 남긴다 |
| C-3 | `generate.py:160-179`, `retrieve.py:356-366` | 생성에서 `retriever.rewrite`가 켜져 있으면 멈추고, 쓰지 않는 `explain`의 `rewrite` 인자를 지운다 |
| C-6 | `configs/prompt/v1.yaml:7`, `v2.yaml:9`, `configs/config.yaml:230` | 생성 프롬프트와 판정의 거부 문구가 어긋나면 멈춘다(결정 사항 1) |

## 만드는 것

### 최종 순위 (B-5)

- `Retriever`에 재정렬을 쓰는지(`use_rerank`: hybrid이고 `retriever.rerank.enabled`)를 둔다. `rag.search`(후보 쌍 내보내기 모드는 끔)와 `rag.generate`가 이 값을 읽는다
- `Retriever`에 결합 후보에서 최종 top_k를 내는 메서드 하나를 둔다. 결합 후보, 최다 일치 문서, 재정렬 점수를 받아 `final_order`(재정렬 → 최다 일치 필터) 뒤 `top_k`로 자른다. 재정렬 깊이는 재정렬 점수가 있을 때만 `retriever.rerank.depth`다. dense 단독이면 결합 후보를 그대로 돌려준다(이미 top_k)
- `search.finish`와 `explain`이 이 메서드를 부른다. `explain`은 순위를 따로 계산하지 않고 이 메서드의 결과에 단계 기록을 붙인다

예: `search.py:201`의 `docs[: r.top_k]`를 고치면 지금은 평가 순위만 바뀌고 생성 근거는 그대로다. 바꾼 뒤에는 두 경로가 같은 메서드를 불러 함께 바뀐다.

### 청크 선택과 본문 읽기 (B-6)

- `best_chunks`(문서마다 dense 점수가 가장 높은 청크, D-05)를 `rag.generate`에서 `rag.retrieve`로 옮긴다. `rag.search`의 후보 쌍(`search.py:212`)과 `rag.g2`(`g2.py:120`)도 이 함수를 쓴다
- 청크 번호로 본문을 읽는 구현 셋(`search.read_chunk_texts`, `generate.ChunkStore`, `g2.chunk_texts`)을 `rag.retrieve`의 하나로 줄인다. 생성은 질의마다 몇 개만 읽고 후보 쌍은 한 번에 수만 개를 읽으므로, 줄 위치를 들고 필요한 줄만 읽는 `ChunkStore` 방식에 여러 번호를 한 번에 읽는 메서드를 더한다
- 청크 파일 이름 `chunks.jsonl`을 `rag.index`의 상수 하나로 두고 `index`·`bm25`·`retrieve`가 쓴다

### 의존 방향 (B-7)

- `split_thought`·`answer_start`(Gemma 사고 과정 분리)를 새 모듈 `rag.llm`으로 옮긴다. `rag.rewrite`(검색)와 `rag.generate`가 여기서 import한다
- `git_state`를 `rag.generate`에서 `rag.index`(공용 모듈)로 옮긴다. `rag.gen_eval.judge`가 생성 모듈을 import하지 않게 된다. `write_guarded`는 S15에서 옮겼다
- `rag.gen_eval.checks`는 조건 정규식(`DATE`, `DOC_DATE`)을 계속 import하고, `judge_recipe`에 두 정규식의 패턴 문자열을 넣는다. 검색 개선으로 `conditions.DATE`를 바꾸면 judge 레시피가 달라져 이전 judge 결과와 섞이지 않는다. 정규식을 복사해 떼어 내지 않는 것은 같은 규칙이 두 곳에 생기기 때문이다(리뷰 제안)
- 과거 위치를 위한 재수출은 두지 않는다

### 생성의 재작성 설정 (C-3)

- `rag.generate.Pipeline`은 `retriever.rewrite.enabled`가 참이면 시작할 때 멈춘다. 생성 경로에 재작성이 없는데 레시피에는 `rewrite.enabled: true`가 남기 때문이다. 재작성은 EXP-013에서 기각됐다
- `Retriever.explain`의 `rewrite` 인자는 어디서도 넘기지 않으므로 지운다. `rag.search`의 재작성 경로는 `candidates(rewrite=...)`를 그대로 쓴다

예: `rag.generate +exp=exp013 ask.qid=…` → 지금은 재작성 없이 근거를 내고 레시피에 `rewrite.enabled: true`가 남는다. 바꾼 뒤에는 "생성은 retriever.rewrite를 지원하지 않는다"로 멈춘다.

### 거부 문구 (C-6)

결정 사항 1에 따른다. 권고 (a)면:

- `rag.gen_eval.judge`가 시작할 때 생성 기록 레시피의 `prompt_version`으로 `configs/prompt/<버전>.yaml`을 읽고, 그 `system`에 `gen_eval.refusal`이 들어 있지 않으면 멈춘다(공백 차이는 `refusal_split`과 같게 무시)
- 테스트가 `configs/prompt/*.yaml` 전부에 대해 같은 조건을 확인한다

### 테스트 (B-13)

- explain·search 순위 일치: 합성 인덱스에서 hybrid·조건 목록·재정렬 점수를 켠 설정으로 `rag.search`의 `finish` 경로와 `explain`이 같은 top_k를 낸다
- 조건 목록 경로: RRF 결합(`fusion.method: rrf`)에서 조건 목록이 `lists`에 들어가고 `filter: best`의 최다 일치 문서가 앞으로 오는 것을 `Retriever` 수준에서 확인한다(지금은 score 결합 경로만 있다)
- exp 전체 조합: `configs/exp/*.yaml` 17개를 parametrize해 합성 인덱스로 `Retriever`를 만들고 최종 순위 메서드로 질의 하나를 끝까지 낸다. 재정렬을 쓰는 exp는 합성 점수를 넘긴다. 재작성 exp(013)는 LLM을 부르지 않게 재작성 없이 순위를 내고, 생성 `Pipeline`이 멈추는지는 따로 확인한다. 합성 인덱스로 만들 수 없는 조합이 나오면 그 exp와 이유를 결과 절에 적는다
- 옮긴 함수: `best_chunks`·본문 읽기(여러 인덱스에 걸친 번호), `split_thought`의 기존 테스트를 새 위치로 옮긴다
- 거부 문구: 위 C-6 테스트

## 결정 사항

1. **거부 문구를 어디에 둘지 (C-6).** 지금 문구는 `configs/prompt/v1.yaml`·`v2.yaml`의 `system` 본문과 `configs/config.yaml`의 `gen_eval.refusal`에 따로 있다.
   - (a) 권고. 문구는 지금 자리에 두고, judge가 생성에 쓴 프롬프트 파일에 `gen_eval.refusal`이 있는지 확인해 없으면 멈춘다. 프롬프트 파일을 고치지 않으므로 `prompt_sha256`이 그대로이고, 기존 S14 생성 기록(v1, 20건)을 다시 채점할 수 있다. 예: v3에서 거부 문구를 "근거에서 찾을 수 없습니다"로 바꾸고 `gen_eval.refusal`을 그대로 두면 judge 호출 전에 멈춘다. 문구가 두 곳에 남으므로 v3를 만들 때 두 곳을 같이 고친다
   - (b) 프롬프트 파일에 `refusal` 키를 두고 `system`이 그 값을 넣어 쓰며, judge는 생성 기록의 프롬프트에서 문구를 읽는다. `gen_eval.refusal`은 지운다. 문구가 한 곳이 되지만 v1·v2 파일 내용이 바뀌어 `prompt_sha256`이 달라진다. 기존 S14 기록과 새 기록은 레시피가 달라 같은 파일에 이어 쓸 수 없고, "기록을 남긴 버전은 고치지 않는다"(v2 머리 주석) 규칙의 예외가 된다

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. 결과 불변(검색): `uv run python -m rag.search +exp=exp017 index.scope=dev-small`, `… index.scope=full`, `… index.scope=full search.queries=multidoc`가 각각 기존 순위 파일과 "같은 내용, 그대로 둠"으로 끝난다. 후보 쌍도 `search.mode=rerank-pairs`로 dev-small을 다시 내 기존 파일과 "같은 내용"으로 끝난다
3. 결과 불변(생성 근거): 기존 생성 기록 `data/gen_eval/runs/hybrid-cond-filter-law-ms256-k20-ce-v1-dev-small.jsonl` 20건의 qid로 `Pipeline.retrieve`만 불러(생성 API는 부르지 않는다) 근거의 (`doc_id`, `index`, `chunk_id`, `score`) 목록이 기록과 같다
4. 멈춤: `rag.generate +exp=exp013 ask.qid=<dev qid>`가 API 호출 전에 rewrite로 멈춘다
5. `rag.rewrite`·`rag.gen_eval.judge`가 `rag.generate`를 import하지 않는다(`grep`)
6. test 분할 질의를 읽는 명령은 돌리지 않는다. 외부 API(생성·judge·재작성)는 호출하지 않는다

## 수정 허용 파일

- `src/rag/retrieve.py`, `search.py`, `generate.py`, `g2.py`, `rewrite.py`, `index.py`, `bm25.py`, `llm.py`(새 파일)
- `src/rag/gen_eval/judge.py`, `checks.py`(결정 사항 1이 (b)면 `configs/prompt/v1.yaml`·`v2.yaml`, `configs/config.yaml`의 `gen_eval.refusal`)
- `tests/test_search.py`, `test_generate.py`, `test_g2.py`, `test_rewrite.py`, `test_gen_eval.py`, `test_fusion.py`, 새 테스트 파일 `tests/test_exp_configs.py`
- `docs/slices/16-search-gen-rules.md`, `docs/PLAN.md`, `docs/reviews/2026-10-code-review.md`(진행 표시)

## 범위 밖

- 실시간 재정렬과 H10 근거 구성(리뷰 3d). 이 조각은 그 변경이 고칠 곳을 줄이는 데까지다
- `lists()`의 플래그 정리와 `fuse: false`·`rrf` 조합의 KeyError(B-8), `Retriever.rank`·`rrf` 정리(B-9), 가중치 위치 대응(B-10), 기본값 위치(B-11). exp 전체 조합 테스트에서 B-8 조합에 닿으면 고치지 않고 결과 절에 적는다
- 순위 파일 이름 규칙(A-5), 근거 `score`의 뜻(C-15), 질의 임베딩 캐시(C-11, B-12)
- 평가 쪽 묶음(D-8, D-2)과 보호 경로 전부
- 테스트 속도(E-1, E-2)
