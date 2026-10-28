# S29 근거 청크의 발언자 표시

근거 청크에 문서의 질의자·답변자(이름·직위·소속)와, 청크 안에서 라벨의 질의·답변 발언(`question.comment`·`answer.comment`)과 겹치는 부분의 표지를 더하는 기능을 config로 켜게 만든다(PLAN 생성 평가 "H20 발언자 표시(SLICE)", D-56 결정 3과 그 이후 변경). 기본 설정의 생성·judge 동작은 바꾸지 않는다. 채택은 H20 EXP 판정으로 정하고 이 SLICE는 판정하지 않는다.

흐름: A. 지시서 확인 뒤 구현한다. 새 API 호출, Colab, 재임베딩은 없다. 검색 텍스트(임베딩)는 바꾸지 않는다(D-56 근거).

## 배경 수치 (메인이 2026-10-28 셈, 코퍼스 38,516문서·dev 3,016질의)

원천 데이터는 회의록 전문이 아니라 질의·답변 2행이다(`docs/data.md` §5). 그래서 본문 전체의 발언별 발언자는 없고, 표시할 수 있는 것은 문서 단위 화자 목록과 라벨 발언이 차지하는 구간뿐이다.

| 항목 | 값 |
| --- | ---: |
| `questioners`·`answerers` 이름이 있는 문서 | 각 38,514(99.99%, 빈 2개는 D-20 한계) |
| 직위가 있는 문서 | 질의자 38,423(99.8%), 답변자 38,405(99.7%) |
| 소속이 있는 문서 | 질의자 341(0.9%), 답변자 31,597(82.0%) |
| 화자가 2명 이상인 문서 | 질의자 163(0.4%), 답변자 246(0.6%) |
| QA가 1개인 문서(`n_qa`) | 37,787(98.1%) |
| dev 질의 발언이 문서 `context`에 그대로 있음 | 3,016 / 3,016 |
| dev 답변 발언이 문서 `context`에 그대로 있음 | 3,004 / 3,016(12개 없음) |
| 발언이 `context`에 두 번 이상 나옴 | 질의 115, 답변 92 |
| 두 발언 길이 / `context` 길이 | 중앙값 0.278, 하위 10% 0.084 |

원천 라벨 zip 전체(39,633 QA)를 읽는 데 6.9초가 걸려, QA별 화자·발언은 실행 시작 때 원천 라벨에서 만든다. 미리 만든 파일을 두지 않는다(구현 원칙 "실행 config에 따라 바뀌는 입력을 미리 만든 파일로 읽지 않는다").

## 결정 사항 (구현 전 확인)

1. judge 지시 j_v8은 "근거에는 발언자 표기가 없다"(`configs/judge/prompt/j_v8.yaml:53`, `:161`)고 적혀 있는데, 이 기능을 켠 기록에서는 judge가 발언자 표기를 본다
   - (a) j_v8을 그대로 두고 judge 입력(`format_contexts`)에만 표기를 넣는다(추천). judge 레시피(지시 해시)가 같아 `rag.gen_eval.compare`가 S25 기준과 비교할 수 있고 기준 재채점이 없다(PLAN 범위 그대로). 감수: 지시의 그 문장이 사실과 어긋나고, 표기가 있는 입력에서 judge가 어떻게 판정하는지는 D-49 검증 범위 밖이다. 표기로 발언자가 분명해지면 규칙 5의 "질의자 발언이 분명함"·"답변자 발언이 분명함" 갈래로 판정이 옮겨 가는 것이 H20이 겨냥한 효과다
   - (b) 그 문장을 고친 j_v9를 만든다. compare는 지시 해시가 다르면 멈추므로 기준 S25를 j_v9로 다시 채점해야 하고(gen-full 약 1,700 호출), D-49 변경 절차(새 파일, 재검증, 사용자 결정)가 걸린다. PLAN의 "기준 재채점 없음"과 어긋난다
   - 예: (a)에서 후보 judge 요청의 근거에 `질의자: 홍길동 위원`이 붙어도 지시에는 "표기가 없다"가 남는다. (b)에서는 지시도 바뀌어 기준과 후보 모두 j_v9 결과로 비교한다
