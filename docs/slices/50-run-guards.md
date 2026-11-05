# S50 평가·실행 안전장치

전체 파이프라인 점검이 고른 C 항목 6건을 고친다(`docs/reviews/2026-11-pipeline-review.md`). 재현 코드를 공개하기 전에, 조용히 틀리거나 원인을 모른 채 멈추는 경로를 막는다. 지표 값과 기준 설정은 바뀌지 않는다. 실제로 일어난 기록은 없고, 재현은 합성 입력이거나 코드에서 추론한 것이다.

## 만드는 것

- **R2-3 `reason` 형식 검사:** `valid_verdicts`(`src/rag/gen_eval/judge.py:249`)는 `reason`을 보지 않는데 `speaker_mismatch`(`src/rag/gen_eval/report.py:71`)는 `v["reason"]`을 읽는다. 없으면 judge를 다 돌린 뒤 report와 compare가 `KeyError`로 멈추고, 응답이 캐시에 남아 다시 돌려도 같다. `reason`이 문자열이 아니면 형식 오류로 보고 기존 재요청 경로를 탄다
- **R1-2 질의 임베딩 캐시 덮어쓰기:** `embed_vm_queries`(`src/rag/search.py:133`)가 방지 없이 쓴다. 로컬에서 실행하면 Colab 캐시가 CPU 값으로 바뀌고 지문 대조도 지난다. 시작할 때 `refuse_existing`으로 멈춘다. 다시 만들려면 `search.overwrite=true`다
- **R1-4 BM25 행 수 대조:** `Retriever`(`src/rag/retrieve.py:390`)가 dense와 달리 BM25 행 수를 `chunks.jsonl`과 대조하지 않는다. 시점이 다른 두 파일을 읽으면 행이 적을 때 다른 문서와 오류 없이 짝지어진다. 불러올 때 대조하고 다르면 멈춘다
- **R1-5 `rag.rerank`의 test 차단:** `search.queries=test`이면 test 후보 쌍을 가리키는데 `allow_test`를 보지 않는다(`src/rag/rerank.py:158`). cross-encoder는 점수 파일이 있어 멈추지만, 이름이 다른 `jev` backend는 지나 외부 API로 보낼 수 있다. `rag.search`의 `check_test`와 같은 검사를 `main` 앞에 둔다
- **R1-8 안내 문구:** `src/rag/generate.py:209`, `:242`가 "실시간 재정렬은 배포 SLICE에서 만든다"고 적는다. S39에서 만들었으므로, 자유 질의는 앱 경로가 재정렬한다고 고친다
- **R2-5 잘린 기록 줄의 오류:** `read_jsonl`(`src/rag/gen_eval/common.py:123`)이 강제 종료로 잘린 줄에서 위치 없이 `JSONDecodeError`를 낸다. 파일과 줄 번호를 적고 멈춘다. 잘린 줄을 건너뛰지는 않는다. 어디까지 썼는지 사람이 확인해야 값이 조용히 빠지지 않기 때문이다

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .` 통과
- 합성 입력 테스트(진입점을 지나 결과를 단언한다, `tests/CLAUDE.md`)
  - `reason`이 빠진 `verdicts` 응답은 재요청되고, `reason`이 있는 응답은 전처럼 지난다
  - 질의 임베딩 캐시가 있으면 `embed-queries`가 임베딩 전에 멈추고, `search.overwrite=true`면 쓴다
  - BM25 행 수와 청크 행 수가 다르면 불러올 때 멈춘다
  - `search.queries=test`에 `search.allow_test=true`가 없으면 `rag.rerank`가 후보 쌍을 읽기 전에 멈춘다
  - 잘린 줄이 든 파일에서 `read_jsonl` 오류가 경로와 줄 번호를 담는다
- 망가뜨린 사본 확인: 추가한 검사를 뺀 사본에서 해당 테스트가 실패한다
- 값 불변(유료 호출 없음)
  - `rag.gen_eval.report +exp=current`의 출력이 구현 전후로 같다(gen-full)
  - `+exp=current`의 생성·judge 레시피가 구현 전후로 같다
  - gen-full judge 기록의 `verdicts`가 모두 새 검사를 지난다. 내용은 출력하지 않고 건수만 본다. test 기록은 세지 않는다
  - 실제 full 인덱스에서 `Retriever`가 새 행 수 대조를 지나 불러와진다

## 결정 사항

메인이 앞 결정으로 정한 것이다. 어긋나면 지시서 확인 때 말씀해 주세요.

- R2-3은 D-49 동결 대상이 아니라고 본다. D-49와 D-58 결정 6이 동결한 것은 judge 지시, 모델, temperature, 형식 교정 지시 파일(`fr_v1`), 재요청 상한, 판정표다. 응답을 받는 검사는 목록에 없고, 지시도 `reason`을 이미 요구한다. 새 지시 버전과 재검증을 두지 않는다. 입력→동작: `reason`이 있는 저장 응답은 재요청 없이 그대로 읽혀 캐시 키와 점수가 같다. `reason`이 빠진 응답이 오면 전에는 report에서 멈췄고, 이제 그 자리에서 재요청한다
- 생성 단계 test는 끝났으므로(D-90) 이 조각의 어떤 확인도 test 기록을 열거나 test 경로를 실행하지 않는다

## 사용자 작업

없다.

## 수정 허용 파일

- `src/rag/gen_eval/judge.py`(`valid_verdicts`), `src/rag/gen_eval/common.py`(`read_jsonl`)
- `src/rag/search.py`, `src/rag/rerank.py`, `src/rag/retrieve.py`(BM25 대조), `src/rag/generate.py`(문구)
- `tests/`의 해당 테스트
- 완료 처리: 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`

