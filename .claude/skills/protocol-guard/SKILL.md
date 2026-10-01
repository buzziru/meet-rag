---
name: protocol-guard
description: meet-rag 브랜치 diff에서 평가 오염과 저장소 금지 조항 위반을 찾는 점검표. test 분할 접근, src/rag/eval·configs/eval·data/splits 수정, 파라미터 하드코딩, data/·.env 스테이징, summary_q의 무료 쿼터 전송, EXP 범위 밖 변경을 판정한다. protocol-auditor 에이전트가 PR 전 감사에서 쓰고, 메인이 커밋 직전 빠른 확인에 쓴다. 일반 코드 리뷰에는 쓰지 않는다.
---

# protocol-guard: 평가 프로토콜 점검표

검색 실험의 수치는 평가가 고정되어 있을 때만 서로 비교할 수 있다. 점수를 올리라는 목표를 받은 에이전트는 평가 쪽을 바꾸거나 test 정보를 쓰는 방식으로도 목표를 달성할 수 있다. 이 점검표는 그런 경로를 diff 단위로 막는다. 근거 문서는 `CLAUDE.md` "금지" 절과 `docs/SPEC.md` "누수 방지"·"자원 제약" 절이다. 두 문서와 이 표가 어긋나면 두 문서를 따르고 어긋남을 보고한다.

## 준비

```bash
git diff --name-status main...HEAD
git diff main...HEAD
git status --short
```

대응 SLICE·EXP 문서의 "수정 허용 파일", "바꾸는 것", "범위 밖"을 읽어 둔다.

## 점검 항목

### P1. test 분할 접근

test 질의를 읽거나 test 점수를 계산하는 코드 경로가 새로 생기면 위반이다. 검색 단계 종료 시 사용자 지시로 1회만 허용된다.

- `split == "test"`, `"test"` 문자열로 분할을 고르는 코드
- `data/splits/queries.csv`를 읽고 split으로 거르지 않은 채 질의 전체를 쓰는 코드. 필터가 없으면 test가 섞인다
- config에서 평가 분할을 바꿀 수 있게 하면서 기본값이나 호출부가 test인 경우

`tests/` 디렉터리(pytest)는 분할과 무관하다. 이름만 보고 판정하지 않는다.

### P2. 설정 선택에 test·dev-small 사용

필터 규칙, 프롬프트, 하이퍼파라미터 선택에 test 질의를 쓰면 위반이다. dev-small 점수로 채택을 판정하면 위반이다(SPEC: dev-small은 방향 확인용).

### P3. 보호 경로 수정

- `configs/eval/`는 항상 보호된다
- `src/rag/eval/`는 S3 완료 후, `data/splits/`는 S2 완료 후 보호된다. 완료 여부는 `docs/PLAN.md` 체크 상태로 판단한다
- `docs/SPEC.md`의 평가 프로토콜 절 수정

보호 경로를 바꿨으면, 사용자 승인 기록과 `docs/DECISIONS.md` 항목이 같은 diff에 있는지 확인한다. 둘 다 있으면 통과이고 기록만 남긴다.

### P4. 파라미터 하드코딩

청크 길이, top-k, 모델명, 배치 크기, seed, 경로, `base_url` 같은 값이 `src/rag/`에 리터럴로 들어가면 위반이다. 값은 `configs/`에서 받아야 한다. 알고리즘의 정의상 고정된 상수(예: RRF의 순위 역수 형태)는 해당하지 않지만, RRF의 `k`처럼 바꿀 수 있는 값은 해당한다. 판단이 어려우면 "불확실"로 둔다.

### P5. 커밋 금지 파일

`data/` 아래 파일, `.env`가 스테이징·커밋되면 위반이다. 노트북 출력에 들어간 회의록 발언 원문은 공개 자료라 허용되지만, `summary_q`·`summary_a`·`context_learn`(AI Hub 생성물)이 출력에 대량으로 남았으면 보고한다. Colab 실행 기록(`colab exec -f`가 만든 `*_output.ipynb`, `colab log -o`로 내보낸 기록)은 `outputs/notebooks/`에 두며 같은 기준으로 본다. 질의가 조금 들어간 것은 보고하지 않는다.

### P6. 무료 쿼터로 평가 질의 전송

`summary_q`(질의 파일의 `query`)를 Google AI Studio·Gemini 무료 쿼터 경로로 보내는 코드면 위반이다. 질의를 LLM에 넣는 실험은 유료 경로(OpenRouter)를 써야 하고, 그 경우 비용 보고와 사용자 승인이 필요하다. `context`만 보내는 생성 경로는 해당하지 않는다.

### P7. EXP 범위 밖 변경 (EXP 작업일 때)

diff를 EXP 문서의 "바꾸는 것"과 대조한다. 목록에 없는 설정·코드 변경이 있으면 위반이다. 실험 코드는 config로 켜는 형태여야 하고, 기준 설정(`configs/config.yaml`과 기본 그룹)의 동작을 바꾸면 위반이다.

### P8. SLICE 범위 밖 변경 (SLICE 작업일 때)

SLICE 문서의 "수정 허용 파일" 밖의 파일이 바뀌었으면 보고한다. 문서 갱신(`docs/`)은 세션 마무리 절차에 속하므로 해당하지 않는다.

## 판정

- 위반: 코드 경로를 따라가 확인한 것
- 불확실: 경로 끝까지 확인하지 못한 것. 무엇을 보면 확정되는지 적는다
- 해당 없음: 이 diff와 무관한 항목
