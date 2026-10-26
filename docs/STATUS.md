# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 단계 종료(D-39). 기준 EXP-017(D-36)
- 생성 단계 평가 모듈: S22 기준 반영(#145, judge j_v8), 판단 모델 미채택(#147, D-48), S23 동결(#148, D-49) 병합
- S24 변동 폭 측정 PR #149 리뷰 대기(브랜치 `feat/s24-variance`, 이 STATUS 커밋 포함). 판단할 곳은 리뷰로 모두 정해짐
  - D-50: 판정용 세트 dev-full 330질의(기본 설정), judge `deepseek_go_mixed` 고정(다수결 없음, `max_tokens` 16384), LangSmith 대량 실행 끔
  - 반복 실행(`gen_eval.gen_rep`, `judge.rep`), 동시 생성(검색 차례로·생성 동시 4), 응답별 시간·토큰 기록, judge 질의 안 독립 사슬 동시 호출
  - 측정 비용 비피크 약 $2.7. 근거 `notebooks/35_01_S24_변동폭.ipynb`

## 실행 중 작업
- 없음

## 이번 세션 결정
- 판단 모델(Decisions API)은 생성 평가에 쓰지 않음, 확정(D-48)
- `report.py`는 테스트 통과만으로 고칠 수 있음, j_v8·판정표는 동결 테스트로 고정(D-49)
- `nothink`은 일관성이 높지만 `verdicts` 0 판정 2.6%로 관대해 `mixed` 유지. `verdicts`만 low도 채택 안 함(D-50)
- 측정 표본 100질의는 판정용 세트에 남김(모듈 작동 확인용이었음, D-50)
- judge 질의 동시 수: 베이스라인 첫 실행에서 8(동시 호출 최대 32) 확인 → 문제없으면 8 → 16 단계 확인. 16 이상 전에 `Judge.ask` 재시도 여부를 베이스라인 지시서에서 정함
- jupyter-mcp-server는 쓰지 않음. nb_kernel 개선과 하네스 점검 결과를 하네스 PR 하나로 묶음(`_workspace/00_main_harness-pending.md` 끝 두 항목)
- LangSmith: 11월에 이어지면 켬, 배포 단계에서도 켬

## 다음 행동
1. [C] PR #149 리뷰·병합 → main 맞추기
2. [F] 하네스 PR: nb_kernel(ruff 자동 수정, traceback 축약, LF), wrap_up 검사 경합, 삭제 검사 정규식(`git -C … worktree remove`), PowerShell matcher, protocol-auditor 작업 종류 하네스, D-49 동결 대상 가이드 규칙, G5 시나리오 등
3. [D 또는 A] 블라인드 확인 1회: 흐름(D/A)과 일치 기준값을 지시서에서 정함
4. [A] 생성 베이스라인(dev-full 330, 비용 승인, judge 동시 8 확인, 재시도 여부 결정)
5. [A] 오라클 진단·최소 개선 폭 → SPEC 생성 평가 개정 → [F] 하네스 생성 평가 반영 → 생성 실험 순서 정리 → [B] H10

## 사용자 확인 필요
- PR #149 병합
