# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c 완료(D-13, D-14). PR #37\~#39 병합
- G3 본 생성 판정 완료(2026-10-08): 통과 638(conf 233, law 190, questioner 215) → `data/multidoc/queries.jsonl`. Jev 누적 13건 $0.00050. 생성·검사·판정 대기 0, 보류 0
- PR #40 병합(3f2b9bc). 본 생성 범위 950개 완료, 대기·보류 0이라 `queries.jsonl` 638건이 동결 대상(SHA-256 `d2169035…8cc48061`)
- G3 검수 완료(2026-10-08): 표본 50건 불량 3(모두 law), law 회의별 쟁점형 113건 사용자 재판정 모호 20, law 190건 서브에이전트 재판정(`scope_v2`, 정답 문서 본문·질의자 포함)에서 동결분 비통과 12와 v1에서만 비통과 3. 38건을 빼 동결 세트 `data/multidoc/queries_g3.jsonl` 600건(conf 233, law 152, questioner 215, SHA-256 `0c385a2b…8d1a874436`, `rag.multidoc.freeze`). 근거 `notebooks/08_04_G3검수.ipynb`. D-14 규칙 5 유지(사용자). PR #41(`chore/g3-review`) 리뷰 대기, DECISIONS 미기록
- 진행 기록 `_workspace/s08_main_progress.md`, 큐 `_workspace/g3_queue.jsonl`(작업 404까지 done), 판정 로그 `_workspace/g3_judge_run1\~3.log`

## 실행 중 작업
- 없음

## 이번 세션 결정
- Jev 11건·2건 승인, 긴 줄 12개는 fix 뒤 재검사, questioner-0305 재검사, 이미 검사한 것 중 최대 줄 2만 자 초과 6개 재검사
- 재검사 19개는 줄을 나눈 입력으로 검사(나머지 762개는 이전 형식). 대체된 출력·기록은 `check_out/superseded/`, `check/superseded/`

## 다음 행동
1. [D] PR #41 리뷰·병합
2. [D] `docs/` 브랜치에서 DECISIONS에 G3 집계·동결 SHA-256·규칙 5 유지·재검사 19개 목록 기록, `08c-checker-agent.md` 검사 입력 설명 갱신, PLAN G3 체크. S9 전에 해야 함(SPEC 동결 조항)
3. [D] 검수 뒤 `pilot_v1`\~`v4` 삭제(사용자 결정, 아직 안 함)
4. [F] 하네스 대기 24\~26 반영(`_workspace/00_main_harness-pending.md`, chore/, harness:evolve)
5. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). G3와 병렬 가능
6. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 다음 추가 생성 때 개선 후보
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에도 `wrap_lines` 적용. 생성 작업자도 긴 원문 일부만 읽음(gen 52 law-0166, gen 54 law-0180, gen 94 questioner-0332)
- 안건 중복 제거(2026-10-07 사용자 결정)
- 작업자 지시 미준수(쟁점 일부만 요소화, 특수문자 회피로 요소 누락, 질의·답변 한 요소에 묶음)는 진행 기록 "관찰". 검수에서 확인

## 사용자 확인 필요
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 결정(사용자)
