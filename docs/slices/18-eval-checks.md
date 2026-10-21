# S18 평가 쪽: 메타데이터 판정 함수와 정답 읽기 테스트

코드 리뷰 2026-10(`docs/reviews/2026-10-code-review.md`)의 "평가 쪽" 묶음을 고친다. 판정 규칙 하나가 코드에 없어 사람이 JSON을 읽어 손으로 적용하는 곳(D-2)과, 검색·채점·생성 평가의 질의 목록을 정하고 test를 막는 함수에 테스트가 없는 곳(D-8)이다. 보호 경로(`src/rag/eval/`, `src/rag/eval_multi/`)를 고치므로 이 지시서 확인이 수정 승인이고, 결과를 DECISIONS에 적는다(CLAUDE.md 금지 절).

| 리뷰 ID | 위치 | 고치는 것 |
| --- | --- | --- |
| D-2 | `src/rag/eval/bootstrap.py:20-25`, `src/rag/eval_multi/compare.py:1-3` | SPEC "메타데이터 가설의 판정"(D-18, D-35)을 함수로 두고 multi-doc 비교가 결과를 낸다 |
| D-8 | `src/rag/eval/metrics.py:26-56` `load_gold` | 합성 파일로 분할·층·test 차단 테스트를 붙인다(코드는 바꾸지 않는다) |

## 만드는 것

### 메타데이터 판정 함수 (D-2)

- `rag.eval.bootstrap`에 `metadata_verdict(single, recall5, complete5_hi, min_gain)`를 둔다. SPEC 절을 그대로 옮긴다
  1. single-doc 판정이 채택이면 채택, 기각이면 기각
  2. 보류이면 multi-doc으로: Recall@5 차이의 (점 추정, 하한, 상한)으로 기존 `verdict`를 쓰고, 채택이 나와도 Complete@5 차이 95% 구간 상한이 0보다 작으면 보류로 둔다
- 반환은 채택·기각·보류와 어느 단계에서 정해졌는지(single-doc, multi-doc)다. D-35에 따라 +1.0%p 미만이고 Recall@5 하한 > 0인 보류를 예외로 올릴지는 함수가 정하지 않는다. 그 경우는 exp-judge 판정 보고에서 예외 검토 대상으로 적는다
- `rag.eval_multi.compare`에 선택 인자 `--single <single-doc 비교 결과 JSON>`를 둔다. 주면 그 JSON의 `verdict`와 multi-doc 전체 행(`group: all`)의 `recall@5`·`complete@5`로 `metadata_verdict`를 계산해 결과에 `metadata_verdict`를 더한다. 주지 않으면 지금처럼 판정 라벨을 내지 않는다(SPEC "보조 관찰": 메타데이터 가설이 아니면 multi-doc에 판정 라벨을 붙이지 않는다). 결정 사항 1
- single-doc 결과 JSON이 dev-full 비교(`layer`)이고 `verdict`가 있는지 읽을 때 본다. 아니면 멈춘다. `min_gain`은 single-doc 결과에 기록되지 않는다(`rag.eval.compare`는 보호 경로이고 이 조각에서 고치지 않는다). 그래서 기록된 차이·구간을 지금 `min_gain`으로 다시 판정해 기록된 `verdict`와 다르면 멈춘다. 예: `min_gain` 0.01일 때 채택(+1.5%p, 하한 > 0)으로 기록된 결과를 0.02인 config로 넣으면 다시 판정한 값이 보류라 멈춘다
- 결과의 `metadata_verdict`에 읽은 single-doc 결과의 경로와 sha256을 남긴다(순위 파일과 같은 방식)
- single-doc 결과가 같은 실험의 비교인지 순위 파일 이름으로 본다. `rag.search`의 이름 규칙(`<인덱스>-<설정 이름>-<평가 층>.csv`)에서 single-doc 결과의 base·cand 이름에서 `-dev-full.csv`를 뗀 것과 `--base`·`--cand`에서 `-multidoc.csv`를 뗀 것이 다르면 멈춘다(가이드 판단할 곳 2, 사용자 결정 2026-10-21). 예: EXP-008 순위 쌍에 EXP-003 결과를 넣으면 멈춘다. 이름을 손으로 바꾼 순위 파일은 같은 실험이어도 멈춘다

예: EXP-008처럼 single-doc 보류, multi-doc Recall@5 +1.65%p [+0.91, +2.49], Complete@5 [+2.00, +4.83]이면 `{"verdict": "채택", "stage": "multi-doc"}`. multi-doc Recall@5 +0.8%p [+0.2, +1.4]이면 보류(D-35의 예).

### 정답 읽기 테스트 (D-8)

`load_gold`를 합성 분할·질의·코퍼스·dev-small 목록 파일로 부른다(경로는 config override). 확인하는 것:

- dev 층은 분할 `dev`의 질의만, dev-small은 그중 dev-small 문서의 질의만 담는다
- test 층은 `allow_test` 없이 멈추고, 있으면 `test` 질의만 담는다
- 모르는 층 이름은 오류
- `meeting_name`은 코퍼스에서, `conference_number`는 분할 파일에서 붙는다
- 결과는 qid 순으로 정렬된다

## 결정 사항

