# 다른 Orca 세션과 병행

배포와 생성 실험처럼 사용자가 + 버튼으로 만든 세션이 동시에 돌 수 있다(사용자 방침 2026-11-03).

- `data/`는 모든 세션이 함께 쓴다. 다른 세션이 쓰는 파일을 고치거나 지우지 않도록, 쓰기 전에 `main`의 STATUS "실행 중 작업"을 본다. worktree 세션은 자기 브랜치의 STATUS가 뒤처졌을 수 있어 `git fetch` 뒤 `git show origin/main:docs/STATUS.md`로 읽는다. 이 칸은 핸드오프 때만 갱신되어 지금 도는 작업을 놓칠 수 있으므로, 없음으로 적혀 있어도 다른 세션이 만든 파일은 덮어쓰거나 지우기 전에 사용자에게 묻는다
- 공유 기록(`_workspace/`의 대기 목록·진행 기록)은 .gitignore 대상이라 메인 체크아웃에 있고 worktree로 따라오지 않는다. worktree 세션은 메인 경로의 파일을 읽는다
- 상대 세션 작업에 영향을 줄 수 있는 일은 하기 전에 공유 기록에 한 줄 적는다: `uv run --no-project --quiet python .claude/hooks/sessions_news.py add "내용" "영향"`. 대상은 `data/`에 쓰거나 지우는 일과 오래 도는 실행, 공통 파일(`docs/SPEC.md`, `docs/DECISIONS.md`와 새 결정 번호, `configs/config.yaml`, `configs/exp/current.yaml`) 변경, 외부 상태(Space, Dataset 리비전, Vercel) 변경, 상대 작업의 전제를 바꾸는 사용자 결정이다. 일반 진행은 적지 않는다. `sessions_news` 훅이 상대가 새로 적은 줄과 상대 브랜치의 새 커밋을 지시마다 컨텍스트에 넣는다. 지금 작업에 영향이 있으면 사용자에게 먼저 알린다(ADR-0098). 입력→동작: `deploy`가 Space를 재시작하기 전에 적으면 `main`은 다음 지시 때 그 줄을 받는다
- 세션 간 메시지는 사용자가 지시할 때 보낸다(사용자 2026-11-05). 사용자에게 옮겨 달라고 하지 않고 메인이 `orca terminal send`로 직접 보낸다(사용자 지시 2026-11-05). 이 명령은 그 세션의 입력 칸에 글자를 넣으므로 사용자가 쓰던 글과 섞일 수 있다. 보내기 전에 `orca terminal read --terminal <handle> --screen --json`으로 입력 칸(`❯` 줄)이 비었는지와 `draft`(Orca 작성 칸에 쓰던 글, 있을 때만 나온다)가 없는지 보고, 보낸 뒤에는 같은 명령으로 도착을 확인한다. 입력→동작: 입력 칸에 사용자가 쓰던 글자가 있으면 보내지 않고 기다렸다 다시 본다
