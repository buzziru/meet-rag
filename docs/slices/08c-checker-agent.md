# S8c 검사를 Sonnet 에이전트로

S8 검사 단계를 OpenRouter `openai/gpt-6-luna` 스크립트 호출에서 Claude Code Sonnet 검사 에이전트(`multidoc-checker`)로 바꾼다(2026-10-07 사용자 결정, PR #31 코멘트). 코드 판정(규칙 1\~5, Jev 인용 의미 판정)은 그대로 `rag.multidoc.check`가 한다.

## 배경

- 사용자는 생성·검사가 같은 계열일 때의 self-evaluation bias보다 검사 성능을 택했다. 파일럿에서 luna·Sonnet 판정이 갈린 5건을 사람이 검수한 결과 Sonnet 3건, luna 2건이 맞았다(`data/multidoc/review/g3_pilot_split5_review.md`). luna 오류는 무관한 근거 연결과 요소 분해였고, Sonnet 오류는 원문에 없는 인과와 문서 누락을 받아들인 쪽이었다
- `typesafe/jev-1.13`은 선택형 출력이라 근거 인용을 낼 수 없어 검사 모델 후보에서 뺐다(인용 의미 판정에는 S8b에서 쓴다)
- bias를 줄이는 장치는 유지한다: 검사 입력에 생성 쪽 시작 묶음·기대 답·근거를 넣지 않고, 검사 에이전트는 훅으로 생성 출력을 읽지 못하며, 통과 여부는 코드가 정한다
- 사실 뒷받침 판정(S8b 실험)은 검사 출력이 사실을 합쳐 써서 채택하지 않았다. 검사 지시에 "사실 하나에 한 가지 내용"을 넣고 다시 실험한다

## 흐름

```
check --prepare ─► check_in/{pool_id}.md   검사 지시(check_v3) + 질의 + 번호 붙인 후보 집합 원문·질의자
                         │                 (생성 출력이 ok이고 검사 기록·check_in이 없는 후보 집합만)
메인: multidoc-checker를 동시 3개, 작업 하나에 후보 집합 2개, 끝나면 새 에이전트로 칸을 채운다
                         ▼
                 check_out/{pool_id}.json  {answerable, elements[{fact, support[{doc, quote}]}]}
                         │
check ─► 스키마 검사 ─► 검사 기록 check/{pool_id}.json ─► Jev 인용 의미 판정 ─► 코드 판정 ─► queries.jsonl
```

## 만드는 것

### 1. 검사 지시 `configs/multidoc/prompt/check_v3.yaml`

`check_v2`의 할 일 1\~4를 유지하고 다음을 더한다.

- 사실 하나에는 한 가지 내용만 쓴다. 질의와 답변, 여러 인물의 발언, 여러 수치를 한 사실에 합치지 않는다
- 출력은 파일 하나에 위 JSON 형식으로 쓴다(`doc`은 입력의 문서 번호)

### 2. `rag.multidoc.check`

- `--prepare`: 선택한 후보 집합 중 생성 출력이 `ok`이고 검사 기록과 `check_in` 파일이 없는 것의 검사 입력을 `paths.multidoc_check_in`에 쓴다. 생성 `skip`은 검사 없이 기록(`gen_skip`)을 만든다
- 기본 실행: `paths.multidoc_check_out`에 출력이 있고 검사 기록이 없는 후보 집합을 스키마로 검사해 검사 기록을 만들고(`recipe`에 검사 지시 버전·SHA-256, 검사 주체 `multidoc-checker`), Jev 판정과 코드 판정을 한다. 스키마에 맞지 않는 출력은 기록을 만들지 않고 `check_out/rejected/`로 옮겨 다시 검사 대기에 둔다. 그다음 기존처럼 검사 기록 전체를 다시 판정해 `queries.jsonl`을 쓴다
- `--dry-run`: 준비할 수, 검사 대기 수(`check_in` 있고 `check_out` 없음), 판정 대기 수, Jev 호출 수(기존 기록분)를 출력한다
- luna 호출 경로(OpenAI 클라이언트, `call`, `SCHEMA`의 structured outputs 용도)와 config의 `base_url`·`model`·`provider`·`seed`·`reasoning_effort`·`max_tokens`를 지운다. `api_key_env`는 Jev가 쓴다
- 기존 검사 기록(luna)은 데이터로만 남는다

### 3. 중단과 이어 하기

본 생성 검사는 동시 3개로 약 10시간 걸릴 것으로 본다(파일럿 비교에서 후보 집합 1개에 약 2.5분, 약 740개). 생성·검사 에이전트는 백그라운드로 돌고, 사용자가 메인에 중단을 지시하면 메인이 멈추며, 새 세션에서 진행 상황을 확인해 이어 간다(사용자 요구). 이를 위해 진행 상태를 세션 메모리가 아니라 파일로 둔다.

- 남은 작업은 매번 파일 상태에서 계산한다. 생성 대기(`gen_in` 있고 `gen_out` 없음), 검사 준비(`check_in` 없음), 검사 대기(`check_out` 없음), 판정 대기(검사 기록 없음)가 각각 파일 존재로 정해지고, 있는 파일은 다시 만들지 않는다
- `--dry-run`이 위 네 가지 수와 Jev 호출 수를 출력한다. 새 세션은 이 출력으로 큐를 다시 만든다
- 중단으로 멈춘 에이전트가 쓰지 못한 후보 집합은 출력 파일이 없어 대기로 남는다. 쓰다 만 검사 출력은 스키마 검사에서 걸러 다시 검사 대기에 둔다
- 메인의 중단·재개 절차(새 작업을 띄우지 않음, 실행 중 에이전트 정지, 진행 기록·STATUS에 남은 수와 재개 명령 기록, 새 세션 0단계에서 확인)는 오케스트레이터 변경이라 `chore/` 브랜치에서 정한다
- 메인은 작업 배정과 이력을 `_workspace/s08_queue.jsonl`에 작업마다 한 줄(작업 번호, 단계, 후보 집합, 상태, 시작·종료 시각)로 남긴다. 사람이 진행을 보고 멈춘 작업을 찾는 기록이고, 남은 작업의 기준은 파일 상태다. 둘이 다르면 파일 상태를 따른다(사용자 결정 2026-10-07). 이 절차도 `chore/`에서 정한다

### 4. 파일럿 재검사 (새 세션)

에이전트 정의는 새 세션부터 적용되므로 하네스 PR(`chore/`) 병합 뒤 새 세션에서 한다.

- 기존 검사 기록(luna) 40개를 `data/multidoc/pilot_v4_luna/check/`로 옮기고, 생성 출력 `ok` 31개를 새 경로로 검사한다(16작업, 약 30분)
- 노트북 `notebooks/08_03_검사모델.ipynb`: G3 갈린 5건 사람 검수 집계, 새 Sonnet 검사와 luna·사람 판정 비교, 수율, 사실 뒷받침 판정 재실험(Jev, 검사 쪽 근거 30쌍과 엇갈린 30쌍, 약 60호출·$0.01 미만, 실행 전 승인)
- 노트북을 사용자에게 보인 뒤 D-14(검사 모델, 검사 지시 버전, 뒷받침 판정 채택 여부)를 갱신한다

## 노트북과 결정의 순서

검사 모델 결정은 사용자가 이미 내렸다. D-14 기록은 4의 노트북 뒤에 한다. 뒷받침 판정 채택은 노트북을 보고 사용자가 정한다.

## 완료 기준

| # | 명령 | 기대 |
|---|---|---|
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과(준비·스키마 검사·거부 이동·이어 하기를 합성 입력으로 시험) |
| 2 | `uv run python -m rag.multidoc.check --prepare` 두 번 | 두 번째는 새로 쓰는 파일 0 |
| 3 | `uv run python -m rag.multidoc.check --dry-run` | 준비·검사 대기·판정 대기·Jev 호출 수 출력, 외부 호출 0 |
| 4 | 파일럿 재검사 뒤 `check` 두 번 | 두 번째는 새 기록·Jev 호출 0, `queries.jsonl` SHA-256 같음 |
| 5 | 노트북 08_03 | 5건 집계, 모델 비교, 뒷받침 재실험 출력 |
| 6 | 문서 | D-14, S8 지시서 역할 표·규칙, `CLAUDE.md` 명령, 이 문서 실행 기록 |

## 수정 허용 파일

- `src/rag/multidoc/check.py`, `tests/test_multidoc_check.py`
- `configs/config.yaml`(`multidoc.check`, `paths.multidoc_check_in`·`multidoc_check_out`), `configs/multidoc/prompt/check_v3.yaml`
- `notebooks/08_03_검사모델.ipynb`
- `docs/DECISIONS.md` D-14, `docs/slices/08-multidoc-queries.md`, 이 문서, `CLAUDE.md` "명령" 절

## 범위 밖

- 검사 에이전트 정의, 읽기·쓰기 훅, 오케스트레이터 절차, ADR: `chore/` 브랜치(하네스 변경)
- G3 본 생성
- 생성 에이전트 작업 단위(10개 그대로, 사용자 결정)

## 실행 기록

(실행 뒤 채움)
