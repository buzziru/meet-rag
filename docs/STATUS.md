# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 단계 종료(D-39). 기준 EXP-017(D-36). 생성 평가 프로토콜은 SPEC "생성 단계 평가"(D-53)
- 생성 베이스라인(S25, gen-full 330): 충실성 0.803, 관련성 0.871, 종합 지표 0.843(314질의), 포함도 0.512(보조), 과잉 거부율 2.4%
- 생성 판정 명령 `rag.gen_eval.compare`(S27, #167, 기준값 `configs/eval/gen_v1.yaml` D-55). judge 모델·지시·채점 규칙이 다르면 멈추고, 생성 프롬프트·검색 조건에서 오는 값은 차이만 낸다
- 비밀 값은 Doppler(`meet-rag`/`dev`). `rag.*`와 노트북 커널은 `doppler run --`, 없으면 `require_env`가 멈춘다(#168, ADR-0068). Colab VM에는 키를 보내지 않는다
- 이번 세션 병합: #165\~#169(하네스 판단할 곳 방식, SPEC 뒤 안내문, S27, Doppler, 생성 평가 코드 리뷰 `docs/reviews/2026-10-gen-eval-review.md` 높음 1·중간 5·낮음 14)

## 리뷰 대기 PR (병합 순서)
1. #170 생성 실험 순서(D-56, `notebooks/38_01_생성실험순서.ipynb`): 판단할 곳 3(리뷰 수정 SLICE를 H24 앞에 둔 해석, 하네스 PR을 H24 판정 전에 병합, H24+H19 묶음과 D-56). H20 SLICE 범위는 대화로 정해 반영함(08c7a97)
2. #171 하네스 생성 평가 반영(ADR-0069, exp-judgment 6절, `references/gen-exp.md`, protocol-guard P11): 판단할 곳 4·5(gen-small 재확인 호출을 처음 승인에 포함, 형식 오류가 기준보다 1건 많아도 판정 전 알림)

## 실행 중 작업
- 없음. 하위 세션 A·B(Orca run_5bc227cb3d3a)는 끝났고 터미널을 닫았다. worktree `.claude/worktrees/harness-gen-eval`, `gen-exp-order`는 PR 병합 뒤 정리(링크 없음 확인, `_workspace` 기록 없음)

## 이번 세션 결정
- 판단할 곳은 질문을 남기고 머리에 "(결정: 요지, 커밋)"(ADR-0066). test 1회 안의 드라이런은 같은 1회, 생성 단계 종료는 남은 실험의 예상 개선 폭을 보고 사용자가 정함(ADR-0067)
- 생성 실험 순서와 상한이 δ 미만인 가설의 단독 실험·보류 예외 경로(D-56, #170)
- H20은 SLICE와 EXP로 나눈다. SLICE 범위: 생성과 judge가 같은 `speakers` 필드를 보고, 필드가 없는 기록의 렌더링은 지금과 같게(기준 재채점 없음). EXP 위치는 H22 결과를 보고 정함
- 생성 평가 리뷰의 높음·중간 6건(G2-1, G1-1, G2-2, G2-3, G3-1, G1-3)과 G2-7은 리팩터링 SLICE 하나로, 다음 세션

## 다음 행동
1. [C] PR #170·#171 병합 확인 → main 맞추기(코멘트 점검, worktree 두 곳 `orca worktree rm --worktree path:<경로>`, `buzziru/<이름>` 브랜치 삭제). 로컬 `docs/gen-eval-review`(병합된 #169 뒤에 잘못 push한 STATUS 커밋 aea30e7)는 `-d`로 지워지지 않아 남겨 둠. 원격 `docs/gen-eval-review`도 그 push로 다시 생겼다(사용자가 지움)
2. [A] 생성 평가 리뷰 수정 SLICE(높음·중간 6건 + G2-7). 첫 생성 EXP(H24) 전에. G1-3 렌더링 고정 테스트가 H20의 "필드가 없으면 지금과 같음" 확인에도 쓰인다
3. [A] H20 발언자 표시 SLICE(PLAN 줄의 범위). 2와 병렬 가능, API 비용 없음
4. [B] H24+H19 거부 형식 → H22 → (H20 EXP 위치 결정) → H10 → H23 → H18. 생성 EXP는 `references/gen-exp.md`(#171) 절차

## 사용자 확인 필요
- 위 리뷰 대기 PR의 판단할 곳
