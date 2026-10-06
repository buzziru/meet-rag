# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09). multi-doc 보조 관찰은 S7 완료(D-13), S8 진행 중
- S8 브랜치 `feat/s08-multidoc-queries`(지시서 `docs/slices/08-multidoc-queries.md`, 진행 기록 `_workspace/s08_main_progress.md`). 준비(`rag.multidoc.prepare`), 검사·판정(`rag.multidoc.check`), 생성 지시 `gen_v1`\~`gen_v4`·검사 지시 `check_v1`·`check_v2` 구현, pytest 56 통과
- 파일럿: v1 통과 5/30, v2 통과 8/30(검사 비용 합 $0.085). v3·v4는 생성만 하고 검사하지 않음(사용자 지시). 현재 생성 `ok` 31건: `conf` 0\~9 v3 6/10, `conf` 10\~19 v4 10/10, `law` 0\~9 v3 10/10, `questioner` 0\~9 v4 5/10(모두 회의별 열거형)

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 미완 상태
- 하네스 PR #29(multidoc-writer 읽기·쓰기 범위 훅, `omitClaudeMd`, ADR-0019) 사용자 검토 중. 에이전트 정의는 세션 시작 때 불러오므로 병합 뒤 새 세션부터 적용된다
- 로컬 `data/multidoc/`: `gen_in`(order 0\~19, 0\~9 SHA-256 `0697a168…64fc`), `docs`(원문), `gen_out`(위 31건 ok + skip), `pilot_v1`·`pilot_v2`(검사 결과 포함)·`pilot_v3`(`questioner` v3 생성). `check`·`queries.jsonl`은 아직 없음
- S8 지시서에 반영했고 DECISIONS에는 아직 없는 결정: 생성 Sonnet 에이전트·검사 OpenRouter `openai/gpt-6-luna`(제공자 `openai` 고정), 판정 규칙 1\~5 유지(완화 불채택), 정답 상한 `max_gold` 5, 질의자 메타데이터 입력, `questioner` 열거형은 한 회의 안, `conf`는 쟁점형만, 개요 확대·2단계 호출 불채택. 지표는 유형별 보고, k는 S9 전에 다시 정함

## 다음 행동
1. [A] S8 이어서: PR #29 병합 확인 → `main`을 S8 브랜치에 병합 → 생성 `ok` 31건 검사 시점을 사용자에게 확인(약 $0.10) → 검사 → `notebooks/08_01_파일럿.ipynb`(v1\~v4 수율 비교, 사유별 불통과, 비용 외삽) → 사용자 결정(본 생성 진행) → DECISIONS → slice-verifier·protocol-auditor → PR. 생성 에이전트를 다시 부를 때는 실행 기록에서 읽은 경로를 확인한다
2. [D] G3 multi-doc 질의 검수: S8 파일럿 검수 → 본 생성 300\~500건 → 50건 재검수 → 동결
3. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S8과 병렬 가능
4. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그에 추가됨

## 사용자 확인 필요
- S8 생성 결과 검사 시점(위 1)
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
