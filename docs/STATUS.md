# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 EXP-021이다(`speakers.mode=marks`, 1위 근거 앞뒤 1청크 확장, 프롬프트 v8, judge j_v13, D-70, DECISIONS 머리 줄)
- 생성 실험과 배포를 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃, 생성 실험, 브랜치와 무관), `deploy`(`.claude/worktrees/deploy`, 배포). 규칙은 `.claude/rules/sessions.md`다. 각 세션은 자기 절만 고치고 상대 세션의 절은 그대로 둔다
- `deploy` 현재: 로컬 앱 완료(S35 채팅, S36 문서 탐색과 근거 탭, PR #207·#213), 앱은 꺼져 있다. 결정 D-74(앱 화면 열람 허용, 파일 내려받기 금지), D-77(화면 검증용 Aside 처리처, ADR-0089), D-78(배포 화면에 test 회의 문서 포함). 실행: `CLAUDE.md` 채팅 앱 줄. worktree는 브랜치 없이 `origin/main`에 있고, `data`는 원본 junction이라 지울 때 링크만 지운다
- 이번 세션 결정: D-71(LangSmith 추적은 단건·gen-small·배포에서 켜고 gen-full·반복 측정에서 끔, 한도 초과가 다시 나면 끔), D-72(LangSmith를 허용 처리처에 더함, test 1회는 끔, 목록은 `CLAUDE.md` 금지 절 한 곳). 하네스 ADR-0083\~0086
- 진행 기록: `_workspace/h22_main_progress.md`, `_workspace/issue201_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
`main` 세션(그쪽 핸드오프에서 이 절을 고친다):
1. [A] 지정 문구 변형 거부를 판별 코드로 해소한다(D-70 결정 5, PLAN). 다음 실험 전에 끝낸다. 먼저 기준 결과의 재계산 범위를 확인한다. 판정 코드 PR이라 병합 전 self-review 대상이다
2. [B] H23 초안: 측정 방법부터 정한다. 지금 judge는 이 문제를 따로 재지 않는다. H10의 나머지와 순서는 EXP-021 원인 분석을 보고 정한다
3. 생성 단계 종료: SPEC·DECISIONS 정합 점검 → SPEC 미결 5(생성 test 질의 범위) 결정 → test 1회(`LANGSMITH_TRACING=false`, D-72)

`deploy` 세션:
1. [A] S38 Space 배포 지시서를 쓴다. 최신 `main`에서 `feat/s38-hf-space`를 만들고, 먼저 PLAN 조각 순서를 S38 Space 배포 → S39 실시간 재정렬 → S40 대화 이어 가기(H21, D-76 결정 4) → S41 공개 마감으로 고친다(사용자 결정 2026-11-04, Space 먼저). 조각 번호는 `main` 세션과 겹치지 않는지 본다. 지시서에는 ZeroGPU 메모리·비공개 가능 여부 확인을 첫 완료 기준으로 둔다(무료 계정의 새 Space는 ZeroGPU만 열림). 화면 검증은 meet-rag "화면 검증" 절을 따른다

## 사용자 확인 필요
- `deploy`: S38에서 코퍼스와 인덱스를 올리기 전에 HF를 허용 처리처에 더하는 승인(D-72 절차). 비공개 Dataset 저장소 권고, 약 1.8GB
- `deploy`: Space 작업 전에 PowerShell에서 `& "$HOME\.local\bin\hf.exe" auth login`(쓰기 권한 토큰)
- LangSmith 프로젝트가 비공개인지 화면에서 확인한다. 추적에 질의와 근거가 들어가므로 공개면 D-31 위반이다(D-72 감수하는 것). 저장소에서 확인할 수 없다
