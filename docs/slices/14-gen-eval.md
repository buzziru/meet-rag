# S14 생성 평가 모듈

생성 단계 평가에 쓸 도구를 만든다. 생성 경로를 D-37(OpenRouter, 제공자 고정, 사고 과정 끔)로 바꾸고 검색 기준 EXP-017의 리랭커를 연결한다. 그 위에 judge 호출(D-38), 코드 판정, 레시피 기록을 더한다. 기준은 SPEC 개정 초안 `docs/drafts/spec-generation-eval.md`(이하 초안)이다. dev-small 소표본으로 동작을 확인하고 토큰 수, 비용, 첫 토큰 지연을 잰다.

점수로 무엇을 정하는 조각은 아니다. 핵심 답변 포함도의 위치(초안 결정 사항 1), 종합 지표(2), 최소 개선 폭(3), judge 보정 기준(4)은 PLAN "생성 평가" 절의 다음 항목에서 이 도구로 정한다.

## 만드는 것

### 생성 경로

- `configs/generator/openrouter.yaml`: `google/gemma-4-31b-it`, `api_key_env: OPENROUTER_API`, 제공자 고정(`provider.order: [coreweave/fp4]`, `allow_fallbacks: false`), 사고 과정 끔(`reasoning.effort: none`), `temperature` 0, `context_docs` 5. 기본 generator를 이 파일로 바꾼다(D-37). `gemma.yaml`(Google 경로)은 지우지 않는다
- `rag.generate`: OpenRouter 요청 본문에 제공자·사고 과정 설정을 넣는다. 응답의 실제 제공자(`provider`)를 기록에 남겨 고정이 지켜졌는지 확인한다. 스트리밍에서 답변 첫 토큰까지의 시간을 잰다
- 리랭커 연결: EXP-017과 같이 RRF 후보(필터 전) 상위 `rerank.depth`개를 재정렬 점수로 다시 줄 세운 뒤 최다 일치 필터를 적용한다. 순서 규칙(`rag.search`의 `rerank_top` → `conditions_first`)을 `rag.retrieve`로 옮겨 평가와 생성이 같은 코드를 쓴다(S12 원칙). 점수 출처는 결정 사항 1
- 프롬프트는 `configs/prompt/v1.yaml`을 그대로 쓴다. 바꾸면 H10에서 새 버전으로 만든다

### 일괄 생성

- `uv run python -m rag.gen_eval.generate +exp=exp017 gen_eval.queries=dev-small gen_eval.n=<N>`: dev 질의를 qid 순서 고정 표본으로 골라 생성하고, 질의마다 한 줄씩 jsonl로 쓴다(`paths.gen_runs`). 한 줄에 qid, 근거(문서·청크·점수), 답변, usage, 제공자, 첫 토큰 시간, 레시피가 들어간다
- 표본은 `gen_eval.seed`로 dev-small에서 뽑는다. `n`을 늘려도 앞 표본이 유지되게 섞은 순서의 앞에서 자른다
- test 질의는 받지 않는다. 질의는 `paths.queries_dev`에서만 읽는다
- 같은 경로에 내용이 다른 파일이 있으면 멈춘다(`write_guarded`). 중단 뒤 다시 실행하면 이미 쓴 qid는 건너뛴다

### 참조 답변

- `answer.comment`는 지금 처리 데이터(`queries_summary_q.dev.jsonl`의 `qid`, `query`)에 없다. 원천 라벨에서 dev 질의의 `answer.comment`만 뽑아 `paths.gen_refs`에 쓴다. test 질의의 값은 파일에 쓰지 않는다
- 이 파일은 핵심 답변 포함도에만 쓰고, 생성 프롬프트에는 넣지 않는다

### 코드 판정

LLM 없이 처리한다(초안 "코드로 판정하는 항목").

