# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c 완료(D-13, D-14). G3 완료(2026-10-08, PR #41 병합): 동결 세트 `data/multidoc/queries_g3.jsonl` 600건(conf 233, law 152, questioner 215, SHA-256 `0c385a2b…8d1a874436`). 근거 `notebooks/08_04_G3검수.ipynb`
- `docs/g3-freeze` PR 리뷰 대기: D-15(G3 검수·동결), PLAN G3 체크·S9 입력, `08c-checker-agent.md` 검사 입력 줄 나눔 설명
- 진행 기록 `_workspace/g3_main_progress.md`, 재판정 큐 `_workspace/g3j_queue.jsonl`

## 실행 중 작업
- 없음

## 이번 세션 결정
- G3 표본은 동결 세트에서만 무작위 50건, law 회의별 쟁점형은 사용자 재판정, law 190건은 서브에이전트 재판정(`scope_v2`). 한 번이라도 통과가 아니면 제외(38건). D-14 규칙 5 유지

## 다음 행동
1. [D] `docs/g3-freeze` PR 리뷰·병합
2. [D] `pilot_v1`\~`v4` 삭제(사용자 결정, 아직 안 함)
3. [F] 하네스 대기 24\~26 반영(`_workspace/00_main_harness-pending.md`, chore/, harness:evolve)
4. [A] S9 다중 정답 채점과 기준선 측정(입력 `queries_g3.jsonl`, D-15). 지표 k 값은 S9 전에 사용자가 다시 정한다(D-14)
5. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF)
6. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 다음 추가 생성 때 개선 후보
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에도 `wrap_lines` 적용. 생성 작업자도 긴 원문 일부만 읽음(gen 52 law-0166, gen 54 law-0180, gen 94 questioner-0332)
- 안건 중복 제거(2026-10-07 사용자 결정)
- law 생성 지시에 다룰 법안·주제를 질의에 명시하는 규칙(G3에서 law 범위 모호·내용 불일치가 집중됨, D-15)

## 사용자 확인 필요
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 결정(사용자)
