# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- S1 데이터 적재 병합 완료(PR #5). `uv run python -m rag.ingest`로 `data/processed/`를 재생성한다
- S2 평가 분할은 PR #6(`feat/s02-splits`), G1 표본 추출 도구는 PR #7(`chore/g1-sample`)로 올렸다. 둘 다 사용자 검토·병합 대기
- 병합 순서: #6 → #7. #7의 표본은 #6의 분할(`queries.csv` SHA-256 `091235be…`, DECISIONS D-02)에서 뽑았다. #6에서 분할이 바뀌면 `uv run python -m rag.sample_review`로 표본을 다시 뽑는다
- 두 PR 모두 slice-verifier 검증(S2)과 protocol-auditor 감사를 통과했다. 두 PR이 함께 고치는 `configs/config.yaml`은 병합 충돌이 없다(`git merge-tree`)

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- 로컬 `data/`에는 S1·S2 산출물과 G1 표본이 있다. `data/splits/`의 해시는 D-02와 같다
- G1 표본: `data/review/g1_summary_q.csv`(dev 100건, 82회의, SHA-256 `97f3674c…`). 사용자가 `verdict`·`issue`·`note` 칸을 채우는 중
- configs의 `???` 값은 해당 SLICE에서 정한다: `chunking.chunk_tokens`·`overlap_tokens`(S4), `retriever.chunk_pool`(S5), `generator.model`(S6)

## 시도했다 버린 것
- `.venv`가 `src/rag` 생성 전에 설치돼 `rag` import가 실패했다. `uv sync --extra cpu --reinstall-package meet-rag`로 해결

## 다음 행동
1. 사용자가 알려 준 병합 결과를 확인한다(`gh pr view 6`, `gh pr view 7`). 병합됐으면 `main`을 pull하고 로컬 브랜치를 지운다
2. G1 검수 결과를 집계한다: 불량 유형별 건수·비율. 필터 규칙을 둘지 사용자와 정해 DECISIONS에 기록하고 PLAN G1을 체크한다(`docs/` 브랜치)
3. 그다음 S3 평가 모듈(`docs/slices/03-eval.md`)을 시작한다. S4는 G1과 상관없이 진행할 수 있다

## 사용자 확인 필요
- 보호 경로(`src/rag/eval/`, `configs/eval/`, `data/splits/`)를 훅으로 막을지: S2·S3 완료 시점에 결정
