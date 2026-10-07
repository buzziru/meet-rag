# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc 보조 관찰: S7·S8·S8b 완료(D-13, D-14). 검사를 luna에서 Sonnet 에이전트로 바꾸는 S8c 진행 중
  - 코드 S8c(`feat/s08-checker-agent`, push, PR 전): `check --prepare`·에이전트 출력 판정·파일 상태 이어 하기, luna 경로 삭제, `check_v3`. 브랜치에 옛 STATUS 커밋(529f606)이 있다
  - 하네스: PR #33(검사 에이전트·작업자 풀, ADR-0020), #35(작업자는 CLI 메인 세션에서만, ADR-0021), #36(CLAUDE.md 명령 절 정리, ADR-0022) 병합. #34(`claude -p` 전환)는 닫음
- 작업자 훅은 IDE 확장(Cursor·VS Code) 세션에서만 적용되지 않는다. CLI 세션(`claude`, `claude --resume <세션 ID>`)에서는 Agent 도구로 불러도 거부를 확인했다
- 진행 기록 `_workspace/s08_main_progress.md`

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- 로컬 `data/multidoc/`: 파일럿 `gen_out` 40개, luna 검사 기록 40개는 `pilot_v4_luna/check/`(당시 `queries.jsonl` 복사본 포함), `check_out/` 비어 있음, 재검사 입력 `check_in/` 31개(`check_v3`) 준비됨. G3 갈린 5건 검수 `review/g3_pilot_split5_review.md`, Jev 실험 `quote_semantic/`
- 파일럿은 본 생성 검사가 끝날 때까지 보관하고, 그 뒤 `pilot_v1`\~`v4`를 지운다(사용자 결정)

## 다음 행동
1. [A] S8c 파일럿 재검사: CLI 세션인지 확인(시스템 프롬프트에 VS Code 확장 환경이 있으면 멈추고 CLI 재개 요청, ADR-0021) → `feat/s08-checker-agent`에 `main` 병합(STATUS 충돌은 `main` 쪽으로) → `check --dry-run multidoc.gen.n_per_type=20`(검사 대기 31, 판정 대기 9 예상) → 작업자 풀(Agent 도구 `multidoc-checker`, 동시 3개, 작업당 후보 집합 2개, 16작업, 약 30분, 큐 `_workspace/s08_queue.jsonl`. 사용자 승인 완료) → `check` 판정(Jev 호출 수 보고·승인) → 노트북 08_03(G3 5건 집계, Sonnet·luna·사람 비교, 수율, 뒷받침 판정 재실험 Jev 약 60회 승인) → D-14 갱신 → slice-verifier·protocol-auditor·pr-briefer → S8c PR
   - `n_per_type=20`이어야 conf 10\~19가 들어간다. law·questioner 10\~19는 생성 입력만 있다(생성 대기 20)
2. [F] 하네스 대기 22: S8c 병합 뒤 CLAUDE.md multi-doc 세 줄의 순서 절차를 meet-rag 스킬로 옮기고 한 줄만 남긴다(Jev 승인 문구는 "금지" 절과 중복이라 뺀다). 같은 브랜치에서 ADR-0016\~0022의 비어 있는 커밋 해시를 채운다
3. [D] G3 본 생성: S8c 병합 뒤에만 시작(사용자). 파일럿 `gen_out`·`check`를 `pilot_v4/`로 옮김 → `prepare n_per_type=350` → 생성(작업당 10개)·검사(작업당 2개) 작업자 풀 → 승인 때 Jev 호출 상한도 보고 → 300\~500건 확인
4. [D] G3 파일럿 통과 질의 검수, 본 생성 뒤 무작위 50건 재검수 → 세트 SHA-256 동결
5. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S8·G3과 병렬 가능
6. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 사용자 확인 필요
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
