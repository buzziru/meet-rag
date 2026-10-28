# S28 생성 평가 모듈 리뷰 수정

코드 리뷰 `docs/reviews/2026-10-gen-eval-review.md`에서 사용자가 고른 항목을 고치고, judge 형식 재요청(D-58)과 생성 호출 대기·재시도(D-57 결정 1)를 구현한다(PLAN 생성 평가 "생성 평가 모듈 리뷰 수정(SLICE)"). 첫 생성 EXP(H24+H19)가 `rag.gen_eval.compare`로 판정하므로 그 앞에 둔다.

흐름: A. 지시서 확인 뒤 구현한다. 유료 호출은 기준 S25 재채점(opencode Go judge, 사용자 승인 2026-10-28, 실행 전 호출 수·시간 보고)뿐이다. gen-small 생성·judge는 결정 사항 4에 따라 따로 승인받는다.

대상: 높음·중간 G2-1, G1-1, G2-2, G2-3, G3-1, G1-3, compare 테스트 G2-7, 낮음 G2-4, G2-6, G3-3, G1-5. 그 밖의 낮음(G1-2, G1-4, G1-6, G2-5, G3-2, G3-4\~G3-7)은 범위 밖이다.

## 확인한 사실 (지시서 작성 중)

S25 기준(`…-deepseek_go_mixed-j_v8-n330.jsonl`)의 judge 형식 오류 3건을 저장 응답으로 확인했다(질의 원문은 열지 않음).

| qid | 단계 | S25 당시 | 지금 캐시의 첫 요청 응답 | 원인 |
| --- | --- | --- | --- | --- |
| 051401-0012 | verdicts | 정상 종료, 저장 응답 | JSON으로 읽힘 | 진술 목록이 입력과 다름(P6 순서·문구) |
| 047672-0008 | key_checks | 정상 종료, 저장 응답 | JSON으로 읽힘 | 판정 목록이 핵심 진술과 다름(P6) |
| 047816-0001 | verdicts | 잘림(`length`, 16,384 토큰), 저장 안 함 | 정상 종료, JSON으로 읽힘 | 뒤 실행(S26 등)이 같은 요청을 다시 물어 저장됨(D-42) |

D-58 결정 1의 문언("JSON으로 읽을 수 없으면")대로면 S25 재채점에서 재요청은 한 번도 일어나지 않는다. 047816-0001은 저장된 첫 요청 응답으로 풀리고, 나머지 2건은 JSON은 읽히므로 재요청 대상이 아니라 형식 오류로 남는다. 결정 사항 1이 이것을 정한다.

## 결정 사항 (구현 전 확인)

사용자 결정(2026-10-28): 1은 (b), 2는 상한 1회, 3은 (a)(앞선 형식 오류를 고치려는 요청이라 직전 응답과 교정 지시를 붙인다), 4는 S25 재채점에서 확인한다. 재채점에 쓸 judge 지시(j_v8, 또는 S29에서 만들 j_v9와 묶어 한 번에)는 아직 정하지 않았다(코디네이터 전달 2026-10-28)

