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

- **Space 저장소**: `deploy/space/`에 진입점 `app.py`, Space 카드 `README.md`, `requirements.txt`를 두고, `src/`, `configs/`와 함께 올린다. 데이터 파일은 넣지 않는다(D-74). 진입점은 `rag.app`과 같은 구성(`+exp=current`, `retriever.rerank.enabled=false`)으로 시작하고, 시작 시간과 최고 메모리를 로그에 남긴다 이후 변경: S39부터 재정렬을 켠 구성으로 시작한다(D-84)
- **시크릿과 추적**: 생성 API 키와 LangSmith 값을 `doppler run -- hf …`와 `--secrets NAME`으로 넣어 값을 명령에 적지 않는다. 비공개 볼륨에 토큰이 따로 필요하면 Dataset 읽기 토큰도 같게 넣는다(문서에 적혀 있지 않아 완료 기준 1에서 본다). `LANGSMITH_TRACING=true`는 Space 변수로 둔다(D-71)
- **설정**: 저장소 이름은 `configs/config.yaml`의 `deploy` 키에, 구간 파일 경로는 `paths`에 둔다. 코드에 직접 쓰지 않는다
- **결정 기록**: 잰 값으로 호스팅과 벡터스토어(전수 검색 유지 여부)를 정해 DECISIONS에 적고, `docs/SPEC.md` 자원 제약의 "HF Spaces 무료 CPU"를 고친다

## 결정 사항

1. **HF를 처리처로 더하는 범위**: 코퍼스(test 회의 문서 본문 포함, D-78), 인덱스, 발언 구간 파일을 비공개 Dataset 저장소와 비공개 Space로 보낸다. 라벨(`summary_q`, `summary_a`)과 질의 파일, `queries-*.npz`는 보내지 않는다. 사용자가 Dataset 생성을 허가했으므로(2026-11-04) 이 범위의 확인을 지시서 확인으로 받는다
2. **데이터 불러오기**: Dataset 저장소를 읽기 전용 볼륨으로 붙이고, 앱이 읽는 `data/` 경로에 맞춘다(사용자 결정 2026-11-04). 처음 지시는 커밋 해시를 고정해 시작할 때 내려받는 안이었다. 지금도 콜드 스타트가 약 1분이라 지연을 더 늘리고 싶지 않고, 데이터셋은 프로젝트를 마친 뒤 바뀌지 않아 revision 변화로 문제가 생기지 않는다고 사용자가 판단했다. 볼륨은 revision을 고정할 수 없어, 올린 커밋 해시를 결과 절에 기록만 한다. `basis.json` 대조는 모델·청킹·범위 설정만 보므로 같은 설정으로 파일이 바뀌면 걸리지 않는다. 입력→동작: 저장소에 새 커밋을 올리고 Space가 재시작하면 앱은 오류 없이 새 파일을 읽는다. 그래서 이 저장소에는 S38 업로드 뒤 커밋을 올리지 않고, 올려야 하면 사용자에게 먼저 묻는다 이후 변경: S39부터 볼륨을 떼고 시작할 때 커밋을 고정해 내려받는다(D-84). 재시작부터 실행까지 54\~58초다
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

