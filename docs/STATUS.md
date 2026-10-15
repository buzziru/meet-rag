# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-014 설정(D-32). EXP-011(snowflake-ko hybrid + 조건 목록 + 최다 일치 필터 + 법률명 조건 + dense 256 청크)에서 RRF k 60 → 20. dev-full Recall@5 0.9413, Recall@1 0.8372, multi-doc Recall@5 0.9541. 실행 `rag.search +exp=exp014`, 생성 `rag.generate +exp=exp014`
- 이번 세션: EXP-013 질의 재작성(H8) 기각(−0.50%p), 기준 오차 분석(24_01, 실패 200개 중 결합 손실 81), EXP-014 RRF k 20(H16) 보류 → 예외 채택(D-32), EXP-015 점수 기반 결합 보류(+0.43%p, multi-doc 하락) → 예외 채택 안 함, H16 닫음. 보류 예외 채택 기준 D-33(multi-doc 하락을 무겁게 봄). H15(BM25 256 청크)·H3 닫음
- 병합 대기 PR: H3 닫기·PLAN 다음 순서(`docs/h3-close`, 이 STATUS 포함)

## 실행 중 작업
- 없음(Colab 세션 없음, 노트북 커널 종료)

## 이번 세션 결정
- 재작성기 등 API로 LLM을 부르는 코드는 LangSmith로 추적한다(메모리 `llm-calls-langsmith`, Jev 쪽은 PR #79). 하네스 규약으로는 아직 옮기지 않았다
- H8 다음 변형 구상(사용자): 1차 검색 결과로 답변 가능 여부를 판단한 뒤 청크를 보고 재작성. cross-encoder 판단 신호와 LangGraph는 쓰지 않는다
- EXP-012 문장 경계 인덱스(약 1.6GB) 삭제(보존 원칙의 예외, 순위 파일은 남김). `meet-rag-exp012` worktree 정리

## 다음 행동 (사용자 지정 순서)
1. [F] 하네스 개선: `_workspace/00_main_harness-pending.md`의 [대기] 5개(B2 착수 승인 규칙, D-31 정렬, colab fetch 세션 유지·세부 개선, wrap_up 뒤 보고 반복을 막는 Stop 훅)와 LangSmith 추적 규약을 메모리에서 하네스로 옮기는 일. `harness:evolve`부터
2. [C] PR 코멘트 반영: 사용자가 남긴 PR 코멘트를 확인해 반영(대상 PR은 새 세션에서 확인)
3. [B] H8 사전 확인: 판단 뒤 청크를 보고 재작성하는 방식의 판단기 정확도(1차 상위 5개로 답할 수 있는지 vs 실제 정답 포함)와 구제율(기준이 놓친 질의를 살리는 비율, EXP-013은 10/131)을 dev-small에서 잰다. OpenRouter 소액, 실행 전 보고
4. [B] H5 dense 접두 예상 효과 추정: Colab 재임베딩 전에 재임베딩 없이 효과를 가늠할 방법을 찾는다(EXP-002 BM25 접두는 multi-doc +15.32%p, single-doc −2.62%p. 지금 multi-doc Recall@5 0.954, Complete@5 0.912)

## 사용자 확인 필요
- 캐시 정리 여부: `uv cache prune`, KURE-Reranker-nano HF 캐시
- 원격 브랜치 정리(사용자): `chore/harness-setup`, `docs/review-2026-10-01`
