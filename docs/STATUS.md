# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 단계를 마쳤다(D-90, PR #233). test 1회 결과는 D-90에 있고 다시 돌리지 않는다. 생성 기준은 `exp029` 그대로다(프롬프트 v19, DECISIONS 머리 줄). 남은 큰 일은 공개 마감(S41)이다
- 전체 파이프라인 점검을 마쳤다(`docs/reviews/2026-11-pipeline-review.md`, PR #235). 지난 값을 바꾸는 지적은 확인되지 않았다. 사용자가 고른 항목: A 정합 표시 37건(완료), B 앱 4건(S49 완료, PR #236), C 안전장치 6건(S50, 리뷰 대기), D 고치지 않음
- 앞 결정의 표시에는 왜 바뀌었는지도 적는다(ADR-0102, `docs/CLAUDE.md`)
- 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃), `deploy`(`.claude/worktrees/deploy`). 규칙은 `.claude/rules/sessions.md`, 소식은 `_workspace/00_sessions_log.md`다
- `main` 현재: S50을 `feat/s50-run-guards`에서 PR로 올렸다
- `deploy` 현재: S47(토큰 연결), S48(Gradio 화면 제거), S49(앱 점검 4건)를 병합했다(PR #231, #232, #236, 하네스 #229, #234). 비공개 ZeroGPU Space `ingyoun/meet-rag`는 Hub 457de1c(`COMMIT` f6699d4)로 돌고, 그 뒤 main 차이 중 S49 쪽은 주석과 문서뿐이다. Vercel production과 미리보기 배포가 켜져 있고, production 페이지는 브라우저 저장소의 토큰으로 채팅이 된다. S49로 dev-full·multi-doc 순위와 재정렬 후보 쌍이 기준과 같음을 확인해 기준 변경 결정은 없었다. worktree는 `feat/s40-multiturn`(원격에 있음, PR 없음, S40 지시서와 사용자 결정만 있음)에 있다. `data`는 원본 junction이라 지울 때 링크만 지운다.
- 진행 기록: `_workspace/pipeline-review_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`, 회고 입력 `_workspace/retrospective_main_notes.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- `main`: 없음
- `deploy`: 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- S50 평가·실행 안전장치(`feat/s50-run-guards`, 위험도 단방향)

## 다음 행동
`main` 세션:
1. S50 PR 병합 확인 뒤 main 맞추기
2. [F] `protocol-guard`(`SKILL.md:29-30`)와 `meet-rag`(`SKILL.md:127`)의 생성 test 문구를 D-90 뒤 상태로 맞추고 test 경로를 둘지 정한다. 재귀 검색이 `.claude/worktrees/deploy/data` junction으로 들어간 일도 본다(`_workspace/00_main_harness-pending.md`). 다음 ADR 번호는 0103이다
3. S41 뒤 늘어난 결정만 정합 점검하고 `docs/SPEC.md`를 줄마다 대조한다(`docs/PLAN.md`)

`deploy` 세션:
1. [A] S40 대화 이어 가기: `feat/s40-multiturn`에서 구현한다. 지시서 `docs/slices/40-multiturn.md`의 결정과 호출 승인을 사용자에게 받았다(페이지 메모리, 인용 번호 뺀 원문 최근 3턴, 3초는 첫 질문만, 새 채팅 버튼, OpenRouter 11번 안쪽, Space 재시작 1번). 다시 묻지 않는다. D-30에 표시를 붙이고(왜 바뀌었는지까지, ADR-0102) 사용자 작업은 PR 리뷰 1번과 병합 뒤 production 대화 보기 1번이다
2. S40의 Space 업로드에서 처음 확인할 것: S50의 BM25 행 수 대조로 Space 시작이 멈추는지(Dataset 사본이 처음 대조된다, main 공유 기록), 정상 질문 경로와 S49의 추적 전송, 추적의 `git_commit`이 `COMMIT` 값인지, 같은 브랜치에 페이지 커밋과 문서 커밋을 이어 올릴 때 미리보기가 빌드되는지
3. [A] S41 공개 마감: 토큰 코드와 스킬의 토큰 옮기기 문장을 지우고 사용자에게 토큰 폐기 시점을 알린다(D-88 결정 3)

## 사용자 확인 필요
- `main`: 없음. 디스크 여유 29G(2026-11-05)
- `deploy`: 없음. 토큰 입력은 다시 요청하지 않는다(ADR-0101). S45 완료 기준 5는 사용자가 미리보기에서 답변을 보고 확인했다. 한 답변만 괄호가 붙지 않았고 조건은 모른다(S47 결과 절). 병합 뒤 production에서 질의 없이 연결과 문서 열람을 확인했다
