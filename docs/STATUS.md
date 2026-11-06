# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 단계를 마쳤다(D-90). 생성 기준은 `exp029` 그대로다(DECISIONS 머리 줄). 남은 큰 일은 공개 마감(S41)이다(`docs/PLAN.md`)
- 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃), `deploy`(`.claude/worktrees/deploy`). 규칙은 `.claude/rules/sessions.md`, 소식은 `_workspace/00_sessions_log.md`다. 다음 ADR 번호는 0108, 조각 번호는 S54부터다
- `main` 현재: 2026-11-06에 아래를 병합했다. 열린 PR과 열린 이슈는 없다
  - 일일 종합 #239 처리, `app.concurrency`가 1이 아니면 앱 시작을 멈춤(#240)
  - 하네스: 배포 코드는 일일 코드 리뷰가 본다(ADR-0104, #241), 판단 없는 worker는 opencode CLI(ADR-0105, #243), 화면 SLICE는 지시서에 `frontend-design` 디자인 방향, PR 전 `better-interface` 리뷰(ADR-0106, #244), worker 모델 고르는 기준(ADR-0107, #247). 디자인 스킬 9개는 전역 `~/.claude/skills`에 있다
  - 배포 페이지 디자인 점검(`docs/reviews/2026-11-design-review.md`, 지적 15, HIGH 4, #245). 수정은 `deploy`의 S52
  - 회고 두 편 `docs/retrospective/`(하네스·운영, RAG 내용, 진행 문서라 그대로 고쳐 쓴다, #246, #248), 원칙 문서에 B4·C2(#246)
  - S53 judge 변형 시험(#250): 뚜렷한 오류 세 유형을 50건 중 하나도 놓치지 않음. 미묘한 오류 검출률은 모른다(회고 `project-rag.md` 3.4·11절)
- `deploy` 현재: 2026-11-06에 S51 앞 근거 다시 쓰기(#249, D-91)와 S52 디자인 점검 수정·문서 뷰어 배치(#251)를 병합했다. 사용자가 S52 화면을 production에서 확인했다. 비공개 ZeroGPU Space `ingyoun/meet-rag`는 S52 코드(Hub 4b270e3, `COMMIT` ce737d2)로 돈다. 그 뒤 병합된 `src/` 변경은 `app.shown_words` 빈 값을 시작 때 막는 확인뿐이라 다시 올리지 않았고, S41 업로드 때 반영된다. LangSmith는 이번 달 한도 초과로 Space 추적이 꺼져 있다. worktree는 브랜치 없이 origin/main에 있다. `data`는 원본 junction이라 지울 때 링크만 지운다
- 진행 기록: 하네스 대기 `_workspace/00_main_harness-pending.md`, 세션 공유 기록 `_workspace/00_sessions_log.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- `main`: 없음
- `deploy`: 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
`main` 세션:
1. 세션 시작 때 main 맞추기(`.claude/rules/git.md`). S41 전까지 `main`의 할 일은 없다. 일일 종합 이슈가 열리면 처리한다
2. S41 뒤: 늘어난 결정만 정합 점검하고 `docs/SPEC.md`를 줄마다 대조한다, 회고 두 편에 공개 뒤 지연·주소·11/5 이후 작업일을 더한다(`docs/PLAN.md`)

`deploy` 세션:
1. 세션 시작 때 최신 main에서 S41 작업 브랜치를 만든다(worktree는 지금 브랜치 없이 origin/main에 있다)
2. [A] S41 공개 마감 지시서부터 쓴다. 아래를 지시서와 PLAN S41 줄에 넣는다
   - UI-6(빈 화면 안내). 추천 질의 출처는 D-74(평가 질의를 화면에 보이지 않음)와 맞춘다(PLAN S41 줄은 "test 질의 제외"로만 적혀 있다)
   - 문서 찾기의 목록 불러오기 표시(사용자 결정 2026-11-06): 연도를 고른 뒤 회의 칸이 켜지기까지 약 4초 동안 칸이 비활성이고 커서가 금지 표시라 오류처럼 보인다. 불러오는 동안 안내 글자("회의 목록을 불러오고 있습니다"), 스피너(움직임 줄이기 존중), `cursor: progress`, `aria-busy`를 둔다. 문서 칸도 같다. 아직 못 고르는 비활성 칸은 금지 표시 그대로
   - 4초의 원인 나누기: 서버 계산(`Corpus.meetings`)은 밀리초 단위로 추정(재지 않음)이라 Space 왕복 쪽으로 본다. 3초 재측정 때 서버 처리 시간과 페이지 시간을 나눠 본다
   - 토큰 코드와 스킬의 토큰 옮기기 문장을 지우고 사용자에게 토큰 폐기 시점을 알린다(D-88 결정 3)

## 사용자 확인 필요
- `main`: 없음
- `deploy`: S51 완료 기준 7(병합 뒤 production에서 대화가 자연스러운지)을 사용자가 봤는지 아직 듣지 못했다. 토큰 입력은 다시 요청하지 않는다(ADR-0101)

## 이번 세션에서 바뀐 작업 방식
- 명령이 거부되면 막은 장치(거부 규칙, 훅)와 목적부터 확인하고, 그 전에는 권한 추가·모드 변경·직접 실행을 권하지 않는다. `doppler run -- env …`는 전역 거부 규칙에 걸리니 환경 변수는 `doppler` 앞에 둔다(메모리, 회고 "Claude가 저지른 큰 실수 두 가지")
