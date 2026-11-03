# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 EXP-019다(D-63, PR #190 병합). 판정은 보류이고 기준 전환은 판정과 무관하다
- 하네스 `chore/f-gen-exp-judge-defer` PR 리뷰 대기(ADR-0078). 이 STATUS는 그 브랜치에 있다
- 진행 기록: `_workspace/specdoc_main_progress.md`(SPEC 지적·결정·문안), `_workspace/h22_main_progress.md`, `_workspace/exp019_main_progress.md`(끝남). 메인 체크아웃에만 있으므로 worktree 세션이면 메인에서 읽는다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- `chore/f-gen-exp-judge-defer`

## 다음 행동
1. SPEC 정리 `docs/` PR: 진행 기록대로 `docs/drafts/`에 초안을 두고 사용자 승인을 받는다. 정한 범위는 지적 정리, 미결 사항 5(생성 test 규모), 재검증 규칙(재채점·변동 폭·사례 대조), `docs/SPEC.md:234` 비용 문장, ZDR 날짜(2026-11-30까지), 설명 이동, 블라인드 문안, `docs/CLAUDE.md` 재발 방지다
2. [B] H22 초안: 먼저 EXP-019에서 관련성이 답함 → 일부로 내려간 질의를 읽어 원인을 가린다(PLAN H22, 진행 기록). 작업 전 새 세션을 쓴다

## 사용자 확인 필요
- 없음
