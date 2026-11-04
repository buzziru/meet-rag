# S35 채팅 앱

배포 첫 조각이다. 지금 자유 질의는 `rag.generate`에서 재정렬 점수 파일이 없으면 멈추고(`src/rag/generate.py:172-174`, D-40 결정 1), 스트리밍은 토큰을 `print`한 뒤 끝에 한 번에 반환한다(`src/rag/generate.py:233-249`). 화면에 토큰을 흘려보낼 경로가 없다. 이 조각은 로컬에서 도는 채팅 앱까지만 만든다.

## 만드는 것

- `src/rag/app.py`: Gradio `Blocks` 채팅 화면. 입력창, 스트리밍 답변, 답변 아래 근거(번호, 회의 정보, 발언자 표시를 붙인 근거 원문, `original` 링크)를 둔다. 실행은 아래 완료 기준 2의 명령이다
- `src/rag/generate.py`: 스트리밍 응답을 토큰 단위로 내보내는 경로를 더한다. 사고 과정은 내보내지 않고(`answer_start`), 기존 `generate()`는 이 경로를 쓰도록 바꾸되 반환 값과 `echo` 출력은 그대로 둔다
- 재정렬을 끈 구성: `retriever.rerank.enabled=false`를 명령으로 준다. 켠 채 앱을 시작하면 시작할 때 원인을 적고 멈춘다(실시간 재정렬은 S38). `rag.generate`의 점수 파일 동작은 바꾸지 않는다
- 멀티턴 대비: 처리 함수는 `(message, history)`를 받고 검색 질의를 만드는 함수 한 곳(`search_query(message, history)`)을 거친다. 지금은 `message`만 돌려준다. 멀티턴은 이 함수에 재작성을 넣고 프롬프트에 이력을 더하는 것으로 넓힌다. 화면에는 앞 질문이 이어지지 않는다는 안내를 한 줄 둔다
- 설정: 제목, 안내 문구, 동시 처리 수를 `configs/config.yaml`의 `app` 키에 둔다. 코드에 직접 쓰지 않는다
- 의존성: `pyproject.toml`의 선택 의존성 `app`에 `gradio`를 더하고 `uv.lock`을 갱신한다. 평가·실험 환경에는 설치하지 않는다
- 테스트: `tests/test_app.py`. API를 부르지 않고 합성 응답과 합성 `Pipeline`을 쓴다
- 문서: 결정 기록(결정 사항 3), `CLAUDE.md` 명령 한 줄, D-40 결정 1에 표시

앱은 방문자 질의를 `data/`에 저장하지 않는다. `rag.generate`의 `save`를 부르지 않는다. 추적은 LangSmith로 남는다(D-71).

## 결정 사항

1. 화면 도구: Gradio. 무료 계정의 새 Space에서 서버 코드를 돌릴 수 있는 SDK가 Gradio뿐이고(사용자 확인 2026-11-04), static은 서버 코드가 없고 secret이 브라우저로 전달되어 검색과 생성을 맡을 수 없다(HF Spaces 문서)
2. 화면 구성: ChatGPT 같은 채팅 화면(사용자 2026-11-04). `gr.ChatInterface` 대신 `Blocks`와 `gr.Chatbot`으로 만든다. S36에서 사이드바를 같은 `Blocks`에 더해야 하기 때문이다
3. 근거·문서 열람: 내용 열람은 막지 않고 다운로드는 허용하지 않는다(사용자 결정 2026-11-04). D-31의 "외부에서 내려받을 수 있게 두기"는 파일 내려받기로 읽고, 앱 화면의 열람은 그 밖이다. D-74로 기록했고 D-31에 `보강`을 붙였다. 감수하는 것: 화면이 호출하는 HTTP 요청은 막을 수 없어 문서를 하나씩 긁어 가는 것은 완전히 차단하지 못한다. 다운로드 버튼을 두지 않고 Gradio 공개 API 표시를 끈다

## 완료 기준

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과 |
| 2 | `LANGSMITH_TRACING=true doppler run -- uv run --extra cpu --extra app python -m rag.app +exp=current retriever.rerank.enabled=false` | 로컬 주소가 뜬다. 지어낸 자유 질의 하나에 답변이 여러 번에 나눠 나오고, 끝나면 근거 5개가 답변 아래에 나온다 |
| 3 | 2와 같은 명령에서 `retriever.rerank.enabled=false`를 뺌 | 인덱스를 다 읽기 전에 재정렬을 끄라는 오류로 멈춘다 |
| 4 | `tests/test_app.py` | 합성 스트림에서 (a) 내보낸 토큰을 이어 붙이면 `generate()`의 `answer`와 같다 (b) 사고 과정 토큰이 나오지 않는다 (c) `history`가 달라도 지금은 검색 질의와 메시지가 같다 |
| 5 | `tests/`의 기존 생성 테스트 | `generate()`의 반환 키와 값이 그대로다 |

