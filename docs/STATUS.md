# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 EXP-021이다(`speakers.mode=marks`, 1위 근거 앞뒤 1청크 확장, 프롬프트 v8, judge j_v13, D-70, DECISIONS 머리 줄)
- 다음 작업부터 생성 실험과 배포를 각각 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션 사이 규칙은 `.claude/rules/sessions.md`다
- 이번 세션 결정: D-71(LangSmith 추적은 단건·gen-small·배포에서 켜고 gen-full·반복 측정에서 끔, 한도 초과가 다시 나면 끔), D-72(LangSmith를 허용 처리처에 더함, test 1회는 끔, 목록은 `CLAUDE.md` 금지 절 한 곳). 하네스 ADR-0083\~0086
- 진행 기록: `_workspace/h22_main_progress.md`, `_workspace/issue201_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
생성 실험 세션:
1. [A] 지정 문구 변형 거부를 판별 코드로 해소한다(D-70 결정 5, PLAN). 다음 실험 전에 끝낸다. 먼저 기준 결과의 재계산 범위를 확인한다. 판정 코드 PR이라 병합 전 self-review 대상이다
2. [B] H23 초안: 측정 방법부터 정한다. 지금 judge는 이 문제를 따로 재지 않는다. H10의 나머지와 순서는 EXP-021 원인 분석을 보고 정한다
3. 생성 단계 종료: SPEC·DECISIONS 정합 점검 → SPEC 미결 5(생성 test 질의 범위) 결정 → test 1회(`LANGSMITH_TRACING=false`, D-72)

배포 세션:
1. [A] HF Space 작성: 배포 첫 조각의 지시서를 PLAN 이후 단계로 쓴다. worktree `.claude/worktrees/deploy`는 사용자가 배포용으로 만들었고 `buzziru/deploy`가 옛 `main`(ce9ce96)에 있다. 착수할 때 최신 `main`에서 규약 이름의 브랜치로 옮긴다(`git.md` 세션 시작). 배포 환경에서 추적을 켠다(D-71)

## 사용자 확인 필요
- LangSmith 프로젝트가 비공개인지 화면에서 확인한다. 추적에 질의와 근거가 들어가므로 공개면 D-31 위반이다(D-72 감수하는 것). 저장소에서 확인할 수 없다
