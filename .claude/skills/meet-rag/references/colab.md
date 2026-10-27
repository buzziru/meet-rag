# GPU 작업 (Colab)

meet-rag 스킬 E절의 본문이다. 단계 번호(E1\~E7)는 스킬과 같다.

임베딩은 KURE-v1이고 다른 임베딩 모델로 바꿔도 직접 임베딩하므로, 전체 코퍼스 임베딩·인덱스 구축·재임베딩 실험에는 GPU가 필요하다. 로컬 PC에는 GPU가 없어(SPEC 자원 제약) 이 작업은 Colab VM에서 `colab` CLI로 한다. 생성(OpenRouter, D-37)과 judge(opencode Go, D-38)는 GPU를 쓰지 않는다.

VM 조작은 `scripts/colab_job.py`로 한다. colab CLI를 손으로 부를 때 반복해 생긴 함정(Git Bash 경로 변환, cp949 출력 오류, 미push 커밋, override 오타, Colab Python 3.13, 20분 전후 연결 끊김, tar의 `C:` 해석)을 스크립트가 막는다. 함정을 기억으로 피하면 다음 세션에서 같은 실수가 난다. 스크립트가 다루지 않는 일(세션 할당, 상태 확인, 복구)만 colab CLI를 직접 쓴다.

A2(S4 등 전체 인덱스)와 B3(재임베딩 실험)에서 GPU 임베딩이 필요하면 이 절차를 따른다.

