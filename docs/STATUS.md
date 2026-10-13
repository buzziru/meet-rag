# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-009 설정(D-28). EXP-008(hybrid + 조건 목록 + 최다 일치 필터 + 안건 법률명 조건, D-27)에서 dense 임베딩만 snowflake-arctic-embed-l-v2.0-ko로 바꿨다(SPEC 판정 규칙의 예외, 보류 판정). dev-full Recall@5 0.9214, multi-doc Recall@5 0.9513. 실행 `rag.conditions +exp=exp009 [search.queries=multidoc]` 뒤 `rag.search +exp=exp009`
- 이번 세션 EXP: 006 리랭커(SPEC 채택 +3.08%p, 운영 보류 D-26), 007 문서 집계(기각, H7 닫음), 008 법률명 조건(multi-doc 채택 D-27), 009 snowflake-ko(보류 → 예외 채택 D-28), 010 RRF dense 가중치 2(보류, 가중치 [1,1,1] 유지)
- 병합 대기 PR: 하네스(chore/colab-recovery-exp-order, ADR-0036·0037, 이 STATUS 포함)

## 실행 중 작업
- 없음(Colab 세션 없음)

## 이번 세션 결정
- D-26 리랭커 운영 보류. PR #61 코멘트: 운영 채택 때 그 사이 채택한 EXP를 리랭커 위에서 다시 판정한다. 월 $365는 상시 가동 최대치이고 scale-to-zero면 월 $1 이하 예상
- D-27 법률명 조건 채택, D-28 snowflake-ko 예외 채택. PR #65 코멘트: 예외는 보류 판정에 한하고 합당한 근거가 필요하다. 기각 판정의 채택은 금지한다
- H7 닫음, H13 보류로 두고 닫음(PR #65), H6 후보 교체(bge-m3 계열 제외), KURE-v2·멀티턴·법령 MCP는 아이디어로만(PLAN)
- 운영 채택은 성능만으로 하지 않고 지연·비용과 함께 정한다(사용자)

## 다음 행동
1. [C] 하네스 PR 리뷰·병합(사용자). 판단할 곳은 PR 본문 리뷰 가이드
2. [C] 문서 정리 PR(`docs/` 브랜치): D-26에 PR #61 코멘트(리랭커 운영 채택 시 재판정, scale-to-zero 월 $1 이하 예상) 반영, D-28에 PR #65 예외 원칙 반영, PLAN H13을 닫음으로, EXP-006·009 Colab CU 실제값(사용자 확인) 기록
3. [B] H9 다중 크기 청킹(기준 EXP-009 설정). 재임베딩이라 Colab 비용 승인 대상. 이어서 H4 → H3 → H8 → H5 dense 접두
4. [F] colab CLI 0.6.0 → 0.7.4 업데이트와 colab-operator 스킬 본문 갱신 검토(대기 목록)

## 사용자 확인 필요
- Colab 실제 사용량: EXP-006 T4 약 33분(환산 0.57 CU), EXP-009 L4 약 115분(환산 약 3.0 CU)
- SPEC 미결 3(배포 지연 상한): 리랭커 운영 채택 때 정한다
- G4(응답자 등 지목 질의 유형 추가)를 언제 할지
- `src/rag/eval_multi/compare.py:3` docstring의 옛 문구(보호 경로, 승인 필요)
