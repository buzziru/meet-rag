# S3 평가 모듈

순위 파일을 SPEC "지표"·"판정" 절대로 채점하고, 두 순위 파일을 회의 단위 paired bootstrap으로 비교한다. 완료 후 `src/rag/eval/`은 수정 금지 대상이다. 검색은 하지 않는다(S5).

## 만드는 것

- `src/rag/eval/metrics.py`: 순위 파일 읽기·검증, 질의별 정답 순위, Recall@k·MRR@k, 회의구분·`qna_type`별 표
- `src/rag/eval/bootstrap.py`: 회의 단위 paired bootstrap과 채택·기각·보류 판정
- `src/rag/eval/score.py`: 순위 파일 하나를 채점하는 명령
- `src/rag/eval/compare.py`: 기준·후보 순위 파일을 비교해 판정하는 명령

## 입력

### 순위 파일

CSV, 열은 `qid`, `rank`, `doc_id`. `rank`는 1부터 시작하는 정수다.

- 같은 `qid`에서 `doc_id`가 여러 번 나오면 가장 작은 `rank`만 남기고, 남은 문서를 `rank` 순으로 1부터 다시 매긴다. 청크 단위 결과를 그대로 넣어도 SPEC "문서 순위"가 적용되게 하려는 것이다
- 다음은 오류로 멈춘다
  - 평가 층의 질의 중 순위 파일에 없는 `qid`가 있다
  - 평가 층에 속하지 않는 `qid`가 있다(dev 실행에 test `qid`가 섞인 경우 포함)
  - 중복 제거 후 서로 다른 문서가 10개 미만인 질의가 있다(SPEC "출력")
  - 같은 `qid`에서 `rank`가 중복된다

### 평가 층

`--layer`로 고른다. 정답과 층 정의는 S1·S2 산출물에서 읽는다.

| `--layer` | 질의 | 정답 메타데이터 |
| --- | --- | --- |
| `dev-small` | dev 질의 중 정답 `doc_id`가 `paths.dev_small_docs`에 있는 것 | 정답 `doc_id`, `qna_type`(`paths.queries`), `meeting_name`·`conference_number`(`paths.corpus`) |
| `dev-full` | `paths.splits`에서 `split == dev`인 질의 전체 | 같음 |
| `test` | `split == test`인 질의 전체 | 같음 |

`test`는 `--allow-test`를 함께 줘야 실행된다. 검색 단계 종료 시 사용자 지시로 1회만 쓴다(CLAUDE.md 금지 절). 질의 텍스트(`query`)는 읽지 않는다.

## 규칙

### 지표

파라미터는 `configs/eval/spec_v1.yaml`에서 읽는다(`recall_ks`, `mrr_k`, `breakdowns`).

- 질의별 정답 순위 `r`(상위 목록에 없으면 없음)
- Recall@k: `r <= k`이면 1, 아니면 0. 평균을 낸다
- MRR@10: `r <= 10`이면 `1/r`, 아니면 0. 평균을 낸다
- 표: 전체 한 줄, 그 아래 `breakdowns`의 각 열 값마다 한 줄. 각 줄에 질의 수와 지표를 적는다

### 비교와 판정

`compare`는 `dev-full`에서만 실행한다. SPEC은 판정을 dev-full로만 하고, dev-small은 판정에 쓰지 않는다.

1. 두 순위 파일을 각각 위 규칙으로 검증·채점해 질의별 Recall@5 값 `b_i`, `c_i`를 얻는다
2. 질의를 `conference_number`로 묶는다. 회의 목록을 정렬한 뒤 `numpy.random.default_rng(seed)`로 회의를 복원 추출한다(회의 수만큼, `n_resamples`회)
3. 각 반복에서 뽑힌 회의들의 질의 전체(중복 추출된 회의는 그만큼 반복)로 `mean(c_i - b_i)`를 계산한다
4. 점 추정은 원 표본의 `mean(c_i - b_i)`, 구간은 반복 값의 `alpha/2`, `1 - alpha/2` 분위수다
5. 판정: 하한 > 0이고 점 추정 ≥ `min_gain`이면 채택, 상한 < 0이면 기각, 그 밖은 보류

`n_resamples`, `seed`, `alpha`, `min_gain`, 주지표는 `configs/eval/spec_v1.yaml`의 `bootstrap`·`primary`에서 읽는다.

### 출력

- `score`: 지표 표를 표준 출력에 마크다운으로 쓴다. `--out`을 주면 같은 내용을 JSON으로 저장한다
- `compare`: 두 실행의 전체 지표, 점 추정 차이, 95% 구간, 판정을 출력한다. `--out`이면 JSON으로 저장한다
- 출력에는 층 이름과 순위 파일의 SHA-256을 함께 적는다. EXP 문서에 어떤 파일을 채점했는지 남기기 위해서다

## 명령

```
uv run python -m rag.eval.score --run <순위.csv> --layer dev-small|dev-full [--out <결과.json>]
uv run python -m rag.eval.compare --base <기준.csv> --cand <후보.csv> [--out <결과.json>]
```

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q` | 통과. 테스트는 합성 입력만 쓰고 `data/`를 읽지 않는다. 아래 경우를 포함한다: 손으로 계산한 Recall@1·5·10·MRR@10과 일치, 청크 중복 `doc_id` 제거 후 재순위, 누락 `qid`·층 밖 `qid`·문서 10개 미만·`rank` 중복은 오류, 같은 순위 파일끼리 비교하면 차이 0·보류, 후보가 명백히 나으면 채택·나쁘면 기각, 같은 seed로 두 번 돌리면 구간이 같음, 재표본이 회의 단위(한 회의의 질의가 함께 뽑힘) |
| 2 | `uv run ruff check .` | 통과 |
| 3 | dev-small 오라클 순위 파일(정답을 1위, 다른 dev-small 문서 9개를 뒤에)로 `score --layer dev-small` | Recall@1·5·10·MRR@10이 모두 1.0, 회의구분·`qna_type` 줄의 질의 수 합이 전체와 같음 |
| 4 | dev-full 순위 파일 두 개를 만든다: A는 정답 1위, B는 정답 6위(나머지는 정답이 아닌 코퍼스 문서). `compare --base B --cand A` | 차이 +1.0(100%p), 채택 |
| 5 | 4에서 기준·후보를 바꿔 실행 | 차이 −1.0, 기각 |
| 6 | 4의 A끼리 비교 | 차이 0, 보류 |
| 7 | 4를 두 번 실행 | 출력 일치 |
| 8 | `score --layer test`를 `--allow-test` 없이 실행 | 오류로 멈추고 `test` 질의를 채점하지 않음 |

3~7의 순위 파일은 검증 중에 `paths.splits`·`paths.corpus`·`paths.dev_small_docs`로 만든다. 질의 텍스트는 쓰지 않고 `test` 질의는 만들지 않는다. 8은 순위 파일 없이 `--layer test`만 확인한다.

## 수정 허용 파일

- `src/rag/eval/` 아래 파일, `tests/test_eval.py`
- `CLAUDE.md` "명령" 절(채점·비교 명령 추가), `docs/PLAN.md` S3 체크, 이 문서

## 범위 밖

- `configs/eval/spec_v1.yaml` 수정(보호 경로. 값은 읽기만 한다)
- 검색·순위 파일 생성(S5), dev-small·dev-full 실제 검색 점수
- 결과 표의 파일 저장 위치 규약(EXP 흐름에서 정한다)
- 보호 경로 훅 설정(STATUS "사용자 확인 필요")
