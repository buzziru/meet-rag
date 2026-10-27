# 생성 EXP 실행 절차

B 흐름에서 EXP 문서 판정 기준이 SPEC "생성 단계 평가 > 판정"(D-53)인 실험(H10, H18 등)에 쓴다. B의 각 단계는 그대로 하고, 아래는 생성 EXP에서 달라지거나 더해지는 것이다. 명령 호출법은 `CLAUDE.md` "명령"의 생성 평가 줄, 경로·옵션은 `docs/slices/14-gen-eval.md`·`docs/slices/24-variance.md`·`docs/slices/27-gen-compare.md`에 있다.

## B1 초안

- 판정 기준에 SPEC "생성 단계 평가 > 판정" 절을 그대로 옮긴다. 기준값은 `configs/eval/gen_v1.yaml`이다(D-55). 판정 세트는 gen-full(판정용 330질의, D-50)이고 gen-small(S14 표본 20질의)은 작동 확인용이다(D-53 결정 8·9)
- 기준 실험은 기준 설정의 gen-full judge 결과다. 지금은 S25 베이스라인(`data/gen_eval/judge/…-j_v8-n330.jsonl`, D-51)이다
- 근거를 바꾸는 실험이면 핵심 답변 포함도를 판정과 함께 보고한다고 적는다(D-53 결정 1). multi-doc 보조 관찰을 볼지와 건수는 여러 문서를 합쳐 답하는 것을 겨냥한 실험에서만 이때 정한다(D-53 결정 7)
- judge 설정(지시 `j_v8`, 실행 설정 `deepseek_go_mixed`)은 동결이라 "바꾸는 것"에 넣지 않는다(D-49·D-50). 기준과 후보는 같은 judge로 채점해야 비교할 수 있고, 다르면 `rag.gen_eval.compare`가 멈춘다

## B2 승인: 예상 비용·시간

생성(OpenRouter)과 judge(opencode Go)는 유료 호출이라 gen-small 작동 확인과 gen-full 실행을 함께 묶어 호출 수·비용·시간을 보고하고 승인받는다. 보내는 데이터는 dev 질의와 근거다(D-31). 예상은 가장 가까운 실측에서 질의 수 비율로 낸다.

- 생성: S25에서 새로 생성한 330질의가 약 $0.08이었다(D-37 CoreWeave 요금)
- judge: 질의당 호출 약 7\~8회. S25 새 230질의 1,731회가 비피크 약 $1.34였으므로 330질의를 모두 새로 채점하면 비피크 약 $1.9, 피크는 그 2배쯤이다. 생성만 바뀌는 실험은 답변과 무관한 단계(`key_statements`, `chunk_checks`, `items`)가 기준 실행의 저장 응답을 써서 새 호출이 줄어든다. opencode Go는 월 사용 한도에서 차감되므로 한도 대비 비율도 적는다
- 시간: 330질의 judge가 검색이 바뀌는 실험 약 45분, 생성만 바뀌는 실험 약 27분(D-50 어림, 질의 동시 4 기준). 질의 동시 8에서는 새 230질의가 15분 22초였다(D-51)

## B3 실행

`rag.*`는 `doppler run -- uv run python -m …`로 부르고, 대량 실행이라 `LANGSMITH_TRACING=false`를 붙인다(D-50).

1. gen-small 작동 확인: `rag.gen_eval.generate +exp=expNNN gen_eval.queries=dev-small gen_eval.n=20` → `rag.gen_eval.judge`(같은 override) → `rag.gen_eval.report`(같은 override). 생성·judge 오류가 없는지, 바꾼 설정이 생성 기록에 들어갔는지(프롬프트 버전, 근거), report의 judge 형식 오류·끝나지 않은 응답 수를 본다. 실행 오류나 설정 누락이 있으면 gen-full로 넘어가지 않고 고친 뒤 같은 확인을 다시 한다. judge 형식 오류는 JSON이 아니어도 정상 종료된 응답이 저장되어 다시 돌려도 같으므로 다시 확인하지 않고 아래 "형식 오류율"대로 기록한다. 점수는 판정에 쓰지 않는다
2. gen-full: `rag.gen_eval.generate +exp=expNNN` → `rag.gen_eval.judge +exp=expNNN` → `rag.gen_eval.report +exp=expNNN`(기본이 gen-full 330질의)
3. 비교: `rag.gen_eval.compare --base <기준 judge.jsonl> --cand <후보 judge.jsonl> --out <EXP 문서 실행 절에 적은 경로>`

### judge 레시피와 저장 응답

- judge 저장 응답(`paths.gen_judge_cache`, 요청 본문 해시가 키)은 지우지 않는다. 같은 요청을 다시 부르지 않아 비용이 줄고, 기준과 후보가 답변과 무관한 단계에서 같은 응답을 쓴다. 다시 채점해 잡음을 봐야 하면 캐시를 지우지 않고 `judge.rep`(반복 번호)를 쓴다(S24)
- judge 결과 경로에는 질의 수가 없어, 같은 이름의 파일이 있으면 judge가 시작할 때 멈춘다(`refuse_existing`). 덮어쓰지 않고 경로를 바꿔 쓴다(S25의 `-n330`)
- judge 호출 하나가 실패하면 실행이 결과 파일 없이 멈춘다. 다시 실행하면 저장 응답으로 이어 간다. 5xx는 "오류 처리"의 서버 상태 확인부터 한다

### 지시 버전이 바뀌면

judge 지시는 동결이라(D-49) 바꾸려면 새 버전 파일과 재검증, 사용자 결정이 먼저다. 새 지시로 바꾼 뒤에는 생성 기록은 그대로 두고 기준 실행도 같은 지시로 다시 채점한 다음 비교한다. 지시 버전·해시가 다른 두 결과는 `rag.gen_eval.compare`가 비교하지 않는다.

### 형식 오류율

report의 judge 형식 오류 수와 끝나지 않은 응답 수를 실행마다 EXP 결과 절에 적는다(D-51 결정 4. S25는 새 호출 1,731회 중 형식 오류 3건, 약 0.2%). gen-full 후보의 형식 오류 수가 기준 실행보다 많으면 판정(B4) 전에 사용자에게 알리고 답을 받은 뒤 진행한다. 두 실행 모두 같은 330질의라 건수로 비교한다. report는 질의 기록마다 세어 저장 응답을 다시 쓴 오류도 들어가므로, 새 호출 수로 나눈 비율로 비교하면 기준의 오류가 후보에서 다시 세어진다. 구조화된 응답으로 바꿀지 다시 논의하는 조건이다(D-51 결정 4).

## B4 판정 입력

`exp-judge` 프롬프트에 넣는다: EXP 문서 경로, 기준·후보 judge 결과 파일 경로, 3의 비교 결과 JSON 경로, 기준·후보 각각의 report 명령(override 포함), 실행 명령과 커밋 해시, 같은 330질의의 검색 지표(근거를 바꿨으면 기준·후보 모두). judge는 비교 명령을 직접 다시 돌려 JSON과 대조하고, report에서 참조 사용 불가·거부 교차 집계·형식 오류를 읽는다(`exp-judgment` 6절).