- 인용 번호 유효성: 답변의 `[n]`이 1\~`context_docs` 안에 있는지, 인용 없는 진술 문장이 있는지
- 거부: 답변이 프롬프트의 거부 문구("제공된 회의록에서 답을 찾지 못했습니다")를 담는지
- 메타데이터 일치: 답변에 나온 회의 일자·위원회 이름을 인용한 문서의 `date`·`committee_name`과 대조한다(결정 사항 3)
- 정답 문서 포함: 정답 문서가 근거 5개에 있는지(라벨 doc_id 대조). 없으면 핵심 답변 포함도 계산에서 뺀다(초안). 판단은 코드가 하고, 생성 모델은 어느 근거가 정답 문서인지 모른다
- 거부 교차 집계: 거부 여부를 정답 문서 포함 여부로 나눠 센다. 정답 문서가 근거에 있는데 거부한 비율은 잘못된 거부(초안 거부 정확도의 "답이 있는 근거에서 거부하지 않는가")이고, 정답 문서가 없을 때 거부한 비율은 검색 실패에서 지어내지 않고 멈췄는지 보는 참고값이다. 후자는 정답 문서 밖에도 답을 담은 문서가 있을 수 있어(D-34 "다른 정답") 판정에 쓰지 않는다. 정답 문서가 들어갔어도 그 근거 청크가 `answer.comment`를 담지 않았으면 따로 센다(결정 사항 5)

### judge

