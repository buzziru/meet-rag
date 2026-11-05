# S46 생성 단계 test 경로

생성 단계를 마칠 때 `test` 분할로 1회 실행하려면 `rag.gen_eval`이 test 질의를 읽을 수 있어야 한다(D-87 결정 8). 이 조각은 그 경로만 만든다. 실행은 사용자 지시를 받아 따로 한 번 하고, 이 조각의 구현·검증에서는 `test` 질의를 읽거나 보내지 않는다.

## 지금 막혀 있는 곳

- `gen_eval.common.eval_qids`가 층을 `dev-small`, `dev-full`만 받는다(`src/rag/gen_eval/common.py:15`)
- `gen_eval.generate.main`이 질의 원문을 dev 전용 `paths.queries_dev`에서, 임베딩을 `paths.query_emb`에서 읽는다(`src/rag/gen_eval/generate.py:124`, `:127`). test 임베딩은 `paths.query_emb_test`다
- S13 test 질의 임베딩과 재정렬 점수에 지문 파일(`.basis.json`)이 없다. S13 뒤에 지문 대조(S15, S21)가 생겨, 지금은 `read_query_emb`와 `read_rerank_scores`가 읽기 전에 멈춘다(`src/rag/index.py:123`)
- `rag.eval.score --layer test`는 층 전체를 요구해(`src/rag/eval/metrics.py:81`) 800질의 검색 지표를 내지 못한다. 보호 경로라 고치지 않는다
- `rag.gen_eval.report`에 D-87 결정 3의 "인용 없는 답변" 칸이 없다. 노트북에서만 세었다(`notebooks/48_01_S44_답없는부분.ipynb`)

## 만드는 것

- **test 층 허용:** `gen_eval.queries=test`는 `gen_eval.allow_test=true`가 없으면 라벨 파일을 읽기 전에 멈춘다. `search.queries=test`, `search.allow_test=true`도 함께 있어야 한다. 재정렬 점수 경로가 `search.queries`로 정해지므로, 어긋나면 dev 점수를 읽게 되기 때문이다
- **질의 수 고정:** `gen_eval.test_n: 800`(D-87 결정 1)을 config에 두고, test 층에서 `gen_eval.n`이 이 값과 다르면 멈춘다. 표본은 지금의 `sample_qids`를 `gen_eval.seed`로 그대로 쓰고 뺄 질의는 없다
- **test 1회 제약:** test 층에서 아래 중 하나면 생성·judge가 호출 전에 멈춘다
  - 환경 변수 `LANGSMITH_TRACING`이 `false`가 아님(D-72, D-87 결정 7)
  - `gen_eval.gen_rep`이나 `judge.rep`이 0이 아님, `gen_eval.contexts`가 `retrieved`가 아님(D-87 결정 2)
- **입력 대조:** `gen_eval.test_inputs`에 S13 실행 기록의 SHA-256 앞자리를 둔다. 생성은 시작할 때 파일을 열어 내용을 쓰기 전에 해시를 대조하고, 다르면 멈춘다(D-87 결정 6). 대상은 질의 임베딩 `snowflake-ko/queries-test.npz` `8f828601`, 후보 쌍 `test-full-ms256-k20.pairs.jsonl` `018f1544`, 점수 `test-full-ms256-k20-cross-encoder.scores.jsonl` `c8dea3ee`, 순위 `snowflake-ko-fixed-512-64-hybrid-cond-filter-law-ms256-k20-ce-test.csv` `d905a3d3`다
- **질의 입력:** test 층의 질의 원문은 `paths.queries`에서 표본 qid만 읽고, 임베딩은 `paths.query_emb_test`를 읽는다
- **800질의 검색 지표:** 새 모듈 `rag.gen_eval.retrieval`. 아래 "검색 지표 방법"대로 낸다
- **보고 칸:** `rag.gen_eval.report` 코드 판정 표에 "인용이 전혀 없는 답변"을 더한다. 정의는 S44 노트북과 같게 한다. 나머지 D-87 결정 3 지표는 이미 나온다(회의 표기는 "회의 일자·위원회 불일치가 있는 답변" 칸이다)
- **`compare` 제외:** `rag.gen_eval.compare`는 gen-full 고정이고 override를 받지 않아 test를 쓸 수 없다. 테스트로 묶어 둔다