`deploy/space/`, `src/rag/app.py`, `src/rag/generate.py`, `src/rag/speakers.py`, `configs/config.yaml`(`deploy`, `paths`, `speakers` 키), `tests/`의 구간 파일 테스트, `CLAUDE.md`(허용 처리처 줄, 명령 한 줄), `docs/SPEC.md`(자원 제약, 결정 표시), `docs/DECISIONS.md`, 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/slices/35-chat-app.md`, `docs/slices/36-doc-browser.md`(조각 번호 표시)

## 범위 밖

- 실시간 재정렬과 추론 서버(S39). ZeroGPU에서 재정렬이 도는지와 방문자별 일일 할당량(무료 계정 5분, 비로그인 2분)도 S39에서 본다
- 대화 이어 가기(S40)
- 추천 질의, 첫 구동 안내, 데모 키 크레딧 한도, 3초 판정, Space와 앱의 공개(S41). 이 조각에서는 지금 생성 API 키를 비공개 Space에 넣는다
- 디자인, 답변 형식
- Dataset 저장소의 공개. 공개로 바꾸려면 다시 묻는다

## 결과 (2026-11-04)

커밋: 구현 069c9df. Space 코드 커밋은 Hub의 0654da5, Dataset 마지막 커밋은 `968be89c7ee6bfb1fb2bb8847805bda03190ed8f`(파일 180개, 저장 약 2.32GB, 비공개)

- 완료 기준 1: 비공개 Dataset과 비공개 ZeroGPU Space를 무료 계정에서 만들었다. 컨테이너 메모리 한도 104GB(`memory.max`), 16GB 할당 성공, CPU 16코어 분량(`cpu.max`), `/tmp` 10GB 쓰기 성공(디스크 한도는 호스트 값만 보여 확인하지 못함), Python 3.12.12, torch 2.13.0+cu130. `@spaces.GPU` 함수가 없으면 `No @spaces.GPU function detected during startup`으로 멈추고, 부르지 않는 함수 하나를 두면 돌며 할당량이 줄지 않는다. 비공개 Dataset 볼륨은 토큰 없이 읽혔고 `/home/user/app/data`로 지정해 `/app/data`에 붙었다
- 완료 기준 2: `tests/test_speakers.py` 통과. 실제 라벨로 만든 구간 파일이 문서 38,516개 모두 `doc_spans` 결과와 같다(구간이 빈 문서 6개 포함, 구간 80,292개). 파일 약 10MB, 키는 역할, 위치, 이름, 직책, 소속뿐이다
- 완료 기준 3: 올리기 전과 뒤 모두 비공개다. 목록에 표 밖 파일, `queries`, `LAB_`, 시험 파일이 없다
- 완료 기준 4: 지어낸 질의 3개의 근거 화면이 로컬과 글자까지 같다. 문서 탭은 문서 2개가 같다. 근거 탭은 25개 링크를 대조했고 6개만 끝의 빈 줄 2글자가 달라 화면에 영향이 없다(원인 확인하지 않음). 익명 접속은 404, 공개 API 목록은 비어 있고, 다운로드 버튼이 없고, 본문에 `splits`, `n_qa`, `summary_`가 없다. LangSmith에 호출이 남고 메타데이터 `git_commit`은 Space 저장소의 커밋이다
- 완료 기준 5: 아래 표(재정렬을 끈 구성). OpenRouter 26번, 비용은 재지 않았다(1,000질의당 약 $0.37로 어림해 약 $0.01)
- 완료 기준 6: 사용자가 화면에서 작동을 확인했고, ZeroGPU 유지와 벡터스토어 미도입을 정했다(D-80)

| 항목 | 값 |
| --- | --- |
| 첫 토큰 시간(지어낸 질의 20개, 한국에서 큐 요청) | 중앙값 1.58초, 최소 1.34초, 최대 4.24초 |
| 답변 전체 시간 | 중앙값 9.7초, 최대 33.0초 |
| 재시작부터 실행 상태까지 | 109초 |
| 재시작부터 첫 토큰까지 | 111초 |
| 인덱스·코퍼스 읽기(볼륨) | 71.0초 |
| 임베딩 모델 받기와 불러오기 | 12.4초 |
| 메모리 최고(`memory.peak`, 파일 캐시 포함 가능) | 8.43GB |

### 지시서와 다르게 하거나 더한 것

- 수정 허용 파일에 `src/rag/app.py`를 더했다. 시작 시간을 나눠 잰 출력 한 줄이다
- 구간 파일 설정은 `speakers`가 아니라 `deploy.speakers_from_file`에 뒀다. 생성 레시피가 `speakers` 전체를 기록해, 키를 더하면 지난 기록과 레시피가 달라진다
- 구간 파일에 만든 설정 지문을 함께 뒀다(`src/CLAUDE.md`, `check_basis`)
- Space 변수 `HF_HOME=/tmp/hf-home`, `PYTHONUNBUFFERED=1`, `LANGSMITH_TRACING=true`를 뒀다. `HF_HOME`이 없으면 임베딩 모델을 불러오는 단계에서 멈춘다(`rag.index.pinned`)
- `deploy/space/requirements.txt`는 잠금 파일에서 내보내되 torch, CUDA 묶음을 빼고 `pydantic`을 2.12.5로 낮췄다. Space 빌드가 함께 설치하는 `gradio[mcp]`가 2.12.5 이하를 요구한다. 앱 동작은 완료 기준 4로 확인했고 평가 환경은 바뀌지 않는다
- 볼륨 위치는 config가 아니라 Space 설정에 있다(`hf spaces volumes`). `deploy.space`, `deploy.dataset`은 이름 기록이고 코드가 읽지 않는다 이후 변경: S39부터 볼륨이 없고 진입점이 `deploy.space`, `deploy.dataset`을 읽는다(D-84)
- 첫 콜드 스타트 측정은 재시작이 적용되기 전 옛 컨테이너가 응답한 값(3초)이라 버리고, 실행 상태가 바뀌는 것을 본 값을 적었다

### 관찰

- 위 측정 때 Space의 `HF_HOME`은 Git Bash가 `/tmp/hf-home`을 Windows 경로로 바꿔 넣은 값이었다(모델이 `/app` 아래에 받아짐). 검증에서 찾아 `MSYS_NO_PATHCONV=1`로 고쳤고, 고친 뒤 한 번의 시작은 인덱스·코퍼스 81.0초, 모델 15.3초다
- `deploy/space/requirements.txt`를 잠금 파일에서 다시 내보내면 `pydantic` 고정이 돌아가 빌드가 깨진다. 내보낸 뒤 이 고정과 `pydantic-core` 삭제를 다시 적용한다
- `rag.speakers --export-spans`와 `--gen`을 함께 주면 `--gen`을 무시한다. 산출물은 틀어지지 않아 두었다(감사 P13)
- 채팅 칸의 `share` 버튼이 켜져 있다. S41 항목에 이미 있다
- `import spaces` 뒤 프로세스가 비정상으로 끝나면 로그에 남지 않는다. 시작 오류를 찾을 때 자식 프로세스로 앱을 띄워 출력을 받아 원인을 봤다
