# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 단계 종료(D-39). 기준 EXP-017(D-36): EXP-014에 RRF 후보 상위 20개 KURE-Reranker-nano 재정렬. dev-full Recall@5 0.9566, test Recall@5 0.9577(3,003질의), 베이스라인 대비 test +10.52%p로 dev 이득 유지. 검색 부분 질의당 평균 약 0.84초(CPU 0.40 + T4 0.44)
- 생성 기본 경로: OpenRouter 유료 Gemma 4 31B, 사고 과정 끔, 제공자 CoreWeave 고정(D-37). 아직 구현하지 않음(`rag.generate`는 Google 무료 경로, 리랭커 미연결)
- 생성 평가 방향(D-38): RAGAS 정의를 빌린 LLM judge 직접 구현, judge는 API·버전 관리. SPEC 개정 초안 `docs/drafts/spec-generation-eval.md`(SPEC 미반영)
- 이번 세션 PR #91\~#102 병합: 백로그·문헌(H10·H11·H17), +1.0%p 해석(D-35)과 문서 작성 원칙, EXP-017(D-36), 생성 경로(D-37), 노트북 ruff 수정, S13 test 1회(search.queries=test, D-39), colab_job --allow-test 추가 뒤 제거(ADR-0043·0045)

## 실행 중 작업
- 없음(Colab 세션 없음, 노트북 커널 종료)

## 이번 세션 결정
- +1.0%p는 자동 채택선, 미만 보류는 D-33 선례로 사용자가 정한다(D-35). 최소 개선 폭은 베이스라인 확인 때 근거와 함께 정한다(문서 작성 원칙)
- 리랭커 운영 채택(D-36), D-26 재판정 조항은 하지 않음
- 생성: OpenRouter 유료, CoreWeave(fp4) 고정, D-30 3초는 첫 토큰 중앙값으로 판정(D-37)
- test 결과로 기준 설정을 바꾸지 않음. 실사용 질의는 따로 만들지 않고 배포 페이지에 시험용 질문 샘플을 둔다(PR #101 코멘트)
- 생성 단계 test 1회도 사용자 지시로 할 수 있다(D-38, PR #102 코멘트)
- H17(검색기별 상위 슬롯 보장)은 아이디어로만 남김

## 다음 행동
1. [A] 검색 단계 정리표: EXP별 single-doc·multi-doc 순위 변화 한 표(PLAN 이후 단계)
2. [D] G4 평가 세트 확장 검토: 하거나 닫을지 결정
3. [A] SPEC 생성 평가 개정: 초안의 남은 결정 사항을 정해 SPEC·CLAUDE.md(test 문구)에 옮긴다(사용자 승인)
4. [A] 생성 경로 구현: OpenRouter CoreWeave 설정(`configs/generator/`), 사고 과정 끔, `rag.generate`에 리랭커 연결, 실제 입력 길이에서 첫 토큰 지연 재측정(D-37 남은 일)
5. [B] 생성 실험(H10 컨텍스트 구성 등)은 3·4 뒤

## 사용자 확인 필요
- 남은 빈 워크트리 폴더 `.claude/worktrees/nervous-nobel-f8af97`, `stoic-cohen-b17c4b`: 두 하위 세션을 보관(archive)하면 지울 수 있다
- 캐시 정리 여부: `uv cache prune`, KURE-Reranker-nano HF 캐시
- 원격 브랜치 정리(사용자): `chore/harness-setup`, `docs/review-2026-10-01`
