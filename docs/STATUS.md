# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). dev-full Recall@5 0.8584, 목표 0.90(D-09)
- multi-doc: S7·S8·S8b·S8c·G3·S9 완료. 동결 세트 600건(D-15), 기준선 Recall@5 0.466·Complete@5 0.315·Hit@5 0.618, 유형별 Hit@5 `conf` 0.983·`law` 0.513·`questioner` 0.298(D-16, PR #45)
- S9 채점 `rag.eval_multi.score`·`compare`, 검색 `rag.search index.scope=full search.queries=multidoc`. 질의 임베딩 캐시 `data/index/kure-v1/queries-multidoc.npz`가 있어 이후 dense 계열 실험은 재임베딩 없이 multi-doc 순위를 낼 수 있다
- 보호 대상 추가(ADR-0028): `src/rag/eval_multi/`, `multidoc.eval`, `configs/multidoc/g3_exclude.yaml`, `paths.multidoc_frozen`
- Colab 업로드 검사가 G3 동결 세트 질의를 dev로 인정(PR #44, ADR-0027)

## 실행 중 작업
- 없음(Colab 세션 없음 확인)

## 이번 세션 결정
- multi-doc 지표 k 5·10 유지, 재표본 단위 `pool_id` 유지(D-16, 사용자)
- S9 질의 임베딩은 Colab T4(약 5분, 약 0.09 CU)
- 동결 세트 제외 목록·경로 키도 보호 대상(사용자, PR #45 코멘트)

## 다음 행동
1. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). 결과 절에 single-doc 판정과 multi-doc 관찰(`rag.eval_multi.compare`, 기준 `data/runs/kure-v1-fixed-512-64-multidoc.csv`)을 함께 적는다. `law`·`questioner`는 날짜·위원회·위원 이름으로 회의를 지목해 BM25가 dense와 다르게 움직일 수 있다(D-16 관찰)
2. [B] 다음 후보: H2 reranker → H7 문서 집계. H12(화자 메타데이터)는 백로그이고 multi-doc `questioner` 관찰과 함께 본다

## 다음 추가 생성 때 선행 작업
- 생성 입력(`rag.multidoc.prepare`의 `gen_in`·`docs`)에 `wrap_lines` 적용(ADR-0024)
- 안건 목록 중복 제거(2026-10-07 사용자 결정, PR #43 코멘트)
- law 생성 지시에 다룰 법안·주제를 질의에 명시하는 규칙(D-15)

## 사용자 확인 필요
- 제외 목록 경로 키 `paths.multidoc_exclude`는 보호 대상에 없음(동결 결과는 D-15 SHA-256으로 확인 가능). 넣을지 미정
- 전역 훅 `ko-doc-check`의 test 분할 오탐은 관찰 중
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 실험에서 결정(사용자)