- `configs/judge/deepseek_go.yaml`: DeepSeek V4.1 Flash, opencode Go 경로(D-38). 엔드포인트 `https://opencode.ai/inference/go/openai/v1`(Chat Completions), 모델 `deepseek-v4.1-flash`, 키 `OPENCODE_API_KEY`. Console 종량제 경로(`/inference/openai/v1`)는 구독이 아니라 잔액에서 차감해 쓰지 않는다. Go 문서(https://opencode.ai/docs/go/, 2026-10-19)에 따라 요청마다 자체 User-Agent(`meet-rag-judge/<버전>`)와 실행마다 고정한 `x-opencode-session`을 보낸다. 워크스페이스 Privacy에서 Global 지역을 켜야 이 모델을 부를 수 있다(사용자 설정 2026-10-19). 기본 응답에 사고 과정 토큰이 있어(더미 호출 28토큰) 켜고 끄는 값을 config에 둔다. 대안 경로 `configs/judge/deepseek_openrouter.yaml`(`deepseek/deepseek-v4.1-flash`)도 둔다. `temperature` 0
- 기준별 프롬프트는 `configs/judge/prompt/`에 버전 파일로 둔다. 출력은 JSON으로 받고 형식이 틀리면 그 항목을 실패로 기록한다(다시 묻지 않는다). 프롬프트를 쓰는 방법은 아래 "judge 프롬프트: RAGAS 차용과 한국어 회의록 수정"
  - 충실성: RAGAS 논문과 같이 두 번 부른다. (1) 답변을 진술로 나누고 (2) 진술마다 근거로 뒷받침되는지 판정한다. 점수는 뒷받침된 진술 수 / 전체 진술 수
  - 답변 관련성: judge가 답변이 질의에 답하는지를 3단계(답함 1, 일부 0.5, 답하지 않음 0)로 매긴다(결정 사항 2). 논문의 역질문 생성과 임베딩 유사도는 쓰지 않는다
  - 핵심 답변 포함도: (1) `answer.comment`에서 질의에 답하는 핵심 진술을 뽑고 (2) 진술마다 답변에 있는지 판정한다. (1)은 답변과 무관하므로 qid와 judge 레시피별로 한 번만 부르고 결과를 저장해 실험 사이에 같은 핵심 진술을 쓴다. 핵심 진술이 없으면 참조 사용 불가로 기록한다
- 거부 답변은 judge에 보내지 않는다(초안 "거부 답변의 처리")
- `uv run python -m rag.gen_eval.judge --run <생성 jsonl>`: 생성 기록을 읽어 judge 결과를 `paths.gen_judge`에 쓴다. 요청 본문 해시로 응답을 저장해 다시 실행할 때 쓴다(`rag.rerank` jev 방식). 동시 요청 수는 config로 둔다
- 호출은 LangSmith로 추적한다(`wrap_openai`, 메타데이터에 qid·기준·레시피). 레시피는 judge 제공자·모델·파라미터·프롬프트 SHA-256과 생성 레시피의 해시다

### judge 프롬프트: RAGAS 차용과 한국어 회의록 수정

D-38은 RAGAS 지표 정의를 빌려 직접 구현하고 ragas 라이브러리는 쓰지 않기로 했다. 이유는 judge 프롬프트를 버전 관리하고 한국어 회의록에 맞춘 지시를 쓰기 위해서다(PR #99 코멘트 "ragas 개선을 통한 judge-as-llm"). 프롬프트는 다음 순서로 만든다.

1. 출발점: RAGAS 논문(arXiv:2309.15217)의 충실성 프롬프트 두 개(진술 추출, 진술별 근거 판정)의 단계 구조를 그대로 따른다. 진술마다 짧은 판정 이유를 먼저 쓰고 판정을 뒤에 두는 순서도 같다. 답변 관련성과 핵심 답변 포함도는 논문에 해당 프롬프트가 없거나(포함도) 계산 방식을 바꿨으므로(관련성) 같은 구조로 새로 쓴다
2. 한국어로 쓴다: 지시문과 예시를 한국어로 쓰고, 예시는 지어낸 회의록 문단으로 만든다(AI Hub 데이터를 넣지 않는다). JSON 키는 영어로 고정해 파싱을 단순하게 둔다
3. 한국어 회의록에 맞춰 더하는 지시
   - 진술 단위: 연결어미로 이어진 긴 문장("~했고, ~하며, ~라는 점에서")은 주장마다 나눈다. 인용 번호 `[n]`, 호칭("○○ 위원님"), 인사·맺음말은 진술에서 뺀다
   - 발언 귀속: 회의록 답변은 "누가 무엇을 말했는가"가 내용의 일부다. 근거에서 장관이 한 말을 위원이 한 말로 옮기면 내용이 맞아도 뒷받침되지 않는 진술로 판정한다
   - 표기 차이: 숫자·금액·날짜의 표기만 다른 것(1조 2천억 원과 1.2조 원, 2020. 3. 5.와 3월 5일)은 같은 내용으로 본다
   - 답을 피한 발언: "검토하겠습니다", "살펴보겠습니다" 같은 발언을 답변이 그대로 옮기면 그 자체로 진술이다. 충실성은 근거에 있으면 뒷받침으로 보고, 답변 관련성은 질의의 답이 아니므로 "일부"나 "답하지 않음"으로 본다
4. 검증: 프롬프트 문구는 이 조각의 PR에서 사용자가 읽고, 기준별 타당성은 G5 사람 채점과의 일치율·kappa로 확인한다(초안 결정 사항 4). 문구를 고치면 새 버전 파일을 만든다

### 집계

- `uv run python -m rag.gen_eval.report --judge <judge jsonl>`: 기준별 평균과 계산한 질의 수, 뺀 질의 수(이유별), 거부율과 거부 교차 집계(정답 문서 포함 여부별 거부율), 인용·메타데이터 오류율, 토큰·비용 합계, 첫 토큰 시간 중앙값·최대를 표로 낸다
- 종합 지표, 기준과의 paired bootstrap 비교, 채택 판정은 만들지 않는다(초안 결정 사항 2·3이 정해진 뒤)

## 결정 사항

모두 정했다(사용자 결정 2026-10-19).

1. 리랭커 점수 출처: 평가 실행은 EXP-017에서 Colab으로 만든 재정렬 점수 파일(`paths.rerank_scores`, dev-full·dev-small)을 읽는다. 자유 질의(`ask.query`)에 리랭커가 켜져 있으면 멈추고, 실시간 재정렬은 배포 SLICE에서 GPU 추론 서버와 함께 만든다. 평가에는 점수 파일로 충분하고 검색 평가 순위와 같은 결과가 보장된다. 로컬 CPU 재정렬은 배포 경로(D-36)와 달라 만들지 않는다
2. 답변 관련성 계산: judge가 3단계(답함 1, 일부 0.5, 답하지 않음 0)로 직접 매긴다. RAGAS 논문 방식(역질문 생성과 임베딩 유사도)은 연속값이라 G5 보정의 kappa에 맞지 않는다
3. 메타데이터 일치 대조 범위: 회의 일자와 위원회 이름을 인용한 문서의 `date`·`committee_name`과 대조한다. 발언자 이름은 대조하지 않는다. 화자 필드는 라벨링된 QA의 화자만 담아 같은 구간의 다른 발언자가 빠지므로(D-19 한계) 맞는 이름을 불일치로 셀 수 있다
4. 완료 확인 규모: dev-small 고정 표본 20질의. 생성 20호출(약 $0.01, D-37 호출당 추정)과 judge 약 100호출(질의당 충실성 2, 관련성 1, 포함도 2. opencode Go 구독이라 추가 과금 없음)이다. dev-small 전체(1,039질의)는 PLAN 다음 항목(핵심 답변 포함도 관찰)에서 호출 수·비용을 보고하고 승인받아 돌린다
5. 거부 교차 집계의 "근거에 답이 있음" 기준: doc_id 대조에 더해 정답 문서의 근거 청크가 `answer.comment`를 담는지 대조해 "정답 문서는 들어갔지만 답이 담긴 청크가 아님"을 따로 센다. 추가 호출 없는 코드 대조로 잘못된 거부와 맞는 거부를 가른다. 근거는 문서마다 dense 최고점 청크 하나라(D-05) 정답 문서가 들어가도 답이 빠질 수 있고, 그때의 거부는 맞는 판단이다. `answer.comment`는 거의 모두 정답 문서 본문에 그대로 있다(`docs/data.md` §7, 39,633건 중 39,467건). 청크 경계에 걸친 경우 얼마나 겹치면 담은 것으로 볼지는 구현 때 dev-small 표본으로 정해 이 문서에 적는다

## 완료 기준

- `uv run pytest -q`, `uv run ruff check .` 통과
- 테스트: 코드 판정(인용 번호, 거부 문구, 메타데이터 일치, 근거 청크의 `answer.comment` 포함과 거부 교차 집계), judge 응답 파싱(정상, 형식 오류), 표본 선택(`n`을 늘려도 앞 표본 유지), 재정렬 순서(합성 입력에서 `rag.search`와 같은 순서), 생성 기록 덮어쓰기 방지와 이어 쓰기
- `rag.generate +exp=exp017 ask.qid=<dev qid>`의 근거 문서 5개가 `rag.search +exp=exp017 index.scope=full` 순위 파일의 같은 qid 상위 5개와 같은 순서다(dev-small 표본 20질의 모두)
- `rag.gen_eval.generate`(n=20) 기록의 제공자가 모두 CoreWeave이고 사고 과정 토큰이 0이다
- `rag.gen_eval.judge`를 같은 입력으로 두 번 실행하면 두 번째는 API를 부르지 않고 같은 결과를 낸다(저장된 응답 사용)
- `rag.gen_eval.report`가 위 집계 표를 낸다. 결과(토큰, 비용, 첫 토큰 시간 중앙값, 기준별 평균, 뺀 질의 수)를 이 문서 결과 절에 적는다. 점수 수준은 완료 기준이 아니다

## 수정 허용 파일

- `src/rag/generate.py`, `src/rag/retrieve.py`, `src/rag/search.py`(재정렬 순서 규칙을 `rag.retrieve`로 옮기는 부분만), 새 `src/rag/gen_eval/`
- `configs/config.yaml`(기본 generator, `paths.gen_runs`·`gen_refs`·`gen_judge`, `gen_eval` 절), 새 `configs/generator/openrouter.yaml`, 새 `configs/judge/`
- `tests/`의 해당 테스트
- `docs/slices/14-gen-eval.md`, `docs/slices/06-generate.md`(경로 서술), `CLAUDE.md` "명령" 절, `docs/PLAN.md`(S14 줄), `docs/DECISIONS.md`(결정 사항 1\~3 기록)

## 범위 밖

- multi-doc 질의의 생성 평가(초안 보조 관찰). 참조 답변을 정하는 초안 결정 사항 1과 함께 한다
- 오라클 진단과 거부 정확도 세트(PLAN 다음 항목)
- 종합 지표, 기준 비교·판정, SPEC 개정
- 실시간 재정렬과 배포
- 프롬프트 변경(H10)
- `src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`(보호 경로)
