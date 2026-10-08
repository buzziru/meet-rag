# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-001 hybrid(dense + BM25 Kiwi, RRF) 채택. dev-full Recall@5 0.9168(목표 0.90 도달), multi-doc Recall@5 0.4336(D-17). 실행 `rag.search +exp=exp001`
- EXP-002(H5 BM25 메타데이터 접두) 기각: dev-full −2.62%p [−4.02, −1.39], multi-doc Recall@5 +15.32%p. 하락은 긴 안건 접두의 BM25 길이 정규화(`notebooks/11_02_EXP002_하락원인.ipynb`)
- 메타데이터는 질의 조건 방식(H14, self-query)으로 이어 간다. 규칙·사전 추출, 약한 필터, 화자 필드는 적재 확장(D-19)
- SPEC 개정(D-18): 메타데이터 가설은 single-doc 보류일 때 multi-doc(Recall@5 개선, Complete@5 비하락)으로 판정. 가설 단위 중단은 한 백로그 항목의 첫 EXP 뒤 변형만 3회 연속으로 센다. SPEC이 EXP 문서에 우선
- 병합 대기 PR 2개(사용자 검토): #49 EXP-002 기록과 D-19(이 STATUS 포함), #50 하네스(지속 커널 유지, protocol-guard P9 질의 쪽 라벨 감사). **#49를 먼저 병합**한다(#50의 P9가 D-19·H14를 참조)

## 실행 중 작업
- 없음(Colab 세션 없음)

## 이번 세션 결정
- EXP-001 채택, 다음 실험 기준(D-17). multi-doc 회복은 dense 기준과도 비교
- SPEC 개정 D-18과 PR #47·#48 코멘트 보완(사용자)
- EXP-002 뒤 메타데이터 방향 D-19(사용자): H14 신설, S10·S11 선행, G4 평가 세트 확장은 대기
- H14·S10 전에 하네스 수정을 먼저 한다(사용자 지시) → #50

## 다음 행동
1. [C] #49 → #50 순서로 병합 확인(사용자). PR 판단할 곳의 답이 오면 git.md PR 절 4번 절차로 반영
2. [A] S10 적재 확장: 문서에 화자 필드(질의자·응답자 이름·직위·소속), 위원회·이름 사전(코퍼스 전체 문서에서, protocol-guard P9). `doc_id`·`context` 불변 확인. 지시서에서 test 분할 회의 문서의 라벨을 사전에 넣는지 정한다(PR #50 범위 밖 항목)
3. [A] S11 질의 조건 추출기(규칙·사전, multi-doc 질의로 추출 정확도)
4. [B] EXP-003 = H14 첫 EXP(기준 EXP-001, SPEC 메타데이터 판정). 동률 처리, 결합 깊이, 안건 항목 색인 단위는 초안에서 제안
5. [B] 이후 H2 reranker(SPEC 미결 3 배포 지연 상한을 여기서 정함) → H13 → H7

## 다음 추가 생성 때 선행 작업
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에 `wrap_lines` 적용(ADR-0024)
- 안건 목록 중복 제거(2026-10-07 사용자 결정, PR #43 코멘트)
- law 생성 지시에 다룰 법안·주제를 질의에 명시하는 규칙(D-15)

## 사용자 확인 필요
- PR #49 판단할 곳: S10 화자 필드와 single-doc 판정, H14를 새 항목으로 둔 것, S10·S11·H14를 H2보다 먼저 하는 순서, BM25 캐시 키·`run_name` 덮어쓰기
- PR #50 판단할 곳: S10 화자 필드 실험의 single-doc 채택 근거 허용 여부, 세션 마무리에 커널 `stop` 넣기, P9 경계 문구
- G4(응답자 등 지목 질의 유형 추가)를 언제 할지
- `src/rag/eval_multi/compare.py:3` docstring의 "multi-doc은 판정에 쓰지 않으므로"는 D-18 뒤 옛 문구. 보호 경로라 고치려면 승인 필요
- 제외 목록 경로 키 `paths.multidoc_exclude`의 보호 대상 포함 여부(미정)
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