2. 표지의 원천에 test 회의 문서의 QA 라벨(발언·화자)을 넣는가
   - (a) 넣는다(추천). 검색 대상은 코퍼스 전체라 dev 질의의 근거에도 test 회의 문서가 올라온다. 문서 화자 필드와 값 사전을 test 문서까지 만든 D-20과 같은 이유다. 코드는 원천 라벨을 메모리에서 읽어 문서별 구간만 만들고, test 질의 텍스트(`summary_q`)는 읽지 않으며 내용을 출력·저장하지 않는다. test 회의 QA의 발언을 쓰는 것이 CLAUDE.md 금지("test 분할의 질의를 읽거나")에 걸리지 않는다는 해석이라 사용자가 정한다
   - (b) 뺀다. test 회의 문서에는 머리 줄만 붙고 겹침 표지가 없어, dev와 test의 생성 입력 조건이 달라진다(생성 단계 test 1회의 조건이 dev와 다름)
3. 머리 줄 단계와 겹침 표지 단계를 나눌지: config 값 하나(`speakers.mode`)에 `off`(기본)·`head`(머리 줄만)·`marks`(머리 줄과 겹침 표지)를 두고 이 SLICE에서 둘 다 만든다(추천). 구현 차이가 함수 하나라 따로 SLICE를 두지 않는다. EXP에서 어느 쪽을 시험할지(둘 다, `marks`만)는 H20 EXP 초안에서 정한다
   - 예: `speakers.mode=head`면 근거 머리에 화자 한 줄만, `marks`면 그 줄과 본문 안 겹친 구간 앞뒤 표지가 붙는다

알려 둘 것(결정을 바꾸지 않으면 감수): 평가 질의(`summary_q`)는 그 QA의 발언으로 만들어졌으므로(`docs/data.md` §7), 정답 문서 청크의 답변 표지는 그 질의의 정답 발언 구간과 거의 같다. 배포 때도 코퍼스 문서마다 라벨이 있어 표지는 같게 붙지만, 새 질의는 라벨 QA와 무관하므로 dev 평가의 개선 폭은 배포 때보다 클 수 있다(추론, 재지 않음). H20 EXP 문서에 단서로 적는다.

## 메인이 정한 것 (PR에서 확인)

1. 생성 기록의 근거 항목에 `speakers` 필드를 더하고 `text`는 원문 그대로 둔다. 생성(`build_messages`)과 judge(`format_contexts`)는 같은 렌더링 함수로 `speakers`를 표시한다. `mode=off`이면 필드를 만들지 않는다
   - 형식: `{"questioners": [{name, position, affiliation}], "answerers": [...], "spans": [{"role": "question"|"answer", "start", "end", "name", "position", "affiliation"}]}`. `spans`의 위치는 청크 `text` 안의 문자 위치이고, `head`면 `spans`가 없다
   - 머리 줄의 화자는 corpus의 `questioners`·`answerers`(S10, D-20 정규화)다. 겹침 구간의 화자는 그 발언이 나온 QA 라벨의 화자를 같은 정규화(`ingest.speaker`)로 쓴다. 화자가 여럿인 문서(1% 미만)에서도 구간마다 누구의 발언인지 맞게 붙이려는 것이다
   - 발언이 `context`에 여러 번 나오면 모든 위치에 표지를 붙인다(어느 위치인지 라벨에 없다). 그대로 찾아지지 않는 발언(dev 답변 12개)은 표지를 붙이지 않는다. 청크 경계에 걸린 구간은 청크 안 부분만 표시한다. 같은 역할·화자·위치의 구간은 한 번만 둔다
