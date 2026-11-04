# S38 Space 배포

S35·S36의 로컬 앱을 비공개 HF Space에 올린다. 재정렬을 끈 구성은 그대로이고(실시간 재정렬은 S39), 공개는 하지 않는다(S41). 호스팅은 ZeroGPU를 먼저 본다. 무료 계정에서 CPU Basic은 닫혀 있다(사용자 확인 2026-11-04, HF 문서: Gradio Space의 `cpu-basic`은 구독이 필요하고 없으면 402).

조사한 사실(2026-11-04, HF 문서와 `hf` 2.4.0 도움말):

- ZeroGPU는 Gradio SDK만 쓰고, Python 3.12.12·3.10.13, PyTorch 2.8 이상을 지원한다. 잠금 파일의 torch 2.13.0, gradio 6.31.0, 저장소의 Python 3.12와 맞는다
- 무료 개인 계정은 ZeroGPU Space를 2개까지 만들 수 있다(이메일 인증, 가입 30일 이상)
- 문서에 없는 것: ZeroGPU의 CPU 메모리와 디스크 크기, 비공개 가능 여부, `@spaces.GPU` 함수 없이 시작할 수 있는지. 완료 기준 1에서 잰다
- Dataset 저장소를 읽기 전용 볼륨으로 붙일 수 있고 비공개 저장소도 된다. 볼륨 형식은 `hf://[TYPE/]SOURCE:/MOUNT_PATH[:ro]`이고 revision을 적는 칸이 문서와 도움말에 없다
- Space 디스크는 재시작하면 지워진다. 시크릿은 `--secrets NAME`으로 값을 환경 변수에서 읽어 넣을 수 있다

## 만드는 것

- **사전 확인**: 데이터 없는 최소 앱을 비공개 ZeroGPU Space(`ingyoun/meet-rag`)에 올려 로그로 메모리, 디스크, CPU 수를 읽는다. Space 칸을 아끼려고 확인용 Space를 따로 만들지 않고 이 Space를 그대로 앱에 쓴다
- **처리처 기록**: 데이터를 올리기 전에 DECISIONS에 HF를 기록하고 `CLAUDE.md` 허용 처리처 목록에 더한다(D-72 절차)
- **발언 구간 파일**: `speakers.mode=marks`는 시작할 때 원천 라벨 zip에서 발언 구간을 만든다(`src/rag/generate.py:140`, `doc_spans`). 라벨에는 test 질의를 포함한 `summary_q`가 들어 있어 올리지 않는다. test 질의는 단계 종료 1회 외에 보내지 않는다(`CLAUDE.md` 금지 절). 대신 `doc_spans` 결과(문서 번호, 역할, 시작·끝 위치, 화자)만 파일로 내보내 올리고, 파일 경로를 config로 주면 Pipeline이 라벨 대신 이 파일을 읽는다. 값이 없으면 지금처럼 라벨을 읽어 평가·실험 경로는 바뀌지 않는다
- **비공개 Dataset 저장소**(`ingyoun/meet-rag-data`): 비공개로 먼저 만들어 확인한 뒤 아래 파일만 올린다. 앱이 시작해 검색할 때 여는 파일을 기록해 정했다(2026-11-04 실행, 라벨 zip을 빼면 아래 표와 같고 질의 파일은 열지 않는다). 합쳐서 약 1.8GB에 구간 파일이 더해진다

| 경로(`data/` 아래) | 크기 |
| --- | --- |
| `processed/corpus_context.jsonl` | 약 275MB |
| `index/snowflake-ko-fixed-512-64/full/`의 `basis.json`, `chunks.jsonl`, `emb/`, `bm25-kiwi-v1/` | 약 635MB |
| `index/snowflake-ko-fixed-256-32/full/`의 `basis.json`, `chunks.jsonl`, `emb/` | 약 906MB |
| `processed/speaker_spans.json`, `processed/speaker_spans.json.basis.json` | 약 10MB |

