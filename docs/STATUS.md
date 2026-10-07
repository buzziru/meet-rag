# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c 완료(D-13, D-14). PR #37\~#39 병합
- G3 본 생성: 생성 95작업 950개 완료, 검사 완료(2026-10-08, 큐 488작업 모두 done). 판정은 Jev 승인 대기로 아직 안 돌림
- 진행 기록 `_workspace/s08_main_progress.md`, 큐 `_workspace/g3_queue.jsonl`, 작업 목록 `_workspace/g3_gen_jobs.txt`·`g3_check_jobs.txt`(검사 362번까지, 363\~393은 생성 86\~95분)

## 실행 중 작업
- 없음(큐에 running 없음)
- `check --dry-run multidoc.gen.n_per_type=350`: 생성 대기 0, 검사 대기 12(긴 줄 보류분), 판정 대기 908(검사 출력 743 + 생성 skip 165), 완료 30, 보류 0

## 판정 대기
- 판정 시 Jev 호출 11건(conf 5, law 4, questioner 2. 판정 대기분의 원문에 그대로 없는 인용을 읽기 전용 스크립트로 셈). 파일럿 157건 $0.0045 기준 $0.001 미만. 승인 전 실행하지 않음

## 미완 상태
- 파일럿 결과 `data/multidoc/pilot_v4/`, `pilot_v4_luna/`. 본 생성 검사가 끝나면 `pilot_v1`\~`v4` 삭제(사용자 결정, 아직 안 함)
- 작업자 지시 미준수·위험 사례(쟁점 일부만 요소화, 특수문자 회피로 요소 누락, 긴 원문·검사 입력 일부만 읽음, 질의·답변 한 요소에 묶음, questioner 메타데이터 화자 불일치)는 진행 기록 "관찰"에 적음. 판정·검수에서 확인
- 하네스 대기 24(큐 기록·배정 보조 스크립트, 이번 세션 배정 실수 2회), 25(작업자 Read 상한 대응)를 `_workspace/00_main_harness-pending.md`에 추가

## 다음 행동
1. [D] 사용자 결정 3건(아래 "사용자 확인 필요") 받기 → Jev 11건 승인이면 `uv run python -m rag.multidoc.check multidoc.gen.n_per_type=350`으로 판정 → 통과 수·사유 집계 보고(300\~500건 확인)
2. [A] 긴 줄 처리를 진행하기로 하면 fix 브랜치: `check --prepare`가 긴 문단을 줄바꿈으로 나눔 → 12개 check_in 재생성 → 검사 → 판정
3. [D] G3 검수: 파일럿 통과 질의, 본 생성 뒤 무작위 50건 → 세트 SHA-256 동결
4. [F] 하네스 대기 24·25 반영(chore/, harness:evolve)
5. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). G3와 병렬 가능
6. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 사용자 확인 필요
- Jev 판정 호출 11건 승인
- 긴 줄 12개: law-0085·0112·0123·0135·0146·0156·0166·0180·0203, questioner-0202·0229·0332(문서 한 줄 2.4만\~7.4만 자라 작업자가 끝까지 못 읽음). fix 브랜치로 줄 나눈 뒤 검사할지, 이번 세트에서 뺄지
- questioner-0305 재검사: 작업자가 "11월 4일 문서 없음"으로 answerable=false를 적었으나 check_in 32행에 있음(70KB 입력 일부만 읽음). 그대로 두면 판정 탈락. 실패 건만 골라 다시 돌리면 편향이 생겨 지우지 않음
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 결정(사용자)
