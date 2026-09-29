# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 문서 체계 구축 완료: CLAUDE.md, SPEC, PLAN, DECISIONS, `.claude/rules/`(git, notebook)
- 베이스라인 착수 전. 다음 조각은 PLAN S1(데이터 적재)
- 원격: https://github.com/buzziru/meet-rag (public). PR #1, #3 병합 완료, #2는 닫음

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- `data/processed/`는 사용자가 삭제했다. 원본 zip(`data/Training`, `data/Validation`, `data/Sublabel`)만 있다. S1에서 코드로 재생성한다
- `docs/slices/`, `docs/experiments/`, `docs/EXPERIMENTS.md`, `configs/exp/`는 아직 없다. 첫 사용 시 만든다
- configs의 `???` 값은 해당 SLICE에서 정한다: `chunking.chunk_tokens`·`overlap_tokens`(S4), `retriever.chunk_pool`(S5), `generator.model`(S6)
- `.venv`는 `--extra cpu` 없이 만들어졌다. 필요하면 `uv sync --extra cpu`로 다시 맞춘다
- 테스트가 아직 없어 `uv run pytest -q`는 exit 5로 끝난다

## 시도했다 버린 것
- `gh repo create --public`이 auto mode 분류기에 막혔다. `.claude/settings.local.json`(gitignore 대상)에 `gh repo create`, `gh pr create`, `git push` 허용 규칙을 넣어 해결했다

## 다음 행동
- `main`에서 `feat/s01-data` 브랜치를 만들고 `docs/slices/01-data.md`를 작성한다. 범위는 라벨 zip에서 `corpus_context.jsonl`(고유 `context` 38,516건)과 `queries_summary_q.jsonl`(39,633건)을 재생성하는 것이고, 필드와 `doc_id` 규칙은 `docs/data.md` §16을 따른다

## 사용자 확인 필요
- SPEC 미결 1(`summary_q` 100건 검수)은 S2 이후, S5 평가 실행 전에 사용자가 해야 한다
- 보호 경로(`src/rag/eval/`, `configs/eval/`, `data/splits/`)를 훅으로 막을지: S2·S3 완료 시점에 결정