- **Space 저장소**: `deploy/space/`에 진입점 `app.py`, Space 카드 `README.md`, `requirements.txt`를 두고, `src/`, `configs/`와 함께 올린다. 데이터 파일은 넣지 않는다(D-74). 진입점은 `rag.app`과 같은 구성(`+exp=current`, `retriever.rerank.enabled=false`)으로 시작하고, 시작 시간과 최고 메모리를 로그에 남긴다
- **시크릿과 추적**: 생성 API 키와 LangSmith 값을 `doppler run -- hf …`와 `--secrets NAME`으로 넣어 값을 명령에 적지 않는다. 비공개 볼륨에 토큰이 따로 필요하면 Dataset 읽기 토큰도 같게 넣는다(문서에 적혀 있지 않아 완료 기준 1에서 본다). `LANGSMITH_TRACING=true`는 Space 변수로 둔다(D-71)
- **설정**: 저장소 이름과 볼륨 위치는 `configs/config.yaml`의 `deploy` 키에, 구간 파일 경로는 `paths`에 둔다. 코드에 직접 쓰지 않는다
- **결정 기록**: 잰 값으로 호스팅과 벡터스토어(전수 검색 유지 여부)를 정해 DECISIONS에 적고, `docs/SPEC.md` 자원 제약의 "HF Spaces 무료 CPU"를 고친다

## 결정 사항

1. **HF를 처리처로 더하는 범위**: 코퍼스(test 회의 문서 본문 포함, D-78), 인덱스, 발언 구간 파일을 비공개 Dataset 저장소와 비공개 Space로 보낸다. 라벨(`summary_q`, `summary_a`)과 질의 파일, `queries-*.npz`는 보내지 않는다. 사용자가 Dataset 생성을 허가했으므로(2026-11-04) 이 범위의 확인을 지시서 확인으로 받는다
2. **데이터 불러오기**: Dataset 저장소를 읽기 전용 볼륨으로 붙이고, 앱이 읽는 `data/` 경로에 맞춘다(사용자 결정 2026-11-04). 처음 지시는 커밋 해시를 고정해 시작할 때 내려받는 안이었다. 지금도 콜드 스타트가 약 1분이라 지연을 더 늘리고 싶지 않고, 데이터셋은 프로젝트를 마친 뒤 바뀌지 않아 revision 변화로 문제가 생기지 않는다고 사용자가 판단했다. 볼륨은 revision을 고정할 수 없어, 올린 커밋 해시를 결과 절에 기록만 한다. `basis.json` 대조는 모델·청킹·범위 설정만 보므로 같은 설정으로 파일이 바뀌면 걸리지 않는다. 입력→동작: 저장소에 새 커밋을 올리고 Space가 재시작하면 앱은 오류 없이 새 파일을 읽는다. 그래서 이 저장소에는 S38 업로드 뒤 커밋을 올리지 않고, 올려야 하면 사용자에게 먼저 묻는다
3. **OpenRouter 호출**: 완료 기준 4·5의 지어낸 질의로 약 30번, $0.02 이하로 본다(호출당 약 $0.0004\~0.0006, D-37·S35 추정). Colab과 유료 HF 하드웨어는 쓰지 않는다
4. **사전 확인에서 막힐 때**: 비공개가 안 되거나 메모리가 모자라면(로컬 앱 최고 약 2.8GB, S35) 데이터를 올리기 전에 멈추고, 값과 선택지(구독, 다른 호스팅, 인덱스 축소)를 비용과 함께 보고한다. 메인이 정하지 않는다

## 노트북과 결정의 순서

호스팅과 벡터스토어 결정의 근거는 코퍼스나 점수 분석이 아니라 메모리·시간 실측 몇 개라 노트북을 쓰지 않는다. 이 문서 결과 절에 표로 적어 사용자에게 보이고, 결정을 받은 뒤 DECISIONS와 SPEC을 고친다. 처리처 기록은 그와 별개로 데이터를 올리기 전에 한다.

## 완료 기준

