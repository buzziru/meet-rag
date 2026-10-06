# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc 보조 관찰: S7·S8 완료(D-13, D-14, PR #30 병합). G3 본 생성 준비 중
- PR #31(`fix/s08-quote-match`, 인용 유사도 대조와 `quote_dependent`) 사용자 검토 중. 이 STATUS 커밋도 이 브랜치에 있다
- 진행 기록 `_workspace/s08_main_progress.md`

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- 로컬 `data/multidoc/`: `pools.jsonl` 950개(conf·questioner 350, law 250, SHA-256 `d1e0f04a…2bbc`), 파일럿 `gen_out`·`check` 40개(conf 0\~19, law·questioner 0\~9), `queries.jsonl` 15건(`c56dba8e…`), `pilot_v1`\~`pilot_v3`
- 파일럿은 본 생성 검사가 끝날 때까지 수율 개선 자료로 보관하고, 그 뒤 `pilot_v1`\~`v4`를 지운다(사용자 결정)

## 다음 행동
1. [D] G3 본 생성: PR #31 병합 여부 확인(미병합이면 사용자에게 묻고 멈춤) → `main`에서 `chore/g3-multidoc-generation` 브랜치 → 파일럿 `gen_out`·`check` 40개와 `queries.jsonl`을 `data/multidoc/pilot_v4/`로 이동 → `prepare multidoc.gen.n_per_type=350`(law는 250까지만 있음) → 후보 집합 950개 생성 예상 시간 보고·승인 → `multidoc-writer` 생성(동시 3개, 메인이 큐로 칸 채움, memory `agent-concurrency`) → `check --dry-run` 호출 수·비용 보고(약 740호출, 약 $2.5)·승인 → 검사 → 수율·인정 못 한 인용 수·`quote_dependent` 수 보고 → 300\~500건인지 확인
   - 생성 시간 참고: 파일럿 에이전트 1개가 후보 집합 10개에 6.5\~19분
   - 지시 버전 conf·questioner `gen_v4`, law `gen_v3`, 검사 `check_v2`, 인용 대조 `quote_match` 0.8·15자
2. [D] G3 파일럿 검수: luna·Sonnet 판정이 갈린 5건(conf-0005·0011·0014·0018, questioner-0005)과 파일럿 통과 질의. 본 생성 뒤 무작위 50건 재검수 → 세트 SHA-256을 DECISIONS에 적어 동결
3. [F] 하네스 대기 20: 에이전트 동시 실행 3개(최대 4), 교체 주기가 있는 작업자 풀(작업 k개 처리 후 교체, 섞임 검출용 식별 정보 반환)
4. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S8·G3과 병렬 가능
5. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그

## 사용자 확인 필요
- PR #31 병합 여부와 판단할 곳(탐색 폭 `n // 4`를 코드 상수로 둘지)
- G3 파일럿 검수(위 2)를 본 생성 전·후 어느 때 할지
- 작업자 풀의 작업 크기 k(생성 후보 집합 몇 개씩, 하네스 대기 20)
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