확인에 쓰는 질의는 지어낸 것만 쓴다. dev·test 질의를 쓰지 않는다. OpenRouter 호출은 수십 번 이하, $0.05 이하로 본다(호출당 약 $0.0004\~0.0006, D-37 추정, 사용자 승인 2026-11-04). Colab은 쓰지 않는다. 지연은 재지 않는다(S37, S39).

## 수정 허용 파일

`src/rag/app.py`, `src/rag/generate.py`, `configs/config.yaml`(`app` 키), `pyproject.toml`, `uv.lock`, `tests/test_app.py`, `CLAUDE.md`(명령 한 줄, D-74 표시), `docs/SPEC.md`(D-74 표시), `docs/DECISIONS.md`, 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`

## 범위 밖

- 사이드바, 문서 목록, 문서 보기(S36)
- Space 올리기, 인덱스 보관, 시크릿, ZeroGPU(S37)
- 실시간 재정렬, 추론 서버(S38)
- 추천 질의, 첫 구동 안내, 크레딧 한도, 3초 판정, 공개(S39)
- 멀티턴 동작 자체(재작성, 프롬프트 이력, 평가)
- `docs/SPEC.md` 자원 제약의 "HF Spaces 무료 CPU" 수정(S37 결과를 보고 정한다)

## 결과 (2026-11-04)

커밋: 구현 c995476

- 완료 기준 1: `uv run pytest -q` 429 통과(main 병합 뒤, slice-verifier), `uv run ruff check .` 통과
- 완료 기준 2: 앱을 띄워 지어낸 질의 2개를 브라우저가 쓰는 큐 요청(`/gradio_api/queue/join`)으로 보냈다. 첫 질의에서 스트리밍 이벤트가 64번 왔고, 끝난 대화에 근거 5개와 `metadata.title`이 있었다. 앞 대화를 넘긴 둘째 질의도 근거 5개로 끝났다. 공개 API 목록은 비어 있다. OpenRouter 호출은 약 3번이다
- 완료 기준 3: `+exp=current`로 시작하면 "앱에는 실시간 재정렬이 없다"로 인덱스를 읽기 전에 멈춘다
- 완료 기준 4·5: `tests/test_app.py`, `tests/test_generate.py` 통과

### 지시서와 다르게 하거나 더한 것

- 메인은 Chrome 확장이 연결되어 있지 않아 위 큐 요청으로 확인했고, 사용자가 화면에서 스트리밍과 근거 표시를 확인했다(2026-11-04, 첫 글자 전 스피너, 체감 지연 2초 이내, 디자인은 추후). 지연을 잰 값은 아니다
- 동시 처리 수를 1로 뒀다(`app.concurrency`). 검색 단계가 여러 스레드에서 안전한지 재지 않았다. 입력→동작: 방문자 둘이 같이 물으면 뒤 사람은 앞 답변이 끝날 때까지 기다린다
- 빈 답변이면 `app.no_answer` 문구를 보인다
- 수정 허용 파일에 `docs/SPEC.md`와 `CLAUDE.md` 금지 절의 표시를 더했다. 감사에서 두 곳만 읽는 세션이 D-74를 볼 수 없다는 지적이 나왔다. 처음 지시는 SPEC을 바꾸지 않는 것이었다

### 리뷰 반영

- 근거에 화자 정보가 없다: 생성·judge와 같은 `render`를 쓴다(9b278b9)
- 답변이 끝나면 화면이 근거까지 내려가 답변 첫 부분을 볼 수 없다: `autoscroll`을 끄고, 새 질문은 위로 올린다. 입력→동작: 둘째 질문을 보내면 그 질문이 대화 칸 맨 위로 올라가고, 답변이 길어져도 화면은 따라 내려가지 않는다
- 첫 글자 전 대기 표시가 보이지 않는다: 질문 표시(`ask`, 큐 없음)와 답변 생성(`respond`)을 나눠, 첫 조각이 올 때까지 아무것도 내보내지 않는다. Gradio는 첫 응답 전까지만 대기 표시를 낸다

### 관찰

- 첫 시작 한 번이 종료 코드 5로 오류 문구 없이 꺼졌고, 같은 단계를 나눈 실행과 다시 띄운 실행은 정상이었다. 그때 PC의 남은 메모리는 약 900MB였다(메모리 부족은 추정, 재현하지 않음). 앱의 작업 메모리는 약 2.4GB, 최고 약 2.8GB였다(Windows 작업 집합). S37에서 Space 값을 잰다
