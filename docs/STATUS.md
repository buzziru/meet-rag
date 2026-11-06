# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 단계를 마쳤고(D-90) 데모를 공개했다(S41, D-92). 생성 기준은 `exp029` 그대로다(DECISIONS 머리 줄). 남은 큰 일은 `main`의 늘어난 결정 정합 점검과 회고 보강이다(`docs/PLAN.md`)
- 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃), `deploy`(`.claude/worktrees/deploy`). 규칙은 `.claude/rules/sessions.md`, 소식은 `_workspace/00_sessions_log.md`다. 다음 ADR 번호는 0108, 결정 번호는 D-93, 조각 번호는 S54부터다
- 공개 상태(2026-11-06): 데모 https://meet-rag.vercel.app (Vercel 로그인 보호는 미리보기에만). Space `ingyoun/meet-rag`는 공개이고 Hub b83fb90(`COMMIT` 53b91ea, PR 2 브랜치 코드)으로 돈다. 데이터는 비공개 Dataset에서 받는다. 질문 수 한도(같은 IP 1시간 50·하루 100, 전체 하루 500), 데모 키 월 $5, 공개 Space 추적 끔. 3초 판정 통과(첫 질문 중앙값 2.80초)
- `deploy` 현재: 2026-11-06에 S41 PR 1(#252)과 사용 한도(#253)를 병합했다. PR 2(공개 뒤 정리, D-92, 이 핸드오프 포함)는 리뷰 대기다. 병합 뒤 Space는 다시 올리지 않아도 코드가 같고, `COMMIT`만 병합 커밋과 다르다
- 진행 기록: 하네스 대기 `_workspace/00_main_harness-pending.md`(S41 스킬 토큰 문장 삭제 대기, 관찰 2건 추가), 세션 공유 기록 `_workspace/00_sessions_log.md`

## 실행 중 작업
- `main`: 없음
- `deploy`: 없음. 공개 Space의 cron 절전 방지를 2026-11-06부터 3일 관찰한다(재시작이 잦으면 백엔드 이전을 다시 본다, D-84 결정 6)

## 판정 대기
- 없음

## 리뷰 대기 PR
- S41 PR 2(#254, 공개 뒤 정리, D-92). 판단할 곳 1은 정했다(그대로, D-92 결정 9)

## 다음 행동
`main` 세션:
1. PR 2 병합 뒤 main 맞추기(`.claude/rules/git.md`). [C] 늘어난 결정만 정합 점검하고 `docs/SPEC.md`를 줄마다 대조한다(PLAN). D-92가 앞 결정 8개에 표시를 붙였다
2. 회고 두 편에 공개 뒤 지연(D-92, `slices/41-public-launch.md` 결과 절), 공개 주소, 11/5 이후 작업일을 더한다

`deploy` 세션:
1. PR 2 병합 뒤 main 맞추기. Space를 병합 커밋으로 다시 올려 `COMMIT`을 맞추고, 사용자에게 S47 브라우저 토큰 폐기를 알린다(D-88 결정 3)
2. [F] 스킬 "화면 검증" 절의 토큰 옮기기 문장을 지운다(`chore/` 브랜치, `harness:evolve`, ADR-0108). 대기 목록 첫 항목
3. 2026-11-09에 cron 3일 관찰 결과(Space 재시작·절전 기록, 첫 방문 대기, 재정렬 실패·시간 초과)를 보고 STATUS에 적는다

## 사용자 확인 필요
- `main`: 없음
- `deploy`: S47 토큰은 PR 2 병합 뒤 폐기(그 전에 폐기하면 토큰을 넣어 둔 브라우저에서 연결이 안 될 수 있다, 시험 안 함). S51 완료 기준 7(production에서 대화가 자연스러운지)은 아직 듣지 못했다

## 이번 세션에서 바뀐 작업 방식
- 판단 없는 공개 웹 조사는 opencode worker에 맡기고 그동안 다른 작업을 한다(사용자 지적, 하네스 대기 관찰)
