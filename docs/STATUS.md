# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c 완료(D-13, D-14). PR #37(S8c), #38(형식 오류 거부 3회 뒤 보류), #39(실행 순서를 meet-rag 스킬로, ADR-0023) 병합
- G3 본 생성 진행 중(2026-10-07 시작, 5시간 사용량 한도로 중단). 초기 판정 conf 0\~29 통과 19/30
- 진행 기록 `_workspace/s08_main_progress.md`, 큐 `_workspace/g3_queue.jsonl`, 작업 목록 `_workspace/g3_gen_jobs.txt`(생성 95작업)·`g3_check_jobs.txt`(검사, 60번까지 배정)

## 실행 중 작업
- 없음(중단 시 실행 중이던 작업은 모두 끝냄)
- 남은 수(`check --dry-run multidoc.gen.n_per_type=350`): 생성 대기 510(law 90\~249, questioner 0\~349), 검사 준비 30, 검사 대기 265, 판정 대기 115, 완료 30, 보류 0
- 생성 완료 440(conf 350: ok 330·skip 20, law 0\~89: ok 85·skip 5)

## 판정 대기
- 검사 출력 115개 판정 전. Jev 호출 수는 판정 전에 세어 보고·승인(지금까지 0건)

## 미완 상태
- 파일럿 결과는 `data/multidoc/pilot_v4/`(검사·판정까지), `pilot_v4_luna/`. 본 생성 검사가 끝나면 `pilot_v1`\~`v4` 삭제(사용자 결정)

## 다음 행동
1. [D] G3 본 생성 재개: CLI 세션 확인(ADR-0021) → `--dry-run`으로 남은 수 확인 → 생성 작업 45부터(`g3_gen_jobs.txt`, law는 gen_v3, questioner는 gen_v4) → 검사(`--prepare` 뒤 `check_in` 있고 `check_out` 없는 것, 작업당 2개) → Jev 호출 수 보고·승인 → `check` 판정 → 300\~500건 확인. 동시 4개(메모리 여유 확인 뒤)
   - 사용량 절감 후보(사용자 결정 필요): 입력의 안건 줄 중복 제거. 비중이 gen_in 44%, check_in 20%. 본 생성 도중 입력 형식 변경이라 "지시 고정"과의 관계를 정해야 함
2. [D] G3 검수: 파일럿 통과 질의, 본 생성 뒤 무작위 50건 → 세트 SHA-256 동결
3. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). G3와 병렬 가능
4. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 사용자 확인 필요
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 향상폭과 지연을 보고 결정(사용자). 미결 1은 G1 검수로 해결됨