2. 렌더링 문자열(2단계에서 확정해 테스트로 고정): 메타 줄 다음에 `질의자: 홍길동 위원 / 답변자: 김철수 국토교통부 장관`, 겹친 구간은 `〈질의 홍길동 위원〉…〈/질의〉`, `〈답변 김철수 장관〉…〈/답변〉`. 생성 프롬프트(v2)의 `context` 서식은 고치지 않고 `text` 자리에 렌더링한 문자열을 넣는다. 표기를 설명하는 지시를 프롬프트에 더할지는 H20 EXP에서 정한다
3. `speakers.mode`는 `configs/config.yaml`에 기본 `off`로 두고, `off`가 아니면 생성 레시피와 생성·judge 기록 경로(`paths.gen_runs`·`gen_judge`)에 표시한다. `off`면 레시피와 경로가 지금과 같다(S25 기록을 그대로 읽는다)
4. "필드가 없는 기록의 judge 요청 본문 sha가 지금과 같음"은 생성 평가 모듈 리뷰 수정 SLICE(S28)가 만드는 G1-3 고정 테스트 위에 더한다. `build_messages`도 `speakers`가 없으면 지금과 같은 메시지를 내는지 테스트한다
5. judge 입력 코드(`format_contexts`)를 바꾸는 이유와 결정 사항 1·2를 DECISIONS에 새 결정으로 적고, D-56 결정 3 줄 끝에 `보강: D-NN`을 붙인다(`docs/CLAUDE.md`). 번호는 S28이 병합된 뒤 비어 있는 다음 번호다
6. 채움 비율·겹침 비율을 다시 셀 수 있게 `uv run python -m rag.speakers [--gen <생성 기록.jsonl>]`을 둔다. 코퍼스 화자 필드 채움 비율과, 생성 기록을 주면 그 근거 중 겹침 표지가 붙는 근거 수·표지 문자 비율을 출력하고 파일은 쓰지 않는다. dev 질의 발언의 일치 수(위 표)는 dev 질의만 센다

## 순서 (사용자 결정 2026-10-28)

S28이 `src/rag/gen_eval/judge.py`·`src/rag/generate.py`·`tests/test_gen_eval_freeze.py`를 함께 고친다.

1. 지금: 이 지시서, `src/rag/speakers.py`(원천 라벨에서 QA별 화자·발언, 문서 구간, 청크별 `speakers` 필드, 채움·겹침 집계 명령)와 `tests/test_speakers.py`
2. S28 병합 뒤(코디네이터 알림): `origin/main`을 병합하고 렌더링(`format_contexts`, `build_messages`), `Pipeline.retrieve`의 필드 생성, `speakers.mode` config·레시피·경로, sha 고정 테스트, DECISIONS를 더한다

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | `tests/test_speakers.py` | 합성 문서로 구간 계산(여러 위치, 찾지 못한 발언, 청크 경계 자르기, 화자 여럿, 중복 제거)이 기대값과 같다 |
| 3 | `uv run python -m rag.speakers` | 위 "배경 수치" 표의 채움 비율·문서 수와 같다. 두 번 실행하면 같은 출력 |
| 4 | `uv run python -m rag.speakers --gen <S25 gen-full 생성 기록>` | 330질의 근거의 표지 붙는 근거 수와 표지 문자 비율이 나온다(결과 절에 적음). `data/` 아래 파일이 바뀌지 않는다 |
| 5 | sha 고정 테스트(2단계) | `speakers`가 없는 기록의 judge 요청 본문 sha와 생성 메시지가 S28 고정값과 같다. `speakers`가 있으면 렌더링 문자열이 메인이 정한 것 2의 형식이다 |
| 6 | 기본 설정 `rag.gen_eval.generate +exp=exp017`의 레시피·경로(호출 없이 함수로 확인) | S25 생성 기록의 레시피·경로와 같다. `speakers.mode=marks`면 경로·레시피가 다르다 |

## 수정 허용 파일

`src/rag/speakers.py`(새 파일), `tests/test_speakers.py`(새 파일), 2단계에서 `src/rag/gen_eval/judge.py`(`format_contexts`), `src/rag/generate.py`(`build_messages`, `Pipeline.retrieve`, `recipe`), `src/rag/gen_eval/generate.py`(레시피 표시가 필요하면), `tests/test_gen_eval_freeze.py`·`tests/test_gen_eval.py`·`tests/test_generate.py`(고정·렌더링 테스트), `configs/config.yaml`(`speakers.mode`, `paths.gen_runs`·`gen_judge`의 표시), `CLAUDE.md`(명령 한 줄), `docs/DECISIONS.md`, `docs/PLAN.md`·`docs/PLAN-done.md`, 이 문서

## 범위 밖

- 검색 텍스트(임베딩)에 발언자를 넣는 것, 재임베딩(D-56 근거)
- judge 지시·판정표·기본 judge 설정(D-49 동결), 보호 경로(`src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`, `data/splits/`, `multidoc.eval`, G3 동결 설정)
- 생성 프롬프트 변경, H20 EXP 실행·판정, `data/processed/` 등 기존 산출물 변경