1. 재요청 범위
   - (a) JSON으로 읽을 수 없는 응답만(D-58 결정 1 문언). `Judge.ask` 안에서 끝난다. S25 재채점은 새 재요청 0회, 남는 형식 오류 2건. 재요청이 다른 응답을 받는지는 S25로 관찰할 수 없다(결정 사항 4)
   - (b) 기준 문서 P6의 형식 오류 전체(추천): JSON 아님·잘림에 더해 정해진 값 밖(`label`, `verdict`, `present`, `state`, `handling`), 진술·항목 목록이 입력과 다름. 단계 함수가 검사 함수를 `ask`에 넘기고, 검사를 통과하지 못하면 재요청한다. D-58의 이유(형식 오류 질의가 짝지은 제외로 빠져 판정을 바꿀 수 있음)는 두 종류에 똑같이 걸리고, S25 오류 3건 중 2건이 이 종류다. D-58 결정 1을 넓히므로 DECISIONS에 새 결정을 쓰고 D-58 결정 1에 `이후 변경`을 붙인다. "진술 없음"(빈 목록)은 형식 오류가 아니라 재요청하지 않는다(이슈 #156)
   - 예: `verdicts` 응답이 `{"verdicts": [진술 2개]}`인데 입력 진술이 3개면, (a)는 형식 오류 1건으로 남기고 (b)는 교정 지시를 더해 다시 묻는다
2. 재요청 상한: 2회(추천, 첫 요청 포함 최대 3회) 또는 1회. 재요청 대상은 S25에서 새 호출 약 0.2%라 상한을 2로 둬도 비용 차이는 질의 몇 개의 호출이다. 1회면 교정 지시를 받고도 같은 오류가 나온 경우 바로 형식 오류로 남는다
3. 교정 지시 방식
   - (a) 대화 이어 묻기(추천): 첫 요청의 messages 뒤에 직전 응답(assistant, 내용이 비었으면 생략)과 교정 지시(user)를 붙인다. 두 번째 재요청은 첫 재요청의 응답을 붙인다. judge가 무엇이 틀렸는지 보고 고칠 수 있고, 입력이 달라 temperature 0에서도 같은 응답이 반복될 가능성이 낮다
   - (b) 첫 요청의 user 메시지 끝에 교정 지시를 덧붙인다. 직전 응답을 보이지 않는다. 재요청끼리 요청 본문이 같아 캐시 키에 재요청 번호를 넣어야 하고, temperature 0에서 같은 응답이 올 수 있다
   - 교정 지시 문구 초안(새 파일 `configs/judge/format_retry/fr_v1.yaml`): "앞 응답이 지시한 JSON 형식과 맞지 않는다. 판정은 처음 지시대로 하고, 지시한 형식의 JSON 객체 하나만 다시 출력한다. 진술·항목 목록이 있으면 입력과 같은 순서·같은 문구로 담는다." (결정 사항 1이 (a)면 "JSON으로 읽을 수 없다"로 줄인다)
4. 재요청이 실제로 다른 응답을 받는지 확인할 곳
   - 결정 사항 1이 (b)면 S25 재채점의 재요청 2건(051401-0012, 047672-0008)에서 본다(추천). 승인된 호출 안에서 실제 오류 사례로 확인한다. gen-small은 돌리지 않는다. 20질의에서 형식 오류가 날 확률이 낮아(0.2% × 질의당 7\~8회 × 20 ≈ 0.3건) 재요청이 일어나지 않을 가능성이 크다
   - 결정 사항 1이 (a)면 S25에서는 볼 수 없고, gen-small(20질의, 저장 응답 대부분 재사용)도 위 이유로 재요청이 일어나지 않을 수 있다. 그때는 확인 방법을 다시 상의한다
   - 두 경우 모두 재요청 응답이 직전 응답과 같으면(본문 비교) 사용자와 다시 논의한다(D-58 결정 6의 재검증)

## 메인이 정한 것 (PR에서 확인)

1. 형식 재요청(D-58) 구현
   - 설정: judge 설정에 `format_retry`(교정 지시 파일 버전·문구, 상한)를 Hydra 그룹으로 두고 `deepseek_go.yaml` defaults에서 고른다(`deepseek_openrouter.yaml`도 같게). 판정 기본값 `deepseek_go_mixed`의 파일 값과 지시 j_v8은 그대로다
   - 레시피·비교: `judge_recipe`에 `format_retry_version`·`format_retry_sha256`·`format_retry_limit`을 넣고 compare `JUDGE_KEYS`에 더한다. 재요청 전 S25 결과와 재요청 뒤 결과는 compare가 비교하지 않고 멈춘다(D-58 결정 2)
   - 캐시: 첫 요청의 본문·키는 그대로다(D-58). 재요청은 본문이 달라 키가 따로 생기고, 저장 규칙(빈 응답·끝나지 않은 응답은 저장 안 함, D-42)은 같다. 다시 실행하면 첫 요청과 재요청 모두 저장 응답을 읽어 같은 결과가 나온다
   - 기록: 재요청한 호출의 usage에 재요청 번호(`format_retry`)를 남기고, report의 judge 단계 표에 단계별 재요청 수와 재요청 뒤 남은 형식 오류 수를 낸다
   - 동결: 교정 지시 파일 해시와 상한을 `tests/test_gen_eval_freeze.py`에 더하고, protocol-guard P11 위반 목록에 교정 지시 파일과 상한을 더한다(D-58 결정 6). P11 변경은 하네스 변경이라 ADR을 더한다
   - 문서: `docs/gen-eval-criteria.md` P6, `parse_json` 설명, DECISIONS(D-58 결정 5의 정한 값, 결정 사항 1 (b)면 새 결정), `.claude/skills/meet-rag/references/gen-exp.md`의 기준 결과 경로
2. 기준 S25 재채점(D-58 결정 3): 생성 기록과 judge 설정은 S25와 같고, 결과를 새 경로 `…-deepseek_go_mixed-j_v8-n330-fr_v1.jsonl`(`paths.gen_judge` override)에 쓴다. 기존 파일은 덮어쓰지 않는다. 오류가 아닌 질의는 저장 응답을 읽는다. report로 충실성·관련성·종합 지표·포함도·과잉 거부율과 남은 형식 오류 수를 내고, DECISIONS 머리 줄과 D-51 베이스라인 줄의 표시를 새 경로·값으로 고친다. STATUS의 베이스라인 수치는 핸드오프 때 고친다
3. G2-1: compare에서 기준별 짝지은 질의 수가 0이면 그 기준과 원인(예: `item_eval=false`로 채점해 과잉 거부 값이 없음)을 적고 멈춘다
4. G1-1: 관련성 `label`이 문자열이 아니면 형식 오류로 센다(결정 사항 1 (b)면 재요청 대상)
5. G2-2: 형식 오류인 항목 평가(`error`가 있음)는 S22 이전 기록 판별과 `item_summary`의 항목 표에서 뺀다. 판단 불가 수는 지금처럼 센다
6. G2-3: report가 읽은 judge 결과의 qid를 `eval_qids(cfg)`와 대조한다. 근거가 검색 결과(`gen_eval.contexts=retrieved`)면 집합이 같아야 하고, 오라클·정답 제외 진단은 근거가 같아 생성하지 않은 질의가 빠지므로 부분집합이어야 한다. 어긋나면 질의 수와 경로 override 예를 적고 멈춘다. 예: CLAUDE.md의 `rag.gen_eval.report +exp=exp017`은 기본 경로의 S24 100질의 파일을 읽으므로, 330질의 표본과 달라 멈춘다
7. G1-3: judge 요청 본문 고정 테스트. 고정한 합성 생성 기록·참조로 `judge_record`를 돌리되 API 대신 정해진 응답을 돌려주는 가짜 클라이언트를 쓰고, 단계별 요청 본문(model, messages, params, extra) sha256을 기대값과 대조한다. `RELEVANCE` 기대값(답함 1, 일부 0.5, 답하지 않음 0)도 대조한다. `format_contexts`의 출력은 바꾸지 않는다. H20 SLICE(S29)가 이 테스트 위에 "speakers 필드가 없으면 요청 본문이 같다"를 더한다. 같이 D-49 점검 줄에 `보강`을 붙인다
8. G2-7: compare `main`의 짝지은 제외, 짝지은 질의 0개 멈춤, 형식 오류 질의 제외를 합성 judge 기록으로 테스트한다
9. G2-4: compare 결과에 실행별·기준별 뺀 이유(전체 거부, 참조 사용 불가 등)와 형식 오류 수를 넣는다. report의 `criterion`을 그대로 쓴다
10. G2-6: report 머리 설명을 지금 출력에 맞추고, 과잉 거부율을 D-53 정의(질의 평균, compare와 같은 `per_query`)로 함께 낸다. `per_query`는 report로 옮기고 compare가 가져다 쓴다(compare가 이미 report를 읽는다)
11. G3-1(D-57 결정 1): `configs/generator/openrouter.yaml`·`gemma.yaml`에 `timeout: 120`, `max_retries: 1`을 두고 `Pipeline`의 `OpenAI()`에 넘긴다. 생성 레시피(`recipe`)는 필드를 골라 담아 이 값이 들어가지 않으므로 S25 생성 기록의 레시피와 같다(D-57 결정 3과 같은 이유). DECISIONS D-57 결정 1에 `→ D-…`나 구현 표시를 붙인다
12. G3-3: 생성 응답의 `finish_reason`을 생성 기록에 남기고, report가 `stop`이 아닌 생성 수를 낸다. 옛 기록에는 없어 "기록 없음"으로 센다
13. G1-5: judge 캐시를 임시 파일에 쓴 뒤 `os.replace`로 옮긴다

## 만드는 것

- `configs/judge/format_retry/fr_v1.yaml`(새 파일), `configs/judge/deepseek_go.yaml`·`deepseek_openrouter.yaml`(defaults), `configs/generator/openrouter.yaml`·`gemma.yaml`
- `src/rag/gen_eval/judge.py`, `compare.py`, `report.py`, `src/rag/generate.py`
- `tests/test_gen_eval.py`, `tests/test_gen_eval_freeze.py`, `tests/test_generate*.py`(필요한 것)
- 문서: `docs/gen-eval-criteria.md` P6, `docs/DECISIONS.md`, `.claude/skills/protocol-guard/SKILL.md` P11, `.claude/skills/meet-rag/references/gen-exp.md`, ADR 하나와 목록

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과. 새 테스트: 형식 재요청(첫 응답 깨짐 → 재요청 응답 사용, 상한까지 깨짐 → 형식 오류, 재요청 본문에 교정 지시, 다시 실행하면 저장 응답으로 같은 결과), 요청 본문 sha 고정, compare 짝지은 0개 멈춤, report qid 대조, 생성 `finish_reason` |
| 2 | `rag.gen_eval.compare --base <S25 …-n330.jsonl> --cand <그 복사본>` | 레시피에 형식 재요청 키가 없는 두 파일이라 비교된다(모든 차이 0, 보류). 재채점 파일과 S25 파일을 비교하면 judge 설정이 다르다고 멈춘다 |
| 3 | `rag.gen_eval.report +exp=exp017` | qid 집합이 330질의 표본과 다르다고 멈춘다. `paths.gen_judge=<S25 …-n330.jsonl>`이면 끝까지 나오고 충실성 0.803(314)·관련성 0.871(321)·포함도 0.512(258), 과잉 거부율(질의 평균) 0.024가 S25 기록과 같다 |
| 4 | 기준 S25 재채점(메인 실행, 승인된 유료 호출) `rag.gen_eval.judge +exp=exp017 paths.gen_judge=<…-n330-fr_v1.jsonl>` → report | 새 호출은 형식 오류 질의의 재요청뿐(저장 응답 사용 수가 나머지 전부). 재요청 응답이 직전 응답과 다른지 보고. 같은 명령을 다시 돌리면 API 호출 0회, 같은 결과 |
| 5 | 1의 테스트 중 생성 클라이언트 테스트(API 호출 없음) | `Pipeline`의 `OpenAI()`가 generator 설정의 timeout 120·max_retries 1로 만들어진다 |

slice-verifier는 1\~3, 5를 맡는다(API 호출 없음). 4는 메인이 실행하고 결과를 이 문서 결과 절에 적는다. 임시 파일은 `data/` 밖에 만들고 `data/` 안의 기존 파일은 덮어쓰지 않는다.

## 수정 허용 파일

위 "만드는 것", `CLAUDE.md`(report 명령의 경로 안내가 바뀌면 한 줄), 이 문서, `docs/PLAN.md`·`docs/PLAN-done.md`, `docs/harness/adr/`

## 범위 밖

- 리뷰 낮음 중 고르지 않은 항목(G1-2, G1-4, G1-6, G2-5, G3-2, G3-4\~G3-7)
- judge 지시 j_v8·판정표(D-49 동결), 기본 judge 실행 설정 값(D-50)
- `format_contexts` 출력과 근거 청크 표시: H20 SLICE(S29)가 이 PR 병합 뒤 고친다
- 보호 경로 `src/rag/eval/`, `configs/eval/`(읽기만)