1. **로컬 확인**: 로컬 PC CPU에서는 코드가 돌고 재개되는지만 본다. 문서 수십 개 이하, 후보 하나로 충분하다. 로컬 CPU는 문서 20개·256 토큰에 약 6분 걸려, 그 이상은 시간만 쓴다. dev-small이라도 임베딩은 GPU에서 하고, GPU 실행은 E3 승인 대상이다. dev-small 작업 과정과 결과는 Jupyter 노트북(`notebooks/`)에 남긴다. 노트북은 Colab 산출물을 불러와 확인하는 자리이고, 노트북에서 무거운 임베딩을 돌리지 않는다
2. **colab-operator 불러오기**: VM을 할당하기 전에 `colab-operator` 스킬을 Skill 도구로 불러온다. 설치 때 읽은 기억으로 대신하지 않는다(S4에서 두 번 모두 불러오지 않고 진행한 사례)
   - CLI 설치: Windows에서는 PyPI 배포본(0.7.4까지)이 `termios` import로 시작하지 못한다(googlecolab/google-colab-cli 이슈 #78·#100). 수정(PR #135)이 들어간 공식 저장소 main의 고정 커밋으로 설치한다: `uv tool install --force "git+https://github.com/googlecolab/google-colab-cli@d4f855d"`. 다음 릴리스에 이 수정이 들어가면 PyPI 버전으로 돌아간다. 설치한 패키지 파일을 로컬에서 고치지 않는다. 이전 0.6.0은 로컬에서 고친 상태로 동작했는데 기록이 없어, 다시 설치하자 원인을 찾지 못하고 실행할 수 없었다(2026-10-14, ADR-0040)
   - 세션 유지: 이 버전부터 keep-alive 데몬이 없고 Colab 백엔드가 커널 활동으로 세션을 유지한다. VM 작업 중에는 `poll`이 주기적으로 exec를 보내 커널을 깨우고, `fetch`는 내려받는 동안 1분마다 깨운다. `colab download`는 커널을 거치지 않아, EXP-012에서 24분 걸린 다운로드 중에 세션이 회수돼 인덱스를 잃었다. 확인 없이 오래 두면 회수될 수 있으니 긴 작업은 `poll`을 백그라운드로 계속 돌린다(E6)
3. **승인 지점**: GPU 종류, 예상 시간, 예상 compute unit을 사용자에게 보고하고 승인받는다. GPU는 사용자가 지정한 것을 쓰고, 지정이 없으면 묻는다. 서브에이전트는 VM을 만들지 않는다. 과금이 걸린 결정이라 사용자에게 물을 수 있는 메인만 한다. 작업 중 사용량이 예상을 넘을 것 같으면(재할당, 처리량 저하) 그 시점에 다시 잡은 예상과 함께 알린다. 사용자가 모르는 비용 초과만 문제이고, 알린 초과는 실행 기록에 사실로 적을 뿐 PR에서 다시 묻지 않는다(PR #78 코멘트: EXP-012 예상의 약 3.6배)
   - 예상 시간: 같은 GPU의 직전 실측 처리량(SLICE·EXP "실행 기록")을 문서 수 비율로 늘리고, 준비(환경 설치·모델 다운로드)와 결과 다운로드 시간을 더한다
   - 예상 compute unit: 요율 × 예상 세션 시간("요율 환산"으로 표시). 요율은 사용자가 Colab 웹 화면에서 확인해 준 값(L4 1.54, T4 1.04 CU/시간)을 쓴다. 요율 환산은 실측보다 약간 높게 나와 상한으로 본다(S4 32분 세션 실측 0.73, 환산 0.83). 처리량에서 요율을 거꾸로 추정하지 않는다. S4 1차에서 그렇게 해 예상치를 낮게 냈다
4. **사전 점검**: `colab_job.py preflight <override...>`. 커밋되지 않은 변경, 원격에 없는 HEAD, 틀린 override를 VM 할당 전에 막는다
5. **할당과 환경**: `colab new -s meet-rag-<작업> --gpu <GPU>` 뒤 `colab_job.py setup -s <세션> --commit <HEAD>`. VM에 uv를 깔고 `uv sync --extra cu126`으로 Python 3.12와 `uv.lock` 버전을 그대로 맞춘다. 로컬과 같은 버전이어야 결과를 재현할 수 있다. 출력된 Python·torch·transformers·sentence-transformers 버전을 실행 기록에 남긴다
   - 할당이 실패하면(400 등) `--gpu T4`로 바꿔 다시 할당한다. 이 대체는 승인 범위 안이라 다시 승인받지 않고 바뀐 GPU와 다시 잡은 예상 시간만 알린다. T4도 실패하면 멈추고 보고한다. 비용이 예상과 달라졌다는 이유만으로 작업을 멈추지는 않는다
6. **입력과 실행**: `colab_job.py upload`로 입력(`data/processed/` 코퍼스, 필요하면 범위에 맞게 거른 파일)을 올리고, `colab_job.py launch -s <세션> -- python -m <모듈> <override...>`로 VM 안 nohup 실행을 띄운 뒤 `colab_job.py poll`로 로그를 본다. 질의는 dev 질의만 거른 파일을 올린다(`upload`가 dev가 아닌 qid가 있으면 막는다). dev 질의는 summary_q dev 분할과 G3 multi-doc 동결 세트(`queries_g3.jsonl`, test 회의를 뺀 dev 전용 세트)의 질의다. `test` 질의와 분할 파일(`queries.csv`)은 올리지 않는다(평가 프로토콜, D-31). dev 질의를 Colab에 보내는 것은 처리 목적이라 허용된다. 질의를 담은 데이터는 jsonl로 쓰고 질의 ID 키는 `qid`로 한다. 업로드 검사가 이 형식에만 기대기 때문이다. 노트북에는 질의 원문을 대량 출력하지 않는다(공개 금지, D-31). `docs/STATUS.md` "실행 중 작업"과 `_workspace/` 진행 기록에 세션 이름, 커밋, 예상 종료 시각을 적는다
   - 띄운 직후 `poll --interval 30 --max-polls 2`로 짧게 확인한다(`poll`은 기본으로 작업이 끝날 때까지 돌아오지 않는다). 이때 "최대 확인 횟수를 넘었다"로 끝나는 것은 실패가 아니라 아직 실행 중이라는 뜻이다. 작업이 정상으로 시작된 것(모델 로드나 진행 표시가 오류 없이 나옴)을 확인하면, `poll`은 Bash `run_in_background`로 돌리고 메인은 다음 작업(사용자 질문, 문서, 다른 흐름)을 진행한다. 끝나면 알림이 온다. VM 작업은 수 분에서 수십 분이 걸려, 포그라운드로 기다리면 그동안 사용자가 다른 일을 맡길 수 없다(사용자 피드백 2026-10-13, ADR-0035). dev-small 결과를 확인한 뒤 남은 단계(dev-full, multi-doc, 지연 측정 등)는 `launch -- bash -c "python -m 모듈1 … && python -m 모듈2 …"`로 VM 작업 하나에 묶어 확인 횟수를 줄인다. dev-small과 dev-full을 처음부터 묶지 않는다. `&&`는 실행 오류에서만 멈추고 결과가 정상인지는 보지 않기 때문이다(B3)
7. **회수와 정리**: `colab_job.py fetch -s <세션> <저장소 기준 산출물 경로>`로 내려받아 로컬 같은 경로에 푼다(worktree의 `data/`가 junction이면 원래 폴더에 풀린다). 로컬에서 다시 만들 수 있는 파일(예: `chunks.jsonl`)은 `--exclude`로 빼 전송량을 줄인다. 내려받는 속도가 초당 1MB 안팎이라 GB 단위 산출물은 수십 분 걸린다. 이어서 `colab_job.py finish -s <세션>`으로 세션 기록을 `outputs/notebooks/`에 남기고 VM을 멈춘 뒤 남은 세션이 없는지 확인한다. 멈추지 않은 VM은 백엔드가 세션을 유지하는 동안 크레딧을 계속 쓴다(새 CLI 본문에는 회수 상한이 적혀 있지 않다). 실제 세션 시간(할당부터 `finish`까지)과 compute unit을 SLICE·EXP 문서 "실행 기록"에 적는다. compute unit은 사용자에게 실제 값을 묻지 않고 요율 × 세션 시간 환산값을 "요율 환산"으로 표시해 적는다(사용자 지시 2026-10-14). 사용자 확인값을 기다리면 기록이 "확인 대기"로 남고 STATUS·PR에 확인 요청이 쌓인다(EXP-006·009)

산출물 취급:
- 내려받은 인덱스·임베딩은 `data/` 아래에만 둔다. 원문을 담고 있어 AI Hub 재배포 제한을 받는다
- `colab exec -f nb.ipynb`가 만드는 `*_output.ipynb`와 `colab log -o`로 내보낸 기록은 `outputs/notebooks/`에 둔다. `outputs/`는 프로젝트 진행 중 커밋하지 않고(`.gitignore`) 완료 후 결과 공개 때 공개한다. 출력에 질의가 조금 들어가는 것은 괜찮다. 회의록 발언 원문은 AI Hub 생성물이 아니지만, 질의응답쌍과 그 분할은 AI Hub 고유 자료일 수 있어 대량으로 남기지 않는다
- `colab auth`, `colab drivemount`는 사람이 터미널에서 해야 하므로 필요하면 사용자에게 요청한다

비밀 값(API 키):
- VM에는 API 키를 보내지 않는다. API 호출(생성, judge, 재작성)은 로컬에서 하고 VM은 GPU 계산만 한다. `colab_job.py`는 `doppler run` 없이 띄운다. 로컬 `colab` CLI에 환경 변수 전체가 넘어가므로(`colab_job.py`의 `ENV`), 키가 없는 환경에서 띄워야 넘어갈 여지가 없다(사용자 결정 2026-10-27, ADR-0068)
- `HF_HOME`은 비밀 값이 아니라 `colab_job.py launch`가 HF 기본 캐시 위치(`/root/.cache/huggingface`)로 넘긴다. 없으면 `rag.index.pinned`가 멈춘다. `launch` 밖에서 VM에 `rag.*`를 돌릴 때(`colab console` 복구, `colab exec`)는 명령 앞에 `HF_HOME=/root/.cache/huggingface`를 붙인다
- 키가 필요한 VM 작업이 생기면 Colab 보안 비밀(`google.colab.userdata`)로 시도한다. CLI로 만든 세션에서 쓸 수 있는지 먼저 웹 자료와 실험으로 확인하고, 실험의 Colab 사용은 승인 지점(3)을 거친다. 실행 코드에 키를 넣어 보내지 않는다. `colab exec` 코드는 로컬 실행 기록(`~/.config/colab-cli/history/`)과 `outputs/notebooks/`의 세션 기록에 남고, `outputs/`는 결과 공개 때 공개된다

## 오류 처리

- Colab 명령이 멈추거나 끊기면(`colab exec`의 시간 초과, "Connection was lost") `colab_job.py`가 시간 제한 안에서 다시 시도한다. 그래도 실패하면 기다리지 않고 `colab restart-kernel -s <세션>`(VM은 그대로, 커널만 다시)을 한 뒤 다시 하고, 계속 안 되면 같은 셸 명령을 `colab console`로 보낸다(터미널 경로라 커널 연결과 별개다). 파일 전송은 console로 하지 않고 `colab_job.py upload`로만 한다. console에는 업로드 검사(dev가 아닌 질의·분할·`.env` 차단)가 없기 때문이다. EXP-009에서 `colab exec`가 40분 멈추는 동안 `colab console`과 `colab upload`는 동작했다(colab-operator Recovery 절, ADR-0036). `launch`가 실패했으면 다시 띄우기 전에 짧은 `poll`로 작업이 이미 떴는지 확인한다. 로그 파일은 `setup`과 같으므로 완료 표시가 아니라 로그 첫 줄의 `date` 시각이 `launch` 시각 뒤인지로 판단한다(응답만 끊기고 VM에서는 떴을 수 있고, 두 번 띄우면 같은 산출물을 동시에 쓴다). 단계마다 성공 표시를 확인한 뒤 다음 단계로 간다: `setup`은 Python·torch 버전 줄, `upload`는 `wc` 줄, `launch`는 짧은 `poll`의 진행 표시다. `setup`은 저장소 폴더를 지우고 다시 만들므로, 실패한 `setup` 뒤 업로드를 먼저 하지 않는다(EXP-009에서 실패한 `setup`을 확인하지 않고 업로드·실행으로 넘어가 다시 실패했다)
- 진행 중이던 VM이 오류로 회수되는 등(404·401) 승인 때 예상하지 않은 GPU 사용이 생기면, 새 VM을 만들기 전에 `colab sessions`와 `colab log -s <세션>`(세션 회수 원인)으로 상태를 확인하고 사용자에게 보고한다. `colab sessions`에 할당이 `[?]`(로컬 기록 없음)로 남으면 CLI로 멈출 수 없으니 사용자에게 Colab 웹 화면에서 종료를 요청한다. 재할당은 사용자가 정한 뒤 중간 산출물부터 재개하고, 재개 명령과 진행 위치를 STATUS에 적는다. 조용히 반복 재시도해 비용을 쓰지 않는다. 인증 오류(403 등)도 다시 시도하지 않고 보고한다

## 시나리오

- 정상: S4 dev-small 통과 후 "전체 인덱스 Colab에서 만들어" → E1 로컬 소규모 재개 확인 → E2 colab-operator 불러오기 → E3 L4·예상 시간·compute unit(요율×세션 시간) 보고, 승인 → E4 `preflight index.scope=full` → E5 `colab new`·`setup` → E6 `upload`·`launch`·`poll`, STATUS·진행 기록 → E7 `fetch`·`finish`, 실행 기록 → A3 verifier가 내려받은 인덱스로 검증
- 오류: E5에서 A100 할당이 400으로 실패 → `--gpu T4`로 재할당, 바뀐 GPU와 다시 잡은 예상 시간을 사용자에게 알리고 진행 → T4도 실패하면 멈추고 보고
- 오류: E6 실행 중 VM이 회수돼 `poll`이 404로 실패 → `colab sessions`로 확인 → 새 VM을 만들지 않고 진행 위치와 재할당 예상 비용을 사용자에게 보고 → 사용자가 정하면 중간 산출물부터 재개
- 오류: E6에서 `upload`가 "dev가 아닌 질의 N건"으로 멈춤 → dev로 거른 파일을 다시 만들어 올린다. 차단을 우회하지 않는다
- 오류: E4 `preflight`가 "HEAD가 원격에 없다"로 멈춤 → push 후 다시 `preflight` → VM 할당은 그 뒤에 한다