## 검색 지표 방법

D-87 결정 3의 "같은 800질의의 검색 지표"는 S13 순위 파일에서 낸다. 검색을 다시 돌리지 않고 보호 경로도 고치지 않는다.

1. 순위 파일을 `test_inputs`의 해시로 대조한다
2. `load_gold(cfg, "test", allow_test=True)`와 순위 파일을 `eval_qids`의 800질의로 줄인다
3. `rag.eval.metrics`의 `gold_ranks`, `per_query`, `metric_table`을 불러 계산한다(지표 정의를 새로 쓰지 않는다, `src/CLAUDE.md`)
4. 생성 기록의 근거 문서 순서가 순위 파일의 상위 `context_docs`개와 같은지 질의마다 본다. 다르면 멈춘다. 지금 검색 코드가 S13과 다른 순위를 내면 지표가 답변의 입력을 설명하지 못하기 때문이다

질의 원문은 출력하지 않는다. 결과는 `write_guarded`로 `data/` 아래에 쓴다.

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .`, `uv run pytest -q .claude/skills/meet-rag/scripts .claude/hooks` 통과
- 합성 입력 테스트(진입점 `main`을 지나 결과를 단언한다, `tests/CLAUDE.md`)
  - 허용 없이 `gen_eval.queries=test`를 주면 라벨을 읽기 전에 멈춘다. `search.queries`가 어긋나거나, `n`이 `test_n`과 다르거나, 반복 번호가 0이 아니거나, 추적이 켜져 있어도 호출 전에 멈춘다
  - 입력 해시가 다르면 멈춘다
  - 합성 test 층에서 질의 원문과 임베딩을 test 쪽 파일에서 읽고, 기록 경로가 dev와 겹치지 않는다
  - 검색 지표가 표본 질의만으로 계산되고, 근거 문서와 순위가 다르면 멈춘다
- 망가뜨린 사본 확인(`tests/CLAUDE.md`): 허용 검사를 뺀 사본에서 해당 테스트가 실패한다
- dev 불변: `eval_qids`가 내는 gen-full 330질의와 gen-small 20질의의 해시가 구현 전후로 같고, `recipe`가 같다(유료 호출 없음)
- 검색 지표 방법을 dev로 확인: gen-small v19 생성 기록과 dev-full 순위 파일로 4단계의 일치 대조를 지난다(유료 호출 없음, 근거 내용은 읽지 않는다)
- S13 입력 대조: 네 파일의 SHA-256 앞자리가 위 값과 같다. 다르면 구현을 멈추고 보고한다(D-87 결정 6). 해시만 재고 내용은 읽지 않는다
- 지문: 질의 임베딩과 재정렬 점수의 만든 설정을 S13 실행 기록과 대조한 뒤 `adopt_basis=true`로 지문만 쓴다(S15, S21과 같은 방식). 파일을 열지 않는다. 대조에서 어긋나면 보고한다
- 이 조각의 구현·검증은 `test` 질의, 라벨, 순위, 점수의 내용을 읽지 않고 외부로 보내지 않는다

## 1회 실행 절차 (사용자 지시 뒤, 이 조각 밖)

공통 인자 `<T>` = `+exp=current gen_eval.queries=test gen_eval.n=800 gen_eval.allow_test=true search.queries=test search.allow_test=true`

1. 비피크인지 확인한다(아래 "비용·시간")
2. `LANGSMITH_TRACING=false doppler run -- uv run python -m rag.gen_eval.generate <T>`
3. `LANGSMITH_TRACING=false doppler run -- uv run python -m rag.gen_eval.judge <T>`
4. `uv run python -m rag.gen_eval.report <T>`, `uv run python -m rag.gen_eval.retrieval <T>`
5. 입력과 결과 파일의 SHA-256, 실행 커밋을 기록하고 gen-full 값과 나란히 적는다(D-87 결정 4). 결과를 보고 지표를 더하거나 빼지 않는다(결정 3). 기준 설정을 바꾸지 않는다(결정 5)
6. DECISIONS에 결과와 생성 단계 종료를 적고, PLAN·STATUS를 갱신한다. `CLAUDE.md` 명령 절에 실행을 마쳤다는 줄을 둔다. 다시 돌리지 않도록 명령은 적지 않는다(S13과 같다)

호출 실패로 중간에 멈추면 같은 명령으로 이어 쓴다. 이미 쓴 질의는 다시 부르지 않고 레시피가 다르면 멈추는 지금 동작 그대로라, 새 실행이 아니라 같은 1회의 이어 쓰기로 본다.

## 비용·시간

실행 승인 때 다시 보고한다. 이 조각의 구현에는 유료 호출이 없다.

| 단계 | 호출 | 비용 | 시간 |
| --- | --- | --- | --- |
| 생성 800질의 | 800회 | 약 $0.32(v19 gen-full 재생성 $0.13 비례) | 약 20분(330회 8분 비례) |
| judge 800질의 | 약 5,900회 | 비피크 약 $3.8, 피크 약 $7.7 | 약 55분(동시 8, 230질의 15분 22초 비례, D-51) |

- judge 어림: 세트 밖 100질의 j_v13 기록의 전체 737회 토큰(입력 1,375,240, 그중 캐시 적중 452,224, 출력 565,818)을 공개 요금에 곱하면 비피크 $0.479다. 저장 응답을 쓴 호출도 원래 토큰으로 더했다. test는 저장 응답이 없어 모두 새 호출이기 때문이다. 청구액이 아니라 어림이다
- 합계 비피크 약 $4.2로 D-87의 judge $5 안이다. 피크에 돌리면 넘는다
- 피크는 평일 01:00\~04:00, 06:00\~10:00 UTC이고 나머지와 주말은 비피크다(opencode Go 문서, 2026-11-05 확인). 한국 시간으로 평일 10\~13시, 15\~19시다. 약 75분이 걸리므로 평일 19시 뒤나 주말에 시작한다
- opencode Go 월 사용 한도에서 차감된다. 5시간 한도 $20, 주간 $50, 월 $100(같은 문서)보다 적다. 지금 쓴 양은 확인하지 않았다

## 결정 사항

사용자가 정할 것은 없다. D-87이 범위·설정·지표·입력·추적을 정했고, 아래는 메인이 그 의도에 맞춰 정한 것이다.

- 검색 지표는 S13 순위 파일을 줄여 낸다(위 방법). 입력→동작: 지금 검색이 S13과 다른 순위를 내면 4단계에서 멈추고 보고한다
- 중간 실패의 이어 쓰기는 1회에 포함한다. 입력→동작: judge가 500번째에서 멈추면 같은 명령으로 나머지만 부른다. `judge.rep=1`로 다시 채점하면 멈춘다

## 수정 허용 파일

- `src/rag/gen_eval/common.py`, `generate.py`, `judge.py`(test 1회 제약 호출만), `report.py`(보고 칸 한 줄과 집계), 새 `src/rag/gen_eval/retrieval.py`
- `configs/config.yaml`의 `gen_eval`(`allow_test`, `test_n`, `test_inputs`)
- `tests/test_gen_eval.py`
- 완료 처리: 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`, `CLAUDE.md` 명령 절(1회 실행 호출법을 적지 않고 이 문서만 가리킨다)

`report.py`를 고치므로 병합 전에 self-review를 한다(`.claude/rules/git.md` PR 절 2).

## 범위 밖

- 생성 test 1회 실행(PLAN 다음 항목, 사용자 지시)
- `src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`, `data/splits/`(보호 경로)
- judge 지시·판정표·기본 judge 설정(D-49 동결)
- 기준선 실행(D-87 결정 2), 짝 비교(결정 4)
- Colab(D-87 결정 6)
