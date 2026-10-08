# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-001 hybrid(dense + BM25 Kiwi, RRF) 채택. dev-full Recall@5 0.9168(목표 0.90 도달), multi-doc Recall@5 0.4336(D-17). 실행 `rag.search +exp=exp001`
- EXP-002(H5 BM25 메타데이터 접두) 기각: dev-full −2.62%p [−4.02, −1.39], multi-doc Recall@5 +15.32%p. 하락은 긴 안건 접두의 BM25 길이 정규화(`notebooks/11_02_EXP002_하락원인.ipynb`). 브랜치 `exp/exp002-meta-bm25`의 PR이 병합 대기
- 메타데이터는 질의 조건 방식(H14, self-query)으로 이어 간다: 규칙·사전 추출, 약한 필터, 화자 필드는 적재 확장(D-19)
- SPEC 개정(D-18): 메타데이터 가설은 single-doc 보류일 때 multi-doc(Recall@5 개선, Complete@5 비하락)으로 판정. 가설 단위 중단은 한 백로그 항목의 첫 EXP 뒤 변형만 3회 연속으로 센다. SPEC이 EXP 문서에 우선
- 하네스: 판정 규칙(ADR-0029), PR 갱신 절차(코멘트 반영 절·판단할 곳 갱신·답글, ADR-0030)

## 실행 중 작업
- 없음(Colab 세션 없음)

## 이번 세션 결정
- EXP-001 채택, 다음 실험 기준(D-17). multi-doc 하락은 관찰, 회복은 dense 기준과도 비교
- SPEC 개정 D-18과 PR #47·#48 코멘트 보완(사용자)
- EXP-002 뒤 메타데이터 방향 D-19(사용자): H14 신설, S10·S11 선행, G4 평가 세트 확장은 대기

## 다음 행동
1. [C] EXP-002 PR 병합 확인(사용자)
2. [F] 하네스 대기 32: 지속 커널을 셀 추가로 분석을 이어 갈 때도 유지하고 `run --from N`으로 새 셀만 실행(`.claude/rules/notebook.md` §8)
3. [A] S10 적재 확장: 문서에 화자 필드(질의자·응답자 이름·직위·소속), 위원회·이름 사전. `doc_id`·`context` 불변 확인(PLAN "질의 기반 메타데이터 검색")
4. [A] S11 질의 조건 추출기(규칙·사전, multi-doc 질의로 추출 정확도)
5. [B] EXP-003 = H14 첫 EXP(기준 EXP-001, SPEC 메타데이터 판정). 동률 처리, 결합 깊이, 안건 항목 색인 단위는 초안에서 제안
6. [B] 이후 H2 reranker(SPEC 미결 3 배포 지연 상한을 여기서 정함) → H13 → H7

## 사용자 확인 필요
- G4(응답자 등 지목 질의 유형 추가)를 언제 할지
- `src/rag/eval_multi/compare.py:3` docstring의 "multi-doc은 판정에 쓰지 않으므로"는 D-18 뒤 옛 문구. 보호 경로라 고치려면 승인 필요
- 제외 목록 경로 키 `paths.multidoc_exclude`의 보호 대상 포함 여부(미정)
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
