# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc 보조 관찰: S7·S8 완료, PR #31(인용 문구 교정 제거)·#32(S8b Jev 인용 의미 판정) 병합. 검사 모델을 luna에서 Sonnet 에이전트로 바꾸는 중(D-14)
  - 하네스 PR #33(`chore/multidoc-checker-agent`): `multidoc-checker`, 공용 읽기·쓰기 훅, 작업자 풀·작업 큐·중단·재개, D-14 검사 모델 기록, ADR-0020. 사용자 리뷰 대기
  - 코드 S8c(`feat/s08-checker-agent`, push, PR 전): `check --prepare`·에이전트 출력 판정·파일 상태 이어 하기, luna 경로 삭제, `check_v3`. 이 STATUS 커밋도 이 브랜치에 있다
- 진행 기록 `_workspace/s08_main_progress.md`

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- 로컬 `data/multidoc/`: 파일럿 `gen_out` 40개, luna 검사 기록 40개는 `pilot_v4_luna/check/`(당시 `queries.jsonl` 복사본 포함), `check/`는 비어 있음, 재검사 입력 `check_in/` 31개(`check_v3`) 준비됨. G3 갈린 5건 검수 `review/g3_pilot_split5_review.md`, Jev 실험 `quote_semantic/`
- 파일럿은 본 생성 검사가 끝날 때까지 보관하고, 그 뒤 `pilot_v1`\~`v4`를 지운다(사용자 결정)

## 다음 행동
1. [A] S8c 파일럿 재검사: PR #33 병합 확인(미병합이면 사용자에게 묻고 멈춤) → `feat/s08-checker-agent`에 `main` 병합 → `multidoc-checker` 훅 적용 확인(`check_in` 읽기 허용, `gen_out` 읽기 거부) → `check --dry-run multidoc.gen.n_per_type=20`(검사 대기 31, 판정 대기 9) → 소요 시간 보고·승인 → 작업자 풀(동시 3개, 작업당 후보 집합 2개, 16작업, 약 30분, 큐 `_workspace/s08_queue.jsonl`) → `check` 판정(Jev 호출 수 보고·승인) → 노트북 08_03(G3 5건 집계, 새 Sonnet·luna·사람 비교, 수율, 뒷받침 판정 재실험 Jev 약 60회 승인) → D-14 갱신 → slice-verifier·protocol-auditor·pr-briefer → S8c PR
   - `n_per_type=20`이어야 conf 10\~19가 들어간다. law·questioner 10\~19는 생성 입력만 있다(생성 대기 20)
2. [D] G3 본 생성: S8c 병합 뒤에만 시작(사용자). 파일럿 `gen_out`·`check`를 `pilot_v4/`로 옮김 → `prepare n_per_type=350` → 생성(작업당 10개)·검사(작업당 2개) 작업자 풀 → 승인 때 Jev 호출 상한도 보고 → 300\~500건 확인
3. [D] G3 파일럿 통과 질의 검수, 본 생성 뒤 무작위 50건 재검수 → 세트 SHA-256 동결
4. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S8·G3과 병렬 가능
5. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 사용자 확인 필요
- PR #33 판단할 곳 2개(D-14 근거 문구, 중단 정의)
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중(인코딩 수정 뒤 PR 본문 작성에서 1건)
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
