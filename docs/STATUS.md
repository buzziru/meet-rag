# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 `exp029`다(프롬프트 v19, 검색·표지·1위 근거 확장·judge j_v13은 그대로, D-85, DECISIONS 머리 줄). 판정 실험이 아니고 사용자가 채택했다(S44)
- 생성 실험과 배포를 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃, 생성 실험, 브랜치와 무관), `deploy`(`.claude/worktrees/deploy`, 배포). 규칙은 `.claude/rules/sessions.md`다. 각 세션은 자기 절만 고치고 상대 세션의 절은 그대로 둔다. 상대에게 영향을 줄 일은 공유 기록 `_workspace/00_sessions_log.md`에 적고 `sessions_news` 훅이 지시마다 전달한다. 늦으면 안 되는 일은 직접 보낸다(ADR-0098)
- `deploy` 현재: S45 회의 정보 괄호 표시와 `EmbedProcess` 수정을 병합했다(PR #228, D-86, D-88). 비공개 ZeroGPU Space `ingyoun/meet-rag`는 Hub 060d729(S45 포함)로 돌고, Vercel 페이지는 Space가 비공개라 채팅 연결 대기다. 화면 점검은 Vercel에서만 하고 Gradio 화면은 없앤다(D-88). worktree는 병합된 `feat/s45-meeting-info`에 머물러 있어 main 맞추기가 먼저다. `data`는 원본 junction이라 지울 때 링크만 지운다. 값과 주의는 `docs/slices/39-zerogpu-rerank.md`, `39b-vercel-front.md`, `45-meeting-info.md` 결과 절이다
- `main` 현재: 세션 소식 훅(PR #226, ADR-0098)을 병합했고, 생성 test 경로(S46, PR #227)와 이어 쓰기 해석(D-89)을 올렸다. test 1회는 아직 실행하지 않았다. 입력 해시와 지문, 호출 전 검사는 실제 설정으로 통과했다. 정합 점검의 낮음 약 20건은 프로젝트 마무리 전 점검으로 넘겼다. 회고 입력은 `_workspace/retrospective_main_notes.md`에도 적었다
- 진행 기록: `_workspace/s46_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- `main`: 없음
- `deploy`: 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- PR #227(S46 생성 test 경로, D-89, 위험도 단방향). 판단할 곳은 사용자가 답했고 이 STATUS 커밋까지 올린 뒤 병합한다(사용자 2026-11-05)

## 다음 행동
`main` 세션(그쪽 핸드오프에서 이 절을 고친다):
1. PR #227 병합 확인 뒤 main 맞추기
2. 생성 test 1회: 사용자 지시로 `docs/slices/46-gen-test.md` "1회 실행 절차"대로 한다. 호출 수·시간·비용을 다시 보고하고 승인받는다(어림 약 $4.2, 약 75분). 평일 19시 뒤나 주말(한국 시간)에 시작하고, 그동안 PC가 켜져 있어야 한다. 결과로 기준을 바꾸지 않는다(D-87 결정 5)
3. [F] 하네스 대기 목록의 `[대기]` 항목: `sessions.md`의 `draft` 확인 오탐(Claude 추천 문구가 `draft`에 나온다, 사용자 지적), 충돌 표식 검사, 파일 끝 줄바꿈, Vercel 작업 절

`deploy` 세션:
1. [F] `meet-rag` 스킬 "화면 검증" 절의 대상 주소를 Vercel 배포 페이지로 고친다(D-88 결정 1, `_workspace/00_main_harness-pending.md`). 최신 `main`에서 `chore/` 브랜치를 딴다
2. [A] S47 화면 점검용 채팅 열기: 지시서를 쓰고 확인받는다. 페이지가 브라우저 저장소의 토큰으로 비공개 Space에 연결한다(D-88 결정 3, PLAN). 토큰으로 연결되는지 먼저 확인한다. 병합 뒤 사용자에게 토큰을 만들고 넣는 절차를 단계별로 안내하고 S45 답변 표시를 Vercel에서 확인받는다(S45 완료 기준 5)
3. [A] S48 Gradio 화면 제거 → S40 대화 이어 가기 → S41 공개 마감. S41에서 토큰 코드를 지우고, 그 시점을 사용자에게 알려 토큰을 폐기하게 한다(사용자 요청, D-88 결정 3)

## 사용자 확인 필요
- `main`: 디스크 여유 18.09G(2026-11-05 앞 세션 값). `data/index/kure-v1-fixed-512-64/full`(0.73G)은 재구축에 Colab 비용이 들어 그대로 뒀다. 더 필요하면 프로젝트 밖 약 190G를 점검한다
- `deploy`: 없음. S45 완료 기준 5는 S47 병합 뒤에 받는다
