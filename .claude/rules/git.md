# 브랜치·커밋·PR 규약

## 기본 규칙

1. `main`에 직접 커밋하지 않는다.
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

Claude가 브랜치를 push하고 `gh pr create`로 PR을 만든다. diff 확인과 병합은 사용자가 한다.

1. `uv run pytest -q`, `uv run ruff check .` 통과를 확인한다
2. 사용자 요청에 따라 self-review를 한다. 작성 맥락과 분리하려고 `/code-review`나 subagent로 실행한다
3. 본문에 대응 문서(SLICE·EXP), 변경, 검증 결과, self-review 지적과 반영 여부, 범위 밖 항목을 적는다

병합은 merge commit으로 한다. squash나 rebase를 쓰면 EXP 문서에 적은 커밋 해시가 `main`에서 사라진다.
