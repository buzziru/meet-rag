# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 `exp029`다(프롬프트 v19, 검색·표지·1위 근거 확장·judge j_v13은 그대로, D-85, DECISIONS 머리 줄). 판정 실험이 아니고 사용자가 채택했다(S44)
- 생성 실험과 배포를 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃, 생성 실험, 브랜치와 무관), `deploy`(`.claude/worktrees/deploy`, 배포). 규칙은 `.claude/rules/sessions.md`다. 각 세션은 자기 절만 고치고 상대 세션의 절은 그대로 둔다
- `deploy` 현재: 비공개 ZeroGPU Space `ingyoun/meet-rag`(Hub 62f55ac, v19)에 재정렬을 켠 앱이 돈다. 데이터는 시작할 때 비공개 Dataset을 커밋 고정으로 내려받는다(볼륨 없음, 재시작→실행 54\~58초). Vercel 프로젝트 `meet-rag`(팀 `ig-pr`, Root `deploy/web`)가 production 배포되고 cron이 등록됐다. 보호 설정 때문에 로그인해야 열리고 Space가 비공개라 채팅은 연결 대기다. 결정 D-84. 값은 `docs/slices/39-zerogpu-rerank.md`, `39b-vercel-front.md` 결과 절이다. worktree는 브랜치 `feat/s45-meeting-info`(S45 지시서까지, PR 없음)에 있고 `data`는 원본 junction이라 지울 때 링크만 지운다. HF CLI는 `ingyoun`, Vercel CLI는 로그인됨. 저장소 루트에서 `vercel deploy`를 하지 않는다. Git Bash에서 `/`로 시작하는 값을 넘길 때는 `MSYS_NO_PATHCONV=1`을 쓴다. 로컬 앱은 메모리가 빠듯해 `index.scope=dev-small`로 띄우고 끝나면 종료한다
- `main` 현재: S43 오차 분석, S44, 생성 test 전 정합 점검을 마쳤다(PR #220, #222, #225, D-82\~D-87). 생성 실험은 더 없고 다음은 test 경로 구현이다. 정합 점검의 낮음 약 20건은 프로젝트 마무리 전 점검으로 넘겼다. 회고 입력은 `_workspace/retrospective_main_notes.md`에도 적었다
- 진행 기록: `_workspace/s45_main_progress.md`, `_workspace/consistency_main_progress.md`, `_workspace/s44_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다. S43·S44 판독 입력과 표는 `data/gen_eval/error_analysis/`다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- 없음

## 다음 행동
`main` 세션(그쪽 핸드오프에서 이 절을 고친다):
1. [A] 생성 test 경로 구현: 최신 `main`에서 브랜치를 따서 지시서를 쓰고 확인받은 뒤 `rag.gen_eval`이 test 800질의(`gen_eval.seed` 순서)를 읽게 한다. 명시적 허용 없이는 멈추고 합성 입력으로만 검증한다. S13 임베딩·후보 쌍·재정렬 점수는 파일 내용을 읽지 않고 해시와 지문으로 대조한다(`data/index/*/queries-test.npz`, `data/rerank/test-full-*` 이름은 확인함). 800질의 검색 지표를 보호 경로를 고치지 않고 낼 방법과 test 1회 호출 수·시간을 지시서에 적는다(D-87). 비용은 j_v13 기준으로 다시 어림하고(judge 비피크 $5 안) 피크 시간대를 확인한다
2. 생성 test 1회: 사용자 지시로 `LANGSMITH_TRACING=false`, 비피크에 1회 실행한다. 보고 지표는 D-87 결정 3이고, 결과로 기준을 바꾸지 않는다

`deploy` 세션:
1. [A] S45 회의 정보 괄호 표시(D-86): `docs/slices/45-meeting-info.md` 지시서를 사용자가 확인했다(결정 사항 모두 답함). 브랜치 `feat/s45-meeting-info`에서 구현한다. 변환은 `rag.app` 쪽, 지어낸 질의 10개(OpenRouter 약 $0.004, 승인됨)로 첫 글자 지연과 v19 답변 화면을 본다
2. 같이 고칠 것: `PYTHONUTF8=1` 없이 `uv run pytest -q`를 돌리면 `test_embed_process_round_trips_query_and_vector_through_worker_protocol`가 실패한다(자식 프로세스 표준 입력이 cp949). `EmbedProcess` 환경에 UTF-8을 넣는다
3. [A] S40 대화 이어 가기 → S41 공개 마감(PLAN 항목에 보호 설정 해제, 대표 주소, 3초 재측정 1회, 공개 뒤 브라우저 확인과 cron 3일 관찰이 있다)

## 사용자 확인 필요
- `main`: `PYTHONUTF8` 없이 돌리면 `tests/test_generate.py`의 `embed_process` 테스트 1개가 실패한다는 보고가 있다(하네스 세션 2026-11-05, 원인 미조사, 대기 목록). 이 세션의 검증은 `PYTHONUTF8=1`로 돌렸다
- `main`: 디스크 여유 18.09G(옛 KURE-v1 스냅샷, 전역 HF hub, uv 캐시를 지움). `data/index/kure-v1-fixed-512-64/full`(0.73G)은 재구축에 Colab 비용이 들어 그대로 뒀다. 더 필요하면 프로젝트 밖 약 190G를 점검한다
