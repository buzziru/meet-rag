# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 EXP-023이다(프롬프트 v10, 검색·표지·1위 근거 확장·judge j_v13은 그대로, D-76, DECISIONS 머리 줄). SPEC 판정은 보류이고 사용자가 예외 채택했다
- 생성 실험과 배포를 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃, 생성 실험, 브랜치와 무관), `deploy`(`.claude/worktrees/deploy`, 배포). 규칙은 `.claude/rules/sessions.md`다. 각 세션은 자기 절만 고치고 상대 세션의 절은 그대로 둔다
- `deploy` 현재: 로컬 앱 완료(S35 채팅, S36 문서 탐색과 근거 탭, PR #207·#213), 앱은 꺼져 있다. 결정 D-74(앱 화면 열람 허용, 파일 내려받기 금지), D-77(화면 검증용 Aside 처리처, ADR-0089), D-78(배포 화면에 test 회의 문서 포함). 실행: `CLAUDE.md` 채팅 앱 줄. worktree는 브랜치 없이 `origin/main`에 있고, `data`는 원본 junction이라 지울 때 링크만 지운다
- `main` 이번 세션 결정: D-73(변형 거부 판별, S34), D-75(v9 미채택, S37), D-76(v10 채택, H10·H25 닫음, H21은 배포로). 생성 실험 백로그는 답변 형식 통일과 오차 분석만 남았다. 하네스 ADR-0088(PR #208)
- 진행 기록: `_workspace/exp022_main_progress.md`, `_workspace/s34_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
`main` 세션(그쪽 핸드오프에서 이 절을 고친다):
1. [A] 답변 형식 통일: 어떤 형식으로 맞출지 사용자에게 묻고 시작한다. 실험으로 채택을 정하지 않고, 프롬프트를 고칠 때 판정 지표와 report 관찰을 재어 성능이 떨어지지 않게 한다(D-75 결정 6, PLAN)
2. [A] 오차 분석: 판정 세트는 라벨·건수만 쓰고, 세트 밖 dev 약 100질의를 새로 생성·채점해 읽는다. 착수 때 호출 수와 비용을 보고한다(예상 생성 약 $0.04, judge 약 $0.6). 결과로 실험을 더할지 정한다(D-76 결정 6)
3. 생성 단계 종료: SPEC·DECISIONS 정합 점검 → SPEC 미결 5(생성 test 질의 범위) 결정 → test 1회(`LANGSMITH_TRACING=false`, D-72). test 때 코드 집계(회의 표기, 인용 없는 답변)를 함께 낼지 그때 정한다

`deploy` 세션:
1. [A] S38 Space 배포 지시서를 쓴다. 최신 `main`에서 `feat/s38-hf-space`를 만들고, 먼저 PLAN 조각 순서를 S38 Space 배포 → S39 실시간 재정렬 → S40 대화 이어 가기(H21, D-76 결정 4) → S41 공개 마감으로 고친다(사용자 결정 2026-11-04, Space 먼저). 조각 번호는 `main` 세션과 겹치지 않는지 본다. 지시서에는 ZeroGPU 메모리·비공개 가능 여부 확인을 첫 완료 기준으로 둔다(무료 계정의 새 Space는 ZeroGPU만 열림). 화면 검증은 meet-rag "화면 검증" 절을 따른다

## 사용자 확인 필요
- `deploy`: S38에서 코퍼스와 인덱스를 올리기 전에 HF를 허용 처리처에 더하는 승인(D-72 절차). 비공개 Dataset 저장소 권고, 약 1.8GB
- `deploy`: Space 작업 전에 PowerShell에서 `& "$HOME\.local\bin\hf.exe" auth login`(쓰기 권한 토큰)
- LangSmith 프로젝트가 비공개인지 화면에서 확인한다. 추적에 질의와 근거가 들어가므로 공개면 D-31 위반이다(D-72 감수하는 것). 저장소에서 확인할 수 없다
- `main`: uv 캐시 정리(`uv cache prune`)가 실패해 남았다. 실행 중인 serena MCP(uvx)가 캐시 안의 파일을 쓰고 있어서다. serena를 끈 뒤 다시 돌릴지 정한다. 옛 KURE-v1 스냅샷과 전역 `~/.cache/huggingface/hub`는 지웠다(여유 10.21G → 14.57G). `data/index/kure-v1-fixed-512-64/full`(0.73G)은 재구축에 Colab 비용이 들어 그대로 뒀다