1. **판정 라벨을 어디서 낼지.** 결정: (a)(사용자 결정 2026-10-21). 보호 경로 수정은 이 지시서 확인으로 승인받았다(같은 날)
   - (a) 권고. `rag.eval_multi.compare --single <JSON>`일 때만 낸다. 메타데이터 가설이 아닌 EXP의 multi-doc 결과에는 지금처럼 라벨이 없다. 명령 하나 더(인자 하나)로 exp-judge가 손으로 적용하던 것을 대신한다. 예: `rag.eval_multi.compare --base … --cand … --single data/runs/exp008-compare.json` → 결과 JSON 끝에 `"metadata_verdict": {"verdict": "채택", "stage": "multi-doc", …}`
   - (b) 별도 명령(`rag.eval.metadata --single <JSON> --multi <JSON>`)이 두 비교 결과 파일을 읽어 판정한다. 비교 모듈은 그대로 두지만 모듈이 하나 늘고, multi-doc 결과 JSON의 행 구조에 기댄다

## 완료 기준

1. `uv run pytest -q`, `uv run ruff check .` 통과
2. 판정 재현: 지난 메타데이터 가설 EXP 중 multi-doc 단계까지 간 EXP-003·004·008의 기준·후보 순위 파일(EXP 문서 실행 기록)로 single-doc 비교(`rag.eval.compare`)와 `rag.eval_multi.compare --single`을 돌려 `metadata_verdict`가 EXP 문서의 결론(셋 다 multi-doc 단계 채택)과 같다. single-doc 단계에서 끝난 EXP-002는 기각이 나온다. 결과 JSON은 `data/runs/`에 새 이름(`s18-…`)으로 쓰고 기존 파일을 덮어쓰지 않는다. 순위 파일이 없는 EXP는 결과 절에 적는다
3. 기존 출력 불변: `--single` 없이 돌린 multi-doc 비교 결과가 이전 코드의 결과와 같다(EXP-008 한 쌍)
4. test 분할 질의를 읽는 명령은 돌리지 않는다(D-8은 합성 파일로만). 외부 API는 호출하지 않는다

## 수정 허용 파일

- `src/rag/eval/bootstrap.py`, `src/rag/eval_multi/compare.py`(보호 경로, 이 지시서 확인으로 승인)
- `tests/test_eval.py`, `tests/test_eval_multi.py`
- `docs/DECISIONS.md`(D-2 반영 기록), `docs/slices/18-eval-checks.md`, `docs/PLAN.md`, `docs/reviews/2026-10-code-review.md`(진행 표시)

## 범위 밖

- exp-judge 에이전트·exp-judgment 스킬이 이 함수를 쓰게 바꾸는 것: 하네스라 F 흐름의 후속 PR로 한다. 이 조각 뒤에도 그 전까지는 손으로 적용하되 함수 결과와 대조할 수 있다
- 다른 평가 쪽 낮음 항목(D-1, D-3, D-6, D-7, D-9 경계값 테스트, D-10, D-11)
- `load_gold` 코드 변경
- B-8(`fuse: false`·`rrf` 조합). 이 조각 다음(사용자 결정 순서)

## 결과 (2026-10-21)

- 구현 커밋 03feb1e. 테스트 234 → 246개, `uv run pytest -q`·`uv run ruff check .` 통과. DECISIONS D-43
- 판정 재현(`data/runs/s18-expNNN-single.json`, `s18-expNNN-multidoc.json`에 새로 씀)

| EXP | single-doc Recall@5 차이 [95% 구간] | single-doc 판정 | multi-doc Recall@5 차이 [구간] | Complete@5 구간 | metadata_verdict | EXP 문서 결론 |
| --- | --- | --- | --- | --- | --- | --- |
| 002 | −2.62%p [−4.02, −1.39] | 기각 | +15.32%p [+13.19, +17.49] | [+10.67, +16.50] | 기각(single-doc) | 기각(single-doc 단계) |
| 003 | +0.00%p [0.00, 0.00] | 보류 | +14.71%p [+12.82, +16.64] | [+10.83, +16.33] | 채택(multi-doc) | 채택(multi-doc 단계) |
| 004 | −0.03%p [−0.10, 0.00] | 보류 | +35.54%p [+32.24, +38.81] | [+39.83, +48.00] | 채택(multi-doc) | 채택(multi-doc 단계) |
| 008 | +0.00%p [0.00, 0.00] | 보류 | +1.65%p [+0.91, +2.49] | [+2.00, +4.83] | 채택(multi-doc) | 채택(multi-doc 단계) |

- 출력 불변: EXP-008 쌍을 `--single` 없이 `main`의 `rag/eval_multi/compare.py`와 이 브랜치 코드로 돌린 출력이 바이트까지 같다
- 지시서와 달라진 것: single-doc 결과 JSON에 `min_gain`이 기록되지 않아(`rag.eval.compare`는 수정 허용 밖) `min_gain` 값을 직접 대조하지 않는다. 대신 기록된 차이·구간을 지금 `min_gain`으로 다시 판정해 기록된 판정과 다르면 멈춘다(가이드 판단할 곳 1, 승인한 지시서의 의도를 되살림). single-doc 모듈은 바꾸지 않아 과거 실험의 single-doc 평가 재현에 영향이 없다
- 감사 P10 보고(어느 single-doc 결과로 판정했는지 남지 않음): 결과에 경로와 sha256을 남긴다
