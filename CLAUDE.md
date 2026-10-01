# meet-rag

AI Hub 국회 회의록 데이터로 만드는 한국어 RAG 질의응답 시스템. 데이터 명세는 `docs/data.md`에 있다.

## 명령

- 환경: `uv sync --extra cpu` (GPU 환경은 `--extra cu126`)
- 테스트: `uv run pytest -q`
- 린트: `uv run ruff check .`
- 데이터 적재: `uv run python -m rag.ingest` (라벨 zip → `data/processed/` 코퍼스·질의, 약 10초)
- 평가 분할: `uv run python -m rag.splits` (→ `data/splits/queries.csv`, `dev_small_docs.txt`, 약 7초. 해시는 DECISIONS D-02)
- 채점: `uv run python -m rag.eval.score --run <순위.csv> --layer dev-small|dev-full [--out <결과.json>]` (순위 파일 열 `qid`, `rank`, `doc_id`)
- 판정: `uv run python -m rag.eval.compare --base <기준.csv> --cand <후보.csv> [--out <결과.json>]` (dev-full 고정, 회의 단위 paired bootstrap)
- 파이프라인 명령(데이터 적재, 분할, 인덱스, 검색, 평가, 생성)은 해당 SLICE가 끝날 때 여기에 추가한다. 빠른 확인은 dev-small로 한다

한글 출력이 깨지면 `PYTHONUTF8=1`로 실행한다. 파일은 `encoding="utf-8"`로 연다.

## 금지

- `src/rag/eval/`(S3 완료 후), `configs/eval/`, `data/splits/`(S2 완료 후)를 수정하지 않는다. 바꿔야 하면 사용자 승인 후 DECISIONS.md에 기록한다
- test 분할의 질의를 읽거나 test 점수를 계산하지 않는다. 검색 단계 종료 시 사용자 지시로 1회만 실행한다
- `docs/SPEC.md`의 평가 프로토콜은 사용자 승인 없이 바꾸지 않는다
- 파라미터를 코드에 직접 쓰지 않는다. `configs/`로만 바꾸고, 실험 설정은 `configs/exp/expNNN.yaml`에 둔다
- 평가 질의(`summary_q`)를 Google AI Studio·Gemini 무료 쿼터로 보내지 않는다
- 외부 GPU(Colab) 실행과 유료 API(OpenRouter) 호출은 예상 시간·비용을 보고하고 사용자 승인 후에만 한다. dev-small은 노트북에서 자유롭게 실행한다
- `data/`와 `.env`는 어떤 형태로도 커밋하지 않는다 (AI Hub 재배포 제한)
- `owner/`는 사용자가 의도를 전달하는 메모다. 읽고 의도를 파악하되 어떤 문서·코드에서도 참조하지 않고, 사용자 요청 없이 수정하지 않는다

## 문서

- 성공 기준·평가 프로토콜: `docs/SPEC.md`
- 베이스라인 조각·실험 백로그: `docs/PLAN.md`
- 조각 지시서: `docs/slices/NN-이름.md`
- 실험 지시서: `docs/experiments/EXP-NNN.md` (config는 `configs/exp/expNNN.yaml`)
- 실험 결과 요약: `docs/EXPERIMENTS.md`
- 채택 설정·방향 결정: `docs/DECISIONS.md`
- 현재 상태: `docs/STATUS.md`
- 브랜치·커밋·PR, 노트북 규약: `.claude/rules/`

## 세션 마무리

작업 PR을 올리기 전에 작업 브랜치에서 한다.

1. 끝난 실행이 있으면 평가하고 EXP 문서의 결과·결론을 채운다
2. 판정한 실험을 EXPERIMENTS.md에 한 줄 추가하고, 채택이면 DECISIONS.md를 갱신한다
3. PLAN.md 백로그 상태를 갱신하고 우선순위를 다시 정한다

핸드오프는 사용자가 요청할 때 한다.

4. STATUS.md를 덮어쓴다 (한 화면 이내). "다음 행동" 항목 앞에 `meet-rag` 스킬의 흐름을 `[A]`·`[B]`·`[C]`·`[D]`로 적는다. 실행 중인 Colab 작업이 있으면 위치와 예상 종료 시각을 적는다
5. `.claude/rules/git.md`의 핸드오프 절차로 커밋한다

## 하네스: meet-rag

**목표:** SLICE 구현과 EXP 판정에서 검증·감사·판정을 작성 맥락과 분리해 평가 오염을 막는다.

**호출 조건:** SLICE 구현, EXP 실행·판정, G 항목(사람 검수 게이트)의 표본 추출·집계·결정 기록, Colab GPU 작업(전체 코퍼스 임베딩·인덱스 구축), PR 준비, 세션 마무리, STATUS "다음 행동" 진행을 요청받으면 `meet-rag` 스킬을 사용한다. 같은 세션에서 다음 조각·게이트·실험으로 넘어갈 때도 스킬의 0단계부터 다시 한다. 단순 질문에는 직접 답해도 된다.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
| --- | --- | --- | --- |
| 2026-09-29 | Harness v2로 처음 구성 | 전체 | - |
| 2026-10-01 | 0단계 재시작 규정, A1 지시서 별도 커밋·확인 전 멈춤, D 흐름(사람 검수 게이트) 추가, 트리거·호출 조건 확장, STATUS 흐름 표기 | skills/meet-rag, agents/protocol-auditor, CLAUDE.md | S1 뒤 같은 세션의 S2·G1에서 스킬이 다시 쓰이지 않아 지시서 확인이 빠지고 G 항목은 대응 흐름이 없었음 |
| 2026-10-01 | colab-operator 스킬 추가, 오케스트레이터 E절(GPU 작업: 승인 → 지정 GPU 할당, 실패 시 T4 → 실행·기록 → 정리) 추가, slice-verifier·protocol-guard에 Colab 산출물 기준 추가 | skills/colab-operator, skills/meet-rag, agents/slice-verifier, skills/protocol-guard, CLAUDE.md | KURE-v1 등 임베딩을 직접 해야 해 GPU 작업을 Colab CLI로 하기로 함 |
| 2026-10-01 | E절 비용·재할당 규칙(비용 변동으로 멈추지 않음, 예상 밖 재할당은 보고 후 사용자 결정) 명시, Colab 실행 기록 위치 `outputs/notebooks/`, P5 소량 질의 허용 | skills/meet-rag, skills/protocol-guard | PR #11 사용자 코멘트 |
| 2026-10-01 | `outputs/`를 진행 중 커밋 금지(완료 후 공개)로 정하고 `.gitignore`의 `output/`을 `outputs/`로 교체 | skills/meet-rag, skills/protocol-guard, .gitignore | PR #11 사용자 결정 |
