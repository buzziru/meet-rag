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
- single-doc 결과 JSON이 dev-full 비교인지(`layer`), 판정 기준(`min_gain`)이 지금 config와 같은지는 읽을 때 본다. 다르면 멈춘다

예: EXP-008처럼 single-doc 보류, multi-doc Recall@5 +1.65%p [+0.91, +2.49], Complete@5 [+2.00, +4.83]이면 `{"verdict": "채택", "stage": "multi-doc"}`. multi-doc Recall@5 +0.8%p [+0.2, +1.4]이면 보류(D-35의 예).

### 정답 읽기 테스트 (D-8)

`load_gold`를 합성 분할·질의·코퍼스·dev-small 목록 파일로 부른다(경로는 config override). 확인하는 것:

- dev 층은 분할 `dev`의 질의만, dev-small은 그중 dev-small 문서의 질의만 담는다
- test 층은 `allow_test` 없이 멈추고, 있으면 `test` 질의만 담는다
- 모르는 층 이름은 오류
- `meeting_name`은 코퍼스에서, `conference_number`는 분할 파일에서 붙는다
- 결과는 qid 순으로 정렬된다

## 결정 사항

1. **판정 라벨을 어디서 낼지.**
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
