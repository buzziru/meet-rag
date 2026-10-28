# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준 EXP-017(D-36). 생성 기준 EXP-018(프롬프트 v3, 예외 채택 D-61). 지금 기준은 별칭 `configs/exp/current.yaml`과 DECISIONS 머리 줄 두 곳에만 둔다(ADR-0076). 명령은 `+exp=current`
- 이번 세션 병합: #170\~#180(생성 실험 순서 D-56, 하네스 생성 EXP 절차 ADR-0069, worktree·표기 ADR-0070, D-57 대기·재시도와 DECISIONS 정합 보강 D-58, docs 규약과 P12 ADR-0071, S28 리뷰 수정·형식 재요청 D-59, docs 규약 확장 ADR-0074, S29 발언자 표시 D-60, SPEC 미결 4 해결 표지, EXP-018)
- 원칙(사용자 지적, PR #180): 채택마다 바뀌는 값을 명령·테스트 기대값·절차 문서에 고정하지 않는다. 기능 테스트는 처음 구현 당시 설정을 쓰고, 지금 기준 조립은 `test_current_alias_composes_as_its_baseline_exp`가 본다

## 실행 중 작업
- 없음. Orca Run `run_febd2188c781`의 하위 세션 S28·S29·docs-conventions는 모두 끝나 worktree·브랜치를 정리했다

## 판정 대기
- 없음

## 리뷰 대기 PR
1. #181 하네스(ADR-0076): 바뀌는 값 고정 금지(CLAUDE.md 금지 절·P4), 병합된 PR 브랜치 push 확인 절차와 `merged_branch_push_guard` 훅, prompt-audit 반영 3건, current 조립 테스트. 판단할 곳 1\~3 모두 결정 반영. 이 STATUS 커밋도 이 브랜치에 있다

## 다음 행동
1. [C] #181 병합 확인 → main 맞추기(코멘트 점검, 로컬 브랜치 `chore/harness-pinning-push-hooks` 삭제)
2. [F] 테스트 리뷰(사용자 지시 2026-10-28): 먼저 `docs/reviews/2026-10-test-review.md`에 리뷰 기준 문서를 쓰고 사용자 확인 → 영역별 읽기 전용 서브에이전트 리뷰 → 지적 표(심각도), 고칠 항목은 사용자가 고름. 형식은 `docs/reviews/2026-10-gen-eval-review.md`. 사용자가 확인한 기준 다섯 가지:
   - 시간 병목: `uv run pytest -q`(약 2분, 352개)를 `--durations`로 재서 느린 테스트의 원인(모델 로딩, 코퍼스 전체 읽기, config 반복 조립 등)
   - 레거시: 없앤 기능·끝난 단계(블라인드 확인, 옛 프롬프트, 지운 옵션)를 붙잡은 테스트. 과거 기록 고정이 목적인 테스트와 구분
   - 바뀐 설정과 어긋남: 기준 값을 기대값에 리터럴로 적은 곳(protocol-guard P4 기준, 예: `tests/test_generate.py:111` 임베딩 revision 리터럴의 해당 여부), 지금 동작과 다른 것을 검사하는 테스트
   - 빠진 검증: 깨지면 판정이 틀려지는데 테스트가 없는 곳(동결·보호 규칙 등)
   - 겹침: 같은 것을 여러 테스트가 반복 검사
3. [B] H22 질의자 주장 구분 EXP(다음 순서: H22 → (H20 EXP 위치 결정) → H10 → H23 → H18). 기준은 EXP-018 결과(DECISIONS 머리 줄), config는 exp018을 직접 상속. 절차 `references/gen-exp.md`

## 사용자 확인 필요
- 없음