`judge.py`와 `common.py`는 병합 전 self-review 범위(`compare.py`, `report.py`, `checks.py`, `src/rag/eval*`)에 들지 않는다(`.claude/rules/git.md` PR 절 2).

## 범위 밖

- 점검 D 항목(R1-3, R1-6, R2-1, R2-2 등. 고치지 않기로 함)
- `docs/reviews/2026-11-pipeline-review.md`의 B 항목(`deploy` S49)
- judge 지시, 판정표, 기본 judge 설정, 보호 경로
- 유료 호출, Colab, 재실행

## 결과 (2026-11-05)

커밋: 구현 9e7ae2b

- 테스트: `uv run pytest -q` 557개 통과, ruff 통과, `.claude/skills/meet-rag/scripts`와 `.claude/hooks` 138개 통과
- 망가뜨린 사본(플러그인으로 끼움): `reason` 검사, `refuse_existing`, BM25 대조, `check_test`, 새 `read_jsonl`을 하나씩 뺀 사본에서 해당 테스트가 실패한다
- `rag.gen_eval.report +exp=current` 출력이 구현 전후로 바이트까지 같다(gen-full)
- judge 레시피: 지금 설정으로 만든 값과 gen-full 기록의 값이 20개 키 모두 같다. `configs/`는 바꾸지 않았다
- gen-full judge 기록의 `verdicts` 321질의가 모두 새 검사를 지난다. 건수만 봤다
- 실제 full 인덱스: BM25 118,039행과 청크 118,039개가 같아 `Retriever`가 불러와진다
- test 기록은 열지 않았고 test 경로는 실행하지 않았다. 유료 호출 없음

### 지시서와 다르게 한 것

- `src/rag/bm25.py`를 수정 허용 목록 밖에서 고쳤다. `BM25Retriever.num_docs` 속성 하나로, `Retriever`가 bm25s 내부 값을 직접 읽지 않게 하려는 것이다
- `rag.rerank`가 `rag.search`의 `check_test`를 `main` 안에서 불러 쓴다. 검사 정의를 다시 쓰지 않으려는 것이고(`src/CLAUDE.md`), Space가 `rag.rerank`를 불러오므로(`deploy/space/app.py:25`) 시작 경로를 늘리지 않으려고 모듈 머리에 두지 않았다
- `docs/slices/05-retrieve.md`에 `이후 변경`을 붙였다(수정 허용 목록 밖). `embed-queries` 동작이 바뀌어 `docs/CLAUDE.md` 당시 기록 절이 요구한다
- Space 시작 때 `Retriever`도 새 BM25 대조를 지난다. 로컬 full 인덱스에서만 확인했고 Dataset 사본은 다음 Space 업로드에서 처음 확인된다
