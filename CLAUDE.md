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
- 인덱스: `uv run python -m rag.index index.scope=dev-small|full [chunking.chunk_tokens=N chunking.overlap_tokens=M] [embedding.device=cuda embedding.dtype=float16]` (→ `data/index/`, 조각 단위 재개. 전체는 Colab L4 약 21분)
- dev-small 검색·청크 크기 비교: `uv run python -m rag.search [chunking.…]`, `uv run python -m rag.chunk_sweep` (결과 DECISIONS D-04)
- dev-full 검색: `uv run python -m rag.search index.scope=full` (→ `data/runs/{인덱스}-dev-full.csv`, 로컬 약 20초). 질의 임베딩 캐시가 없으면 `search.mode=export-queries`로 dev 질의를 내보내 Colab에서 `search.mode=embed-queries embedding.device=cuda`로 만든다(D-07, slices/05-retrieve.md)
- 생성: `uv run python -m rag.generate ask.qid=<dev qid>` 또는 `"ask.query='질문'"` (`[prompt=vN generator.stream=true]`, → `data/runs/generate/`와 LangSmith. 한도 RPM 30·TPM 16K, 호출당 약 3K 토큰. 5xx는 서버 상태부터 확인)
- multi-doc 묶음: `uv run python -m rag.multidoc.pools` (→ `data/multidoc/pools.jsonl`, 약 20초. 유형·값은 D-13)
- multi-doc 생성 준비: `uv run python -m rag.multidoc.prepare [multidoc.gen.n_per_type=N]` (→ `data/multidoc/gen_in`·`docs`, 있는 후보 집합은 건너뜀). 생성은 `multidoc-writer` 에이전트(meet-rag 스킬)
- multi-doc 검사: `uv run python -m rag.multidoc.check --prepare [multidoc.gen.n_per_type=N]`(→ `data/multidoc/check_in/`) → `multidoc-checker` 에이전트(meet-rag 스킬, → `check_out/`) → `uv run python -m rag.multidoc.check [...]`(판정 → `data/multidoc/queries.jsonl`). `--dry-run`은 생성·검사 준비·검사·판정 대기 수와 Jev 호출 수를 출력하고 호출하지 않는다. 진행 상태는 파일 존재로 정해져 중단 뒤 같은 명령으로 이어 간다. 원문에 그대로 없는 인용의 Jev 판정은 OpenRouter 유료(호출당 약 $0.00003)라 실행 전 호출 수 보고·승인. 판정 규칙은 D-14
- 파이프라인 명령(데이터 적재, 분할, 인덱스, 검색, 평가, 생성)은 해당 SLICE가 끝날 때 여기에 추가한다. 빠른 확인은 dev-small로 한다

한글 출력이 깨지면 `PYTHONUTF8=1`로 실행한다. 파일은 `encoding="utf-8"`로 연다.

## 금지

- `src/rag/eval/`(S3 완료 후), `configs/eval/`, `data/splits/`(S2 완료 후)를 수정하지 않는다. 바꿔야 하면 사용자 승인 후 DECISIONS.md에 기록한다
- test 분할의 질의를 읽거나 test 점수를 계산하지 않는다. 검색 단계 종료 시 사용자 지시로 1회만 실행한다
- `docs/SPEC.md`의 평가 프로토콜은 사용자 승인 없이 바꾸지 않는다
- 파라미터를 코드에 직접 쓰지 않는다. `configs/`로만 바꾸고, 실험 설정은 `configs/exp/expNNN.yaml`에 둔다
- 평가 질의(`summary_q`)는 dev 분할만 Google AI Studio 무료 쿼터로 보낸다(`test`는 검색 단계 종료 시 사용자 지시 1회 실행에서만). 질의 전체처럼 많이 보내는 실행은 호출 수·소요 시간(RPD·TPM 한도)을 보고하고 사용자 승인 후에 한다. 노트북·로그에 질의 원문을 대량으로 남기지 않는다(D-10)
- 외부 GPU(Colab) 실행과 유료 API(OpenRouter) 호출은 예상 시간·비용을 보고하고 사용자 승인 후에만 한다. dev-small은 Jupyter 노트북(`notebooks/`)에서 자유롭게 실행하되, GPU가 필요한 dev-small 임베딩도 Colab 승인 대상이다
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

4. STATUS.md를 덮어쓴다 (한 화면 이내). "다음 행동" 항목 앞에 `meet-rag` 스킬의 흐름을 `[A]`·`[B]`·`[C]`·`[D]`·`[F]`로 적는다. 실행 중인 Colab 작업이 있으면 위치와 예상 종료 시각을 적는다
5. `.claude/rules/git.md`의 핸드오프 절차로 커밋한다

## 하네스: meet-rag

**목표:** SLICE 구현과 EXP 판정에서 검증·감사·판정을 작성 맥락과 분리해 평가 오염을 막는다.

**호출 조건:** SLICE 구현, EXP 실행·판정, G 항목(사람 검수 게이트)의 표본 추출·집계·결정 기록, Colab GPU 작업(전체 코퍼스 임베딩·인덱스 구축), PR 준비, 세션 마무리, STATUS "다음 행동" 진행을 요청받으면 `meet-rag` 스킬을 사용한다. 같은 세션에서 다음 조각·게이트·실험으로 넘어갈 때도 스킬의 0단계부터 다시 한다. 하네스 수정과 하네스 피드백 반영은 스킬의 F 흐름으로 하고, 첫 단계에서 `harness:evolve`를 불러온다. 단순 질문에는 직접 답해도 된다.

**변경 기록:** 하네스(`.claude/`의 스킬·에이전트·규약)를 바꾸면 `docs/harness/adr/`에 ADR(상태·맥락·결정·결과·삭제 조건)을 하나 추가하고 목록(`docs/harness/adr/README.md`)을 갱신한다.
