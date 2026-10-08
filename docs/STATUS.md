# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c·G3 완료. 동결 세트 `data/multidoc/queries_g3.jsonl` 600건(conf 233, law 152, questioner 215, SHA-256 `0c385a2b…8d1a874436`, D-15). PR #41·#42 병합
- 하네스 대기 24\~27 반영(PR #43, ADR-0024\~0026): 작업 큐 스크립트 `worker_queue.py`, 작업자 끝까지 읽기, 정의는 반복 작업자만, 리뷰 가이드는 최종 diff로 받음, 하네스 테스트는 스크립트 옆(병합 조건 밖)
- `data/multidoc/pilot_v1`\~`v4` 삭제(`pilot_v4_luna`는 노트북 08_03 입력이라 유지)

## 실행 중 작업
- 없음

## 이번 세션 결정
- S9 지표 k는 5, 10으로 보고한다. 기준선 결과 보고와 함께 k 수정이 필요한지 의견을 낸다(사용자, 2026-10-08)
- multi-doc 작업(S9)이 끝나면 백로그 EXP로 넘어간다(사용자)

## 다음 행동
1. [A] S9 다중 정답 채점과 기준선 측정(PLAN S9, 입력 `queries_g3.jsonl` D-15). 지시서부터 쓴다. 지표 Recall@k·Complete@k·Hit@k(k=5, 10), 유형별, 묶음 단위 paired bootstrap 구간(판정 라벨 없음). `src/rag/eval/`은 고치지 않고 `bootstrap.py`만 가져다 쓴다. 기준선 점수와 k 수정 의견을 보고한다. `law`는 한 번만 재판정한 질의가 있다는 D-15 단서와 함께 본다
2. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S9 뒤 single-doc 판정과 multi-doc 관찰을 함께 기록
3. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 다음 추가 생성 때 선행 작업
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에 `wrap_lines` 적용. 작업자는 끝까지 읽지 못한 원문을 건너뛴다(ADR-0024)
- 안건 목록 중복 제거(2026-10-07 사용자 결정, PR #43 코멘트)
- law 생성 지시에 다룰 법안·주제를 질의에 명시하는 규칙(G3에서 law 범위 모호·내용 불일치가 집중됨, D-15)

## 사용자 확인 필요
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 결정(사용자)
