# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- naive RAG 베이스라인 완료(S1\~S6). 검색: KURE-v1, 512/64 청크, numpy 전수 검색(D-04, D-08). dev-full Recall@5 0.8584 [0.8428, 0.8741], 목표 0.90(D-09). 생성: Gemma 4 31B, 근거 5개, 프롬프트 v1(D-11)
- multi-doc 보조 관찰 추가(SPEC 개정, D-12). 판정은 single-doc만, multi-doc은 EXP마다 함께 보고. PLAN 보조 관찰 절 S7 → S8 → G3 → S9, 실험 백로그와 병렬 가능. 단 G3 동결 전에는 어떤 EXP의 multi-doc 점수도 보지 않는다
- S7 완료(PR #23, D-13): `rag.multidoc.pools`로 후보 집합 750개(`conf`·`law`·`questioner` 각 250). `law`만 시작 묶음(2\~3문서)을 고르고, `conf`·`questioner`는 S8 생성 에이전트가 후보 집합 개요에서 고른다

## 실행 중 작업
- 없음 (`colab sessions` 활성 세션 없음 확인)

## 판정 대기
- 없음. `docs/EXPERIMENTS.md`는 첫 EXP 판정 때 만든다

## 미완 상태
- 로컬 `data/`: full 512/64 인덱스, dev 질의 임베딩, 기준 순위 `data/runs/kure-v1-fixed-512-64-dev-full.csv`(SHA-256 `f1568843…bbe2`), `data/multidoc/pools.jsonl`(SHA-256 `c1ed8e59…0bea`)
- Google AI Studio 프로젝트는 무료 등급(결제 등록 시 Tier 1로 바뀌어 402)

## S8에 넘길 결정 (아직 DECISIONS에 없음, S8 지시서·DECISIONS에 기록)
- 생성: Claude Code Sonnet 에이전트. 검사(필요성·완전성): OpenRouter `openai/gpt-6-luna` 스크립트, 제공자 고정, `seed`·`structured_outputs`. 같은 모델로 생성·검증하는 편향을 피하려고 나눴다
- 검사 방식: 검사 쪽은 생성 쪽 근거 표시·기대 답을 보지 않고, 답에 필요한 요소마다 근거 문장을 원문 그대로 인용해 문서를 지정한다. 인용이 `context`에 있는지 코드로 대조하고, 정답 문서마다 다른 문서로 대신할 수 없는 요소가 있어야 통과
- 파일럿 30건으로 토큰·비용을 재고, 본 생성에서는 파일럿 후보 집합(`pool_id`)의 생성·검사 결과를 재사용해 다시 호출하지 않는다(사용자 요구). 파일럿 뒤 프롬프트가 바뀌면 재사용 여부를 보고하고 정한다
- `conf`·`questioner` 문서 선택 입력은 `context`·메타데이터만(질의·검색 결과 금지, 감사 지적). 생성 에이전트 추가는 하네스 변경이라 F 흐름·ADR
- G3에서 검사 판정과 사람 판정의 일치율을 기록한다. OpenRouter 호출 전 호출 수·비용 보고 후 승인

## 다음 행동
1. [A] S8 질의 생성·검증: `docs/slices/08-*.md` 지시서부터(위 결정 반영). Sonnet 생성 에이전트 정의는 [F]로 분리
2. [D] G3 multi-doc 질의 검수: S8 파일럿 30건 → 수정 → 본 생성 300\~500건 → 50건 재검수 → 동결
3. [B] EXP-001 = H1 hybrid(dense + BM25 Kiwi, RRF). S8과 병렬 가능. 판정은 SPEC 규칙(회의 단위 paired bootstrap, +1.0%p)
4. [B] 다음 후보: H2 reranker → H7 문서 집계. 비채택 3회 연속이면 SPEC 중단 기준

## 사용자 확인 필요
- SPEC 미결 1(G1, D-03 해결)에 해결 표시를 할지(PR #18에서 물음)
- SPEC 미결 3(배포 지연 상한)은 H2 reranker 판정 전에 정해야 함
