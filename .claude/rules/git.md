# 브랜치·커밋·PR 규약

## 기본 규칙

1. `main`에 직접 커밋하지 않는다. 예외는 아래 "핸드오프" 절차의 `docs/STATUS.md` 하나뿐이다.
2. 모든 작업은 최신 `main`에서 딴 브랜치에서 시작한다.
3. 브랜치 하나에는 목적 하나만 둔다.
4. 작업이 끝나면 PR을 만든다.
5. 사용자는 PR 화면에서 diff를 한 번 읽는다.
6. 테스트와 린트가 통과한 뒤 병합한다.
7. 병합 후 브랜치를 삭제한다.

## 세션 시작

- `git branch --show-current`로 현재 브랜치를 확인한다.
- `main`이면 코드나 문서를 고치기 전에 브랜치를 만든다.
- 다른 목적의 브랜치에 있으면 사용자에게 알리고 정리한 뒤 진행한다.

## 브랜치

- 접두사: `feat/`(SLICE), `exp/`(EXP), `docs/`, `fix/`, `chore/`
- SLICE·EXP 번호를 넣는다. 예: `feat/s01-data`, `exp/exp001-hybrid`
- 영문 소문자, 숫자, 하이픈만 쓴다. 한글은 git이 이스케이프해 출력한다
- 기각된 실험도 병합한다. EXP 문서, config, 코드가 함께 남아야 재현할 수 있다. 실험 코드는 config로 켜는 형태로 만들어 기준 설정의 동작을 바꾸지 않는다

## 커밋

- 형식: `<타입>: <요약>`. 타입은 `feat`, `fix`, `exp`, `docs`, `test`, `refactor`, `chore`
- 요약은 한국어 한 줄로 무엇을 바꿨는지, 본문에는 왜 바꿨는지 쓴다
- 커밋 하나에 논리적 변경 하나. 코드와 그 테스트는 같은 커밋에 둔다
- 커밋 전에 `data/`와 `.env`가 스테이징되지 않았는지 확인한다. 저장소는 공개되고, AI Hub 데이터는 재배포가 제한된다

## PR

Claude가 브랜치를 원격에 올리고 `gh pr create`로 PR을 만든다. diff 확인과 병합은 사용자가 한다.

1. `uv run pytest -q`, `uv run ruff check .` 통과를 확인한다. PR 내용이 사용자 결정에 따라 바뀌는 작업이면 결정을 받아 반영한 뒤 올린다(사소한 결정은 PR 코멘트로 받는다). 결정 전에 올리면 PR을 다시 고치게 된다
2. 사용자 요청에 따라 self-review를 한다. 작성 맥락과 분리하려고 `/code-review`나 subagent로 실행한다
3. `pr-briefer`를 불러 받은 리뷰 가이드(`## 리뷰 가이드`)를 본문 맨 위에 둔다. meet-rag 흐름 밖에서 올리는 PR도 같다. 바뀐 파일이 모두 `docs/` 아래면 부르지 않고, `docs/SPEC.md`나 `docs/DECISIONS.md`가 바뀌었을 때만 본문 맨 위에 `위험도: 단방향(SPEC·DECISIONS 변경)` 한 줄을 적는다. 이어서 대응 문서(SLICE·EXP), 변경, 검증 결과, self-review 지적과 반영 여부, 범위 밖 항목을 적는다

병합은 merge commit으로 한다. squash나 rebase를 쓰면 EXP 문서에 적은 커밋 해시가 `main`에서 사라진다.

## 핸드오프

STATUS는 세션마다 덮어쓰는 스냅샷이고 코드가 아니므로 PR을 거치지 않는다.

- 작업 PR이 병합된 뒤 핸드오프하면 `main`에 직접 커밋한다
  1. `git switch main`, `git pull --ff-only`로 원격과 맞춘다
  2. `docs/STATUS.md`를 덮어쓴다
  3. `git add docs/STATUS.md` 후 `git diff --cached --name-only`가 이 파일 하나뿐인지 확인한다
  4. `docs: STATUS 갱신`으로 커밋하고 원격에 올린다
- 작업 도중 세션이 끝나면 STATUS 커밋을 작업 브랜치에 태운다
- 다른 파일을 고칠 거리가 생기면 이 경로를 쓰지 않고 브랜치를 만든다
