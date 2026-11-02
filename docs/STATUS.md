# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 생성 기준은 아직 EXP-018이다(DECISIONS 머리 줄, `configs/exp/current.yaml`). 발언자 머리 줄을 지표와 무관한 메타데이터로 정했고(D-63), EXP-019 결과 PR에서 기준을 옮긴다
- 작업 브랜치 `exp/exp019-speakers-head`(PR 없음). gen-small을 마쳤고, judge 지시 재검증 중이다. j_v10은 질의자 주장을 사실처럼 쓴 진술에 1을 주는 쪽으로 치우쳐 쓰지 않기로 했고 `verdicts`만 고친 j_v11을 만들었다(D-63 결정 8, `docs/experiments/EXP-019.md` 실행 절)
- 이번 세션 병합: #189(S31 judge 실패 질의 재처리, D-64). 이 브랜치에는 아직 합치지 않았다
- 진행 기록: `_workspace/exp019_main_progress.md`

## 실행 중 작업
- 기준 재채점 `rag.gen_eval.judge +exp=exp018 judge/prompt=j_v11`(12:36쯤 시작, 12:53쯤 끝날 어림). 결과 파일 `…-v3-dev-full-deepseek_go_mixed-j_v11.jsonl`이 없으면 같은 명령으로 이어 간다

## 판정 대기
- EXP-019(재검증 뒤 gen-full, 아직 실행 전)

## 리뷰 대기 PR
- 없음

## 다음 행동
1. [B] 재채점이 끝났는지 본다. main 맞추기(`fix/s31-judge-retry` 정리) 뒤 EXP 브랜치에 `main`을 합친다
2. [B] j_v8과 j_v11을 같은 기록으로 비교하고, 바뀐 질의 전체를 서브에이전트로 분류해(사용자 지시) 사용자에게 보고한다. 받아들이면 gen-full로 간다. 절차와 이후 단계는 진행 기록에 있다

## 사용자 확인 필요
- j_v11 재검증 결과를 받아들일지(결과 보고 뒤)
