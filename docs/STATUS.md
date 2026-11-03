# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준을 EXP-019로 옮기는 결과 PR을 준비했다(`exp/exp019-speakers-head`, D-63). 판정은 보류이고 기준 전환은 판정과 무관하다(D-63 결정 2)
- 진행 기록: `_workspace/exp019_main_progress.md`(블라인드 회차 확인과 SPEC 정리 내용 포함)

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- EXP-019 결과 PR

## 다음 행동
1. [F] EXP-019 PR 병합 뒤 `chore/` PR: `gen-exp.md:35`(호출 하나가 실패하면 멈춘다), `gen-exp.md:10`·`protocol-guard`의 기준 judge 지시 표기, `src/rag/gen_eval/judge.py:96`의 안내 문구. H22 초안 전에 끝낸다
2. SPEC 정리 `docs/` PR: `docs/drafts/` 초안을 두고 사용자 승인을 받는다. 사용자가 정한 범위는 충돌 정리, 미결 사항 5(생성 test 규모), 재검증 규칙(재채점·변동 폭·사례 대조), `docs/SPEC.md:234` 비용 문장, ZDR 날짜, 설명 이동, `docs/CLAUDE.md` 재발 방지다. 블라인드 문장: 사람 검수는 모듈을 만드는 과정에서 했고(S14, S14c), 블라인드 확인은 S25에서 1질의 뒤 중단했다(사용자 확인 2026-11-03, D-51)
3. [B] H22 초안: 착수 전 확인과 지시 설계는 PLAN H22 항목에 있다

## 사용자 확인 필요
- 없음