순서대로 한다. 앞 기준을 통과하기 전에 다음으로 가지 않는다. 확인 질의는 지어낸 것만 쓰고 dev·test·multi-doc 질의를 쓰지 않는다. 화면 확인은 meet-rag "화면 검증" 절을 따르고 대상 주소는 이 Space 하나다.

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `hf repos create ingyoun/meet-rag --type space --sdk gradio --flavor zero-a10g --private`, `hf repos create ingyoun/meet-rag-data --type dataset --private`, 최소 앱을 올리고 `hf spaces info`, `hf spaces logs` | 비공개로 만들어지고 ZeroGPU로 돈다. 메모리 한도, 디스크 여유, CPU 수, Python·torch 버전, `@spaces.GPU` 함수가 필요한지를 값으로 보고한다. 비공개 Dataset 저장소를 만들어 데이터가 아닌 시험 파일 하나만 두고, ZeroGPU Space에 볼륨으로 붙여 읽히는지와 토큰이 필요한지를 본다. 여기서 사용자에게 보고하고 결정 사항 4에 해당하는지 받는다 |
| 2 | 구간 파일 테스트(`tests/`) | 합성 라벨에서 (a) 파일을 거친 구간이 `doc_spans` 결과와 같다 (b) 파일에 발언 원문과 `summary_q`, `summary_a` 값이 없다 (c) 경로가 없으면 지금처럼 라벨을 읽는다. 실제 라벨로 만든 구간 파일도 로컬에서 문서 38,516개 모두 `doc_spans` 결과와 같다(구간이 빈 문서 포함) |
| 3 | 위 표의 파일을 `hf upload`(시험 파일은 지운다), 저장소 정보와 파일 목록 조회 | 올리기 전과 후에 비공개다. 목록에 표 밖 파일, `queries`, `LAB_`이 없다. 마지막 커밋 해시를 결과 절에 적는다 |
| 4 | Space에 앱을 올리고 Space 주소에서 확인 | 지어낸 질의에 답변이 나눠 나오고 근거 5개가 붙는다. 같은 지어낸 질의 3개의 근거 문서 5개와 근거·문서 화면의 발언자 표시가 로컬 앱과 같다. 읽기 전용 볼륨에 쓰려다 나는 오류가 없다. 문서 탭과 근거 탭이 S36대로 동작한다. 공개 API 목록이 비어 있고, 다운로드 버튼이 없고, 화면에 `splits`, `n_qa`, `summary_`가 없다. LangSmith에 호출이 남는다 |
| 5 | Space 로그와 지어낸 질의 20개 | 최고 메모리, 콜드 스타트(재시작부터 첫 응답까지, 볼륨에서 인덱스 읽기와 임베딩 모델 받기를 나눠서), 첫 질의와 이후 질의의 첫 토큰 시간(중앙값, 최대)을 결과 절에 적는다. 3초 판정은 S41에서 한다 |
| 6 | 사용자가 Space를 화면에서 확인 | 채팅, 문서 탭, 근거 탭을 쓸 수 있다. 호스팅과 벡터스토어 결정을 받는다 |
| 7 | `uv run pytest -q`, `uv run ruff check .` | 통과 |

## 수정 허용 파일

`deploy/space/`, `src/rag/generate.py`, `src/rag/speakers.py`, `configs/config.yaml`(`deploy`, `paths`, `speakers` 키), `tests/`의 구간 파일 테스트, `CLAUDE.md`(허용 처리처 줄, 명령 한 줄), `docs/SPEC.md`(자원 제약, 결정 표시), `docs/DECISIONS.md`, 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/slices/35-chat-app.md`, `docs/slices/36-doc-browser.md`(조각 번호 표시)

## 범위 밖

- 실시간 재정렬과 추론 서버(S39). ZeroGPU에서 재정렬이 도는지와 방문자별 일일 할당량(무료 계정 5분, 비로그인 2분)도 S39에서 본다
- 대화 이어 가기(S40)
- 추천 질의, 첫 구동 안내, 데모 키 크레딧 한도, 3초 판정, Space와 앱의 공개(S41). 이 조각에서는 지금 생성 API 키를 비공개 Space에 넣는다
- 디자인, 답변 형식
- Dataset 저장소의 공개. 공개로 바꾸려면 다시 묻는다
