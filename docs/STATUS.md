# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 단계를 마쳤고(D-90) 데모를 공개했다(S41, D-92). 생성 기준은 `exp029` 그대로다(DECISIONS 머리 줄). 남은 큰 일은 `main`의 늘어난 결정 정합 점검과 회고 보강이다(`docs/PLAN.md`)
- 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃), `deploy`(`.claude/worktrees/deploy`). 규칙은 `.claude/rules/sessions.md`, 소식은 `_workspace/00_sessions_log.md`다. 다음 ADR 번호는 0108, 결정 번호는 D-93, 조각 번호는 S54부터다
- 공개 상태(2026-11-06): 데모 https://meet-rag.vercel.app (Vercel 로그인 보호는 미리보기에만). Space `ingyoun/meet-rag`는 공개이고 Hub 9bf0c07(`COMMIT` 618ba9a, PR #254 병합 커밋)으로 돈다. 데이터는 비공개 Dataset에서 받는다. 질문 수 한도(같은 IP 1시간 50·하루 100, 전체 하루 500), 데모 키 월 $5, 공개 Space 추적 끔. 3초 판정 통과(첫 질문 중앙값 2.80초)
- `deploy` 현재: 2026-11-06에 S41 PR 1(#252), 사용 한도(#253), 공개 뒤 정리(#254)를 병합했다. S47 브라우저 토큰은 사용자가 폐기했다. worktree는 브랜치 없이 origin/main에 있다. `data`는 원본 junction이라 지울 때 링크만 지운다
- `main` 2026-11-08: 이슈 #255(일일 종합)를 정리해 닫았다. 코드 리뷰 지적은 PR #256으로 병합했고, S41 답변 확인 위치 차이는 사용자가 받아들였다
- 진행 기록: 하네스 대기 `_workspace/00_main_harness-pending.md`(S41 스킬 토큰 문장 삭제 대기, 관찰 2건 추가), 세션 공유 기록 `_workspace/00_sessions_log.md`

## 실행 중 작업
- `main`: 없음
- `deploy`: 없음. 공개 Space의 cron 절전 방지를 2026-11-06부터 3일 관찰한다(재시작이 잦으면 백엔드 이전을 다시 본다, D-84 결정 6)

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
`main` 세션:
1. 세션 시작 때 main 맞추기(`.claude/rules/git.md`). [C] 늘어난 결정만 정합 점검하고 `docs/SPEC.md`를 줄마다 대조한다(PLAN). D-92가 앞 결정 8개에 표시를 붙였다
2. 회고 두 편에 공개 뒤 지연(D-92, `slices/41-public-launch.md` 결과 절), 공개 주소, 11/5 이후 작업일을 더한다

`deploy` 세션:
1. [F] 스킬 "화면 검증" 절의 토큰 옮기기 문장을 지운다(`chore/` 브랜치, `harness:evolve`, ADR-0108). 대기 목록 첫 항목
2. 2026-11-09에 cron 3일 관찰 결과(Space 재시작·절전 기록, 첫 방문 대기, 재정렬 실패·시간 초과)를 보고 STATUS에 적는다
3. 1·2를 마치면 사용자에게 production 완료 기준 확인을 요청한다: S40 기준 7(`slices/40-multiturn.md`), S51 기준 7(`slices/51-evidence-reuse.md`), S52 기준 5(`slices/52-design-fixes.md`). 이슈 #255에서 넘겨받았다(사용자 결정 2026-11-08)

## 사용자 확인 필요
- `main`: 없음
- `deploy`: production 완료 기준 세 개(S40 기준 7, S51 기준 7, S52 기준 5)는 deploy 작업을 마친 뒤 사용자가 확인한다
