# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-004(D-24). hybrid + 질의 조건 목록(RRF 세 번째 목록) + 최다 일치 필터. dev-full Recall@5 0.9164, multi-doc Recall@5 0.9361·Complete@5 0.8717. 실행 `rag.search +exp=exp004`(조건 파일 `rag.conditions`가 먼저 있어야 함)
- H14(메타데이터 질의 조건): EXP-003 채택(D-23), EXP-004 채택(D-24). 가중 결합은 하지 않음. multi-doc 상승은 세트 구성(메타데이터로 묶음)과 필터가 맞물린 결과라 상한에 가깝게 읽는다
- H2(reranker): EXP-005 기각, 멈춤. KURE-Reranker-nano는 CPU 2스레드 질의당 37초라 실행 안 함, Jev는 dev-full Recall@5 −3.08%p [−4.16, −2.04]
- 병합 대기 PR: #59 EXP-005(이 STATUS 포함)

## 실행 중 작업
- 없음(Colab 세션 없음)

## 이번 세션 결정
- 병합된 로컬 브랜치는 main 맞추기에서 정리(ADR-0034, `.claude/rules/git.md`)
- D-22 약칭 유지(`국회 본회의`, 여러 위원회 약칭)
- D-23 EXP-003 채택(필드 2개 이상 일치, dev-small 확인 뒤 `min_fields: 2`)
- D-24 EXP-004 채택. 두 세트의 구성 원리 차이, 실사용에서는 질의 분석으로 RRF·필터를 고를 수 있음(사용자)
- D-25 dev 질의 OpenRouter(Jev) 전송은 EXP-005 일회성 예외. CLAUDE.md·SPEC은 고치지 않음
- H2 기각, 배포 지연 상한(SPEC 미결 3)은 H2에서 정하지 않음

## 다음 행동
1. [C] #59 리뷰·병합(사용자). 판단할 곳: D-25 일회성 예외 처리, 원인 미분리 상태에서 H2 전체 기각, Jev 비용 대조. 답이 오면 git.md PR 절 4번 절차
2. [B] H13 BM25 비중 낮추기(기준 EXP-004). RRF 가중치나 BM25 결합 깊이를 실행 전에 고정
3. [B] 이후 H7 → H5 dense 접두·H4·H3 → H9 → H6 → H8. H14 남은 변형(안건 항목 색인, `date`·`year_ref` 이중 계산)은 H13 뒤에 다시 정한다

## 다음 추가 생성 때 선행 작업
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에 `wrap_lines` 적용(ADR-0024)
- 안건 목록 중복 제거(2026-10-07 사용자 결정, PR #43 코멘트)
- law 생성 지시에 다룰 법안·주제를 질의에 명시하는 규칙(D-15)

## 사용자 확인 필요
- SPEC 미결 3(배포 지연 상한)을 어디서 정할지(H2 기각으로 미정)
- G4(응답자 등 지목 질의 유형 추가)를 언제 할지
- `src/rag/eval_multi/compare.py:3` docstring의 "multi-doc은 판정에 쓰지 않으므로"는 D-18 뒤 옛 문구. 보호 경로라 고치려면 승인 필요
- 제외 목록 경로 키 `paths.multidoc_exclude`의 보호 대상 포함 여부(미정)
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
