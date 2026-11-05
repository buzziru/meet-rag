# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 `exp029`다(프롬프트 v19, 검색·표지·1위 근거 확장·judge j_v13은 그대로, D-85, DECISIONS 머리 줄). 판정 실험이 아니고 사용자가 채택했다(S44)
- 생성 실험과 배포를 별도 세션으로 운영한다(사용자 결정 2026-11-04). 세션은 Orca 이름으로 부른다: `main`(메인 체크아웃, 생성 실험, 브랜치와 무관), `deploy`(`.claude/worktrees/deploy`, 배포). 규칙은 `.claude/rules/sessions.md`다. 각 세션은 자기 절만 고치고 상대 세션의 절은 그대로 둔다
- `deploy` 현재: 비공개 ZeroGPU Space `ingyoun/meet-rag`에 앱이 돈다(재정렬을 끈 구성, S38, PR #215). 데이터는 비공개 Dataset `ingyoun/meet-rag-data`를 읽기 전용 볼륨으로 붙였고 커밋을 올리지 않는다(D-79). 결정 D-79(HF 처리처, 볼륨), D-80(ZeroGPU 유지, 벡터스토어 없음). 값은 `docs/slices/38-hf-space.md` 결과 절이다. worktree는 브랜치 `feat/s39-zerogpu-rerank`에 있고(지시서 커밋까지, PR 없음), `data`는 원본 junction이라 지울 때 링크만 지운다. HF CLI는 `ingyoun` 계정, Git Bash에서 `/`로 시작하는 값을 넘길 때는 `MSYS_NO_PATHCONV=1`을 쓴다
- `main` 현재: S43 오차 분석과 S44를 마쳤다(D-82~D-86). 회의 정보 괄호 표시는 `deploy` 세션의 S45다. 회고 입력은 `_workspace/retrospective_main_notes.md`에도 적었다
- 진행 기록: `_workspace/s42_main_progress.md`, 하네스 대기 `_workspace/00_main_harness-pending.md`. 메인 체크아웃에 있고 worktree로 따라오지 않는다

## 실행 중 작업
- 없음

## 판정 대기
- 없음

## 리뷰 대기 PR
- `feat/s44-answer-gaps` S44 PR

## 다음 행동
`main` 세션(그쪽 핸드오프에서 이 절을 고친다):
1. 생성 단계 종료: SPEC·DECISIONS 정합 점검 → SPEC 미결 5(생성 test 질의 범위) 결정 → test 1회(`LANGSMITH_TRACING=false`, D-72). test 때 코드 집계(회의 표기, 인용 없는 답변)를 함께 낼지 그때 정한다

`deploy` 세션:
1. [A] S39 실시간 재정렬: `docs/slices/39-zerogpu-rerank.md`를 사용자가 초안 커밋까지 지시했다(2026-11-04). 지시서를 다시 보이고 구현 착수 지시를 받은 뒤 `feat/s39-zerogpu-rerank`에서 구현한다. 방안은 같은 Space ZeroGPU, 할당량이 떨어지면 재정렬을 뺀 검색이다(사용자 결정). 목표는 로그인 없는 방문자의 5\~10개 질의다. OpenRouter 약 25번, $0.02 이하 승인됨. 소유자 계정 할당량을 소진하지 않는다. 측정 도구는 메인 체크아웃 `_workspace/s38_space_measure.py`, 기록은 `_workspace/s38_main_progress.md`
2. S39를 마칠 때 PLAN S39 줄을 고치고 S41 항목에 비로그인 브라우저 확인(5\~10개 질의, 할당량 소진 시 재정렬 없는 답변과 안내)을 더한다

## 사용자 확인 필요
- `main`: 디스크 여유 18.09G(옛 KURE-v1 스냅샷, 전역 HF hub, uv 캐시를 지움). `data/index/kure-v1-fixed-512-64/full`(0.73G)은 재구축에 Colab 비용이 들어 그대로 뒀다. 더 필요하면 프로젝트 밖 약 190G를 점검한다
