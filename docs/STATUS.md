# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). 검색: KURE-v1, 512/64 청크, numpy 전수 검색(D-04, D-08). dev-full Recall@5 0.8584 [0.8428, 0.8741], 목표 0.90(D-09)
- 생성: Gemma 4 31B(`models/gemma-4-31b-it`), 근거 5개, 프롬프트 `configs/prompt/v1.yaml`, LangSmith 추적, 레시피 기록(D-11). 답변 품질 평가는 기준을 정한 뒤로 미룸
- 평가 질의 규칙: dev 질의는 Colab 임베딩·무료 쿼터 LLM 전송 가능, `test`는 검색 단계 종료 시 1회만(D-07, D-10)
- 하네스: 변경 기록은 `docs/harness/adr/`(ADR-0001\~0015). 하네스 수정은 F 흐름(`harness:evolve` 호출로 시작). 외부 API 5xx는 https://aistudio.google.com/status 부터 확인. 노트북은 `scripts/nb_kernel.py`로 실패 셀부터 이어 실행
- 하네스 PR(`chore/harness-adr-status-nbresume`)은 사용자 검토 대기

## 실행 중 작업
- 없음 (`colab sessions` 활성 세션 없음 확인)

## 판정 대기
- 없음. `docs/EXPERIMENTS.md`는 첫 EXP 판정 때 만든다

## 미완 상태
- 로컬 `data/`: full 512/64 인덱스, 질의 임베딩 `data/index/kure-v1/queries-{dev-small,full}.npz`, dev 질의 파일 `data/processed/queries_summary_q.dev.jsonl`, 기준 순위 `data/runs/kure-v1-fixed-512-64-dev-full.csv`(SHA-256 `f1568843…bbe2`)·채점 json, 생성 기록 `data/runs/generate/` 5건
- Google AI Studio 프로젝트는 무료 등급(결제 등록 시 Tier 1로 바뀌어 402가 남. 2026-10-02 되돌림)

## 시도했다 버린 것
- Gemma 4 31B 사고 과정 끄기: `reasoning_effort`·`thinking_budget` 모두 400. 대신 `thought`/`answer`로 나눠 기록
- 노트북 전체 재실행으로 API 오류 대응: 서버 장애 중 호출만 늘었음 → ADR-0012·0013

## 다음 행동
1. [C] 하네스 PR 확인·병합 후 `main` pull, 로컬 브랜치 삭제
2. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). 재임베딩 없음, BM25 인덱스는 로컬 CPU. 기준 순위는 위 dev-full 파일. 판정은 SPEC 규칙(회의 단위 paired bootstrap, +1.0%p)
3. [B] 다음 후보: H2 reranker(H1 후보 위에서) → H7 문서 집계. 전체 순서는 PLAN 백로그
4. 비채택 3회 연속이면 SPEC 중단 기준. 검색 단계 종료 시 `test` 1회와 G2 보조 분석

## 사용자 확인 필요
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
