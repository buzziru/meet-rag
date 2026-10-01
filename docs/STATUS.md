# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- S1~S4 완료. S4는 청크 512/64(DECISIONS D-04), 전체 코퍼스 인덱스 `data/index/kure-v1-fixed-512-64/full/`(청크 118,039, Colab L4 약 32분·0.73 CU)
- G1 완료(D-03, `summary_q` 전체 사용). S6 naive 컨텍스트는 문서별 최고 점수 청크(D-05)
- 하네스: Colab 보조 스크립트 `.claude/skills/meet-rag/scripts/colab_job.py`, `_workspace/` 작업 기록 규칙(PR #13). SPEC 자원 제약 개정: dev-small은 Jupyter 노트북으로 기록, GPU 계산은 Colab(D-06, PR #14)
- PR #15(`docs/s04-notebook`, `notebooks/04_01_청크크기비교.ipynb`)는 사용자 검토 대기

## 실행 중 작업
- 없음 (`colab sessions` 활성 세션 없음 확인)

## 판정 대기
- 없음

## 미완 상태
- 로컬 `data/`: processed, splits, dev-small 네 후보 인덱스와 full 512/64 인덱스, `data/runs/`(dev-small 순위 파일 넷, `chunk_sweep.json`), 질의 임베딩 캐시 `data/index/kure-v1/queries-dev-small.npz`
- KURE 모델은 `.hf_cache/`. `.env`의 `HF_HOME`은 절대경로(노트북 커널이 `notebooks/`에서 실행되기 때문)
- `_workspace/s04_main_progress.md`에 S5로 넘길 것이 있다. `00_main_harness-pending.md`는 전부 반영됨
- configs의 `???`: `retriever.chunk_pool`(S5), `generator.model`(S6)

## 시도했다 버린 것
- 로컬 CPU로 네 후보 임베딩: 문서 20개·256 토큰에 368.8초라 중단, dev-small도 Colab으로
- Colab 기본 Python 3.13에 패키지 설치: `requires-python ==3.12`로 실패. S4는 `PYTHONPATH=src`로 했고, 이후는 `colab_job.py setup`의 `uv sync`(VM에서 아직 미검증)

## 다음 행동
1. [C] PR #15 결과 확인. 병합되면 `main` pull, `docs/s04-notebook` 로컬 브랜치 삭제
2. [A] S5 dense 검색 + 평가(`docs/slices/05-retrieve.md` 작성부터). 넘길 것
   - 검색 방식은 naive 단계에서 numpy 전수 검색(exact kNN) 유지(사용자 결정). 지시서와 DECISIONS에 적는다
   - dev-full 인덱스는 512/64 full. 118,039청크(float32 약 480MB)는 질의를 나눠 내적한다. `chunk_pool`을 정한다
   - dev-small 과정·결과는 `notebooks/05_*.ipynb`로 남긴다(SPEC D-06)
   - 같은 명령 두 번 점수 일치. 끝나면 SPEC 미결 2(수치 목표)를 베이스라인 dev-full 점수로 정한다
3. [A] S6 생성(S5 필요)

## 사용자 확인 필요
- SPEC 평가 층 표의 "dev-small은 판정에 쓰지 않는다"에서 "판정"이 EXP 채택·기각 판정만 뜻한다고 문구로 명시할지(S4 감사는 그렇게 해석)
- `colab_job.py`의 VM 쪽 명령(setup·upload·launch·poll·fetch·finish)은 실행해 보지 않았다. 다음 Colab 작업 전에 CPU 세션으로 짧게 시험할지
- 보호 경로 훅은 파이프라인 완성 후 검토(결정됨, 그 전에는 두지 않음)
