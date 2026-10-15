# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-014 설정(D-32). EXP-011(snowflake-ko hybrid + 조건 목록 + 최다 일치 필터 + 법률명 조건 + dense 256 청크)에서 RRF k 60 → 20. dev-full Recall@5 0.9413, Recall@1 0.8372, multi-doc Recall@5 0.9541. 실행 `rag.search +exp=exp014`, 생성 `rag.generate +exp=exp014`
- 이번 세션
  - 하네스 개선 PR #86 병합(ADR-0042): B2 착수 지시 전 구현·dev-small 금지, D-31에 맞춘 P6, `colab_job.py fetch` 다운로드 중 커널 깨우기·무압축 tar·junction·`--exclude`, wrap_up 직후 PostToolUse 훅, PR #78·#79·#83 코멘트 규칙, LangSmith 규약을 구현 원칙으로(메모리 삭제)
  - PR #84 코멘트(B안을 H16 변형으로 실험) 확인 → H16 다시 열고 EXP-016 초안(`exp/exp016-score-fusion-nocond`, 이 STATUS 포함)
- 진행 중 EXP: 016 점수 기반 결합에서 조건 목록 제외(H16 B안, 두 번째 변형). 초안·config 커밋, 결정 사항 1은 (b) 확정. 구현 전

## 실행 중 작업
- 없음(Colab 세션 없음)

## 이번 세션 결정
- B2 강화 유지: 착수 지시(명시적인 시작 지시) 전에는 구현·dev-small도 하지 않는다(사용자 2026-10-15)
- wrap_up 뒤 보고 반복은 같은 날 Claude Code 업데이트 뒤 생긴 문제일 수 있다(사용자). 업데이트로 사라지면 훅을 빼고 확인한다(ADR-0042 삭제 조건)
- EXP-016 결정 사항 1: (b) 결합 목록에 없는 최다 일치 문서는 결합 목록 뒤에 붙여 필터가 올린다(사용자 2026-10-15)

## 다음 행동
1. [B] EXP-016 이어 가기(`exp/exp016-score-fusion-nocond`). 새 세션은 원래 폴더에서 main을 맞춘 뒤 이 브랜치로 switch한다(junction 없이 원래 폴더의 `data/`를 쓴다). 순서: 결정 사항 2(판정 기준: SPEC 그대로 vs 메타데이터 가설 판정 적용) 확인 → 착수 지시 받기(B2, 아직 없음) → 구현(`rag.retrieve`에서 `conditions.fuse: false`면 조건 목록을 결합에 넣지 않고 결합 목록 밖 최다 일치 문서를 뒤에 붙임, 단위 시험, EXP-014·015 dev-small 재실행으로 기존 순위 파일 불변 확인) → dev-small 노트북 27_01 → dev-full·multi-doc → 판정. 로컬 CPU, 비용 없음. single-doc 판정은 EXP-015와 거의 같게 나올 것으로 예상(조건 목록이 생기는 summary_q 0.1% 안팎)
2. [B] H8 사전 확인: 판단 뒤 청크를 보고 재작성하는 방식의 판단기 정확도와 구제율(EXP-013은 10/131)을 dev-small에서 잰다. OpenRouter 소액, 실행 전 보고
3. [B] H5 dense 접두 예상 효과 추정: Colab 재임베딩 전에 재임베딩 없이 효과를 가늠할 방법을 찾는다(EXP-002 BM25 접두는 multi-doc +15.32%p, single-doc −2.62%p)
4. [C] 정리: `_workspace/00_main_harness-pending.md`의 [대기] 5개를 "반영 ADR-0042"로 바꾼다(worktree 세션이라 못 바꿈). 병합된 로컬 브랜치 `chore/harness-pending-1015` 삭제는 main 맞추기에서. 이 세션의 worktree `.claude/worktrees/status-harness-improvement-c099f1`은 앱이 정리하거나 사용자가 지운다

## 사용자 확인 필요
- EXP-016 결정 사항 2(판정 기준)와 착수 지시
- 캐시 정리 여부: `uv cache prune`, KURE-Reranker-nano HF 캐시
- 원격 브랜치 정리(사용자): `chore/harness-setup`, `docs/review-2026-10-01`
