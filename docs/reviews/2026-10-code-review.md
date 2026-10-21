# 코드 리뷰 2026-10: 기준과 결과

프로젝트 시작 뒤 처음 하는 코드베이스 전체 리뷰다. 검색 단계 실험(EXP-001\~017)이 같은 모듈을 자주 고쳤고, 생성 단계 코드(S14·S14b)가 검색 위에 붙기 시작했으며, 테스트가 197개로 늘었다. 생성 실험을 쌓기 전에 구조를 한 번 점검한다(사용자 요청 2026-10-20).

리뷰는 지적 목록만 낸다. 고칠 항목은 사용자가 고르고, 수정은 리팩터링 SLICE(A 흐름)로 나눠 PR을 따로 낸다.

## 목적

1. 전체 파이프라인 점검: 검색 단계 실험의 잦은 수정으로 생긴 중복, 쓰이지 않는 코드, 조용히 어긋날 수 있는 곳
2. 테스트의 병목: 느린 테스트와 그 원인, 역할이 겹치는 테스트
3. 검색과 생성의 결합: 생성·생성 평가가 검색 쪽 내부 구현에 기대는 곳, 한쪽을 바꾸면 다른 쪽이 조용히 달라지는 곳

## 범위

- 대상: `src/rag/`에서 `multidoc/`을 뺀 모듈(약 3,500줄), `tests/`(multi-doc 생성·검사 테스트 `test_multidoc_*`를 뺀 파일), `configs/`
- 대상 밖: `notebooks/`(기록된 노트북은 고치지 않는다, notebook.md), `.claude/`(하네스는 F 흐름), `docs/`, `src/rag/multidoc/`(multi-doc 질의 생성·검사 코드). multi-doc 질의는 G3 동결 세트로 끝나 이 코드를 다시 쓰지 않으므로 리뷰하지 않았다(사용자 결정 2026-10-20). 다시 생성하게 되면 그때 리뷰한다. multi-doc 채점(`src/rag/eval_multi/`)은 계속 쓰므로 범위에 든다
- 보호 경로(`src/rag/eval/`, `src/rag/eval_multi/`, `configs/eval/`, multi-doc 동결 세트 설정)는 읽고 지적하되, 수정은 사용자 승인과 DECISIONS 기록을 거친다(CLAUDE.md 금지 절)
- 하지 않는 것: 코드 수정, 검색·생성 점수 비교, 외부 API·Colab 호출, test 분할 읽기, `data/`의 질의·라벨 파일 읽기

## 영역

영역마다 서브에이전트 하나가 읽기 전용으로 리뷰한다. 교차 항목(기준 3)은 영역 B·C 결과를 받아 메인이 모듈 사이 경계를 직접 읽어 정리한다.

| 영역 | 모듈 |
| --- | --- |
| A 데이터·인덱스 | `ingest`, `splits`, `chunking`, `index`, `bm25`, `chunk_sweep`, `meta_dict` |
| B 검색 | `retrieve`, `search`, `conditions`, `rerank`, `rewrite`, `g2` |
| C 생성·생성 평가 | `generate`, `gen_eval/*` |
| D 평가·검수 | `eval/*`, `eval_multi/*`, `sample_review` |
| E 테스트 | `tests/` 전체, 측정 결과 |

## 기준

### 1. 파이프라인 정합성

- 1a 기각·보류 실험의 코드: config로 켜는 분기로 남은 것은 의도된 것이다(git.md 기각 실험 병합). 지적하는 것은 어떤 config로도 닿지 않는 코드, 기준 설정 경로를 읽기 어렵게 만드는 분기 누적이다. 분기마다 어느 EXP·config가 켜는지 적는다
- 1b 같은 규칙의 중복 구현: 경로 규칙, 순위·필터 순서, 조건 추출, 문장 나누기처럼 한 곳에서 정해야 할 규칙이 여러 모듈에 따로 있는지(S12 원칙, 구현 원칙의 "경로 규칙은 config 템플릿 한 곳")
- 1c 미리 만든 파일 읽기: 실행 config에 따라 달라지는 입력(순위·점수·조건·인덱스)을 파일로 읽을 때 설정 지문을 대조하는지(구현 원칙)
- 1d 산출물 덮어쓰기: `data/` 아래에 쓰는 경로가 `write_guarded` 같은 덮어쓰기 방지를 거치는지
- 1e config와 코드의 대응: 코드가 읽지 않는 config 키, 코드에 직접 쓴 값(P4), 지난 `configs/exp/expNNN.yaml`이 지금 코드로 그대로 조합되는지(재현성)

### 2. 테스트

- 2a 측정: `uv run pytest -q --durations=30`의 상위 항목과 전체 시간. 측정 없이 느리다고 단정하지 않는다. 측정은 전체 테스트로 하므로, 범위 밖인 `test_multidoc_*`가 상위에 있으면 그 시간만 적고 리뷰하지 않는다
- 2b 느린 원인: 실제 `data/` 파일 읽기, 모델·인덱스 로드, 테스트마다 반복되는 준비, 외부 호출 대역 부재
- 2c 역할 겹침: 같은 동작을 여러 테스트가 확인하는지, 기각 실험 분기의 테스트가 기준 경로 테스트와 따로 비용을 쓰는지(지울지 판단은 사용자)
- 2d 실행 범위: 빠른 단위 테스트와 느린 통합 테스트를 나눠 PR마다 돌릴 범위를 정할 수 있는지(pytest marker 등). 나누는 안을 낼 때는 측정값을 붙인다
- 2e 빈 곳: 결과를 조용히 바꿀 수 있는데 테스트가 없는 경로(기준 1에서 찾은 곳 위주)

### 3. 검색과 생성의 결합

- 3a 의존 방향: `rag.generate`·`rag.gen_eval`이 검색 모듈의 내부 함수·자료 형식(순위 파일 열, 근거 dict 키)에 기대는 지점
- 3b 공유 규칙: 재정렬 순서(`rag.retrieve`로 옮긴 S14 규칙), 근거 구성(문서마다 청크 하나, D-05)처럼 평가와 생성이 같아야 하는 규칙이 한 곳에 있는지
- 3c 조용한 어긋남: 재정렬 점수 파일, 인덱스 경로, config 그룹(`retriever`·`generator`·`judge`·`prompt`)을 바꿀 때 생성 기록·judge 기록의 레시피가 그 변화를 잡는지
- 3d 다음 변경의 비용: 실시간 재정렬(배포 SLICE)과 근거 구성 변경(H10)을 붙일 때 바꿔야 할 곳의 수와 위치

### 4. 단순성

- 한 번만 쓰는 추상화, 쓰이지 않는 매개변수·설정 가능성, 일어날 수 없는 경우의 오류 처리(사용자 전역 규칙 "단순성 우선")
- 기준 1\~3과 겹치면 그쪽으로 적는다

## 지적 형식

지적마다 한 행으로 적는다.

| 항목 | 내용 |
| --- | --- |
| ID | 영역 글자와 번호(예: B-3) |
| 기준 | 위 기준 번호(예: 1b) |
| 위치 | `file:line` |
| 문제 | 무엇이 어떻게 되어 있는지 한두 문장 |
| 영향 | 입력→동작 사례 하나, 또는 측정값 |
| 제안 | 고치는 방향과 대략의 크기(파일 수) |
| 심각도 | 높음: 결과가 틀리거나 조용히 바뀔 수 있음 / 중간: 다음 작업(생성 실험, 배포)을 막거나 유지 비용이 큼 / 낮음: 정리 |
| 확인 | 메인이 근거를 직접 확인했는지 |

## 절차 (다음 세션)

1. 측정: `uv run pytest -q --durations=30`을 한 번 돌려 결과를 영역 E에 넘긴다
2. 영역 A\~E를 서브에이전트에 나눠 맡긴다(동시 3개, `references/worker-pool.md`). 프롬프트에 이 문서 경로, 맡은 모듈, 읽을 수 있는 경로(`src/`, `tests/`, `configs/`, `docs/`), 읽지 않을 경로(`data/`, `notebooks/`, `.env`), 지적 형식을 넣는다. 사용자가 리뷰 진행을 지시했으므로 승인 없이 띄우되, 시작할 때 영역 수와 예상 사용량을 알린다
3. 메인이 지적을 모아 중복을 합치고, 심각도 높음·중간은 근거를 직접 확인한다. 교차 항목(기준 3)을 정리한다
4. 아래 결과 절에 지적 표와 요약을 적고 사용자에게 본문으로 보고한다
5. 사용자가 고칠 항목을 고르면 리팩터링 SLICE로 묶어 지시서부터 쓴다. 보호 경로를 바꾸는 항목은 승인과 DECISIONS 기록을 먼저 한다

## 결과

2026-10-21, main 810bff0. 영역 A\~E를 서브에이전트 5개가 읽기 전용으로 리뷰했다(합계 약 77만 토큰, 영역당 4\~15분). 영역 사이 중복은 한 행으로 합치고 합친 ID를 함께 적었다. 심각도 높음·중간은 메인이 `file:line`을 직접 읽어 확인했다.

### 요약

- 결과를 틀리게 내는 계산 버그는 찾지 못했다. 지표, 회의 단위 bootstrap, 판정은 SPEC과 맞는다(영역 D 대조)
- 높음 6건은 모두 같은 유형이다. 이미 있는 산출물을 만든 설정과 대조하지 않고 읽거나, 덮어쓰기 방지 없이 쓴다. 인덱스 청크·임베딩 조각, 분할 파일, 재정렬 점수 파일, 생성 레시피가 해당한다
- 검색과 생성이 같아야 하는 규칙 가운데 순위 순서(`final_order`)만 한 곳에 있다. 문서마다 청크 하나(D-05), 청크 본문 읽기, 재정렬을 쓸지의 조건, 거부 문구는 2\~3곳에 따로 있다
- 테스트 시간은 대부분 Kiwi 인스턴스를 테스트마다 새로 만드는 비용과 `rag.rerank`의 모듈 첫머리 torch·sentence_transformers 임포트다. 둘을 없애면 전체 60.7초가 약 21.6초가 된다(임시 플러그인과 `--ignore`로 측정)

### 테스트 측정

| 무엇 | 값 |
| --- | --- |
| `pytest -q --durations=30` (메인, 첫 실행) | 197 passed, 102.0초 |
| 같은 명령 (영역 E, 다시 실행) | 56.5\~60.7초. 102초와의 차이는 원인을 확인하지 않았다(첫 실행의 디스크 캐시로 추정) |
| 상위 8개(test_bm25 3, test_fusion 2, test_rewrite 1, test_search 2) | 합 32.6\~37.5초. 9위부터 0.75초 이하 |
| 상위 8개, Kiwi 하나를 공유(임시 플러그인) | 35.8초 → 7.7초 |
| `--collect-only` | 21\~30초. `tests/test_rerank.py`를 빼면 12.7초 |
| Kiwi 하나 | 생성 1.4\~2.7초, 첫 `tokenize` 2.1\~4.2초(인스턴스마다 다시 듦) |
| `import rag.rerank` | 13.1초(sentence_transformers 8.8, torch 2.7) |
| 실행 범위 안 | 현재 60.7초 / E-1만 33.2초 / E-1·E-2 약 21.6초 / 느린 테스트를 marker로 빼기 16.8초 |

### 높음

| ID | 기준 | 위치 | 문제 | 영향 | 제안 | 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| A-1 | 1c | `src/rag/index.py:139`, `:164-171`, `configs/config.yaml:54` | `chunks.jsonl`이 있으면 대조 없이 다시 쓴다. 인덱스 경로에 `max_docs`, 코퍼스, dev-small 목록, `embedding.revision`이 없고, `meta.json`은 쓰기만 하고 읽지 않는다 | SLICE 04 절차대로 `index.max_docs=20`으로 실행한 뒤 같은 경로에서 다시 실행하면 문서 20개 인덱스로 오류 없이 끝난다. BM25도 이 청크로 만든다(`bm25.py:76`). 코퍼스를 다시 적재해도 옛 청크를 쓴다 | 다시 쓰기 전에 `meta.json`을 지금 설정·코퍼스 지문과 대조하고 다르면 멈춘다(bm25 settings.json 방식). 1\~2파일 | 메인 |
| A-2 | 1c | `src/rag/index.py:80`, `src/rag/retrieve.py:183-187` | 조각 이름 `part-k`에 조각 크기가 없고, `load_dense`는 청크 수와 임베딩 행 수를 대조하지 않는다 | `shard_size` 2048로 조각 0·1을 만들고 4096으로 이어 만들면 0·1을 건너뛰어 행이 빠진다. `extra_chunks`(EXP-011 이후 기준)에서는 256 인덱스 임베딩이 앞당겨져 512 인덱스의 doc_id와 짝지어지고 오류 없이 다른 순위가 나온다 | `index.main` 끝과 `load_dense`에서 행 수를 대조하고, 조각 크기를 meta에 적어 재개할 때 대조한다. 2파일 | 메인 |
| A-3 | 1d | `src/rag/splits.py:70-79` | 보호 경로 `data/splits/`의 분할과 dev-small 목록을 덮어쓰기 방지 없이 쓴다. 채점 결과에는 분할 파일 해시가 없다(`eval/score.py:36`) | 코퍼스를 다시 적재했거나 `seed`·`splits.*`를 바꾼 뒤 `rag.splits`를 실행하면 dev·test 구성이 바뀌고, 이후 점수를 과거 EXP와 비교해도 어떤 기록도 잡지 못한다 | `write_guarded`처럼 내용이 다르면 멈춘다. 1파일. 채점 결과에 분할 해시를 넣는 것은 보호 경로(D 영역) | 메인 |
| B-1 (C-2) | 1c, 3c | `src/rag/retrieve.py:134-140`, `src/rag/generate.py:140-144`, `configs/exp/exp017.yaml:30-31` | 재정렬 점수 파일을 경로만 보고 읽는다. 점수 파일에 만든 설정(모델, revision, dtype, 후보 쌍 해시)이 없고 생성 레시피에도 없다 | `retriever.rerank.model`만 바꾸고 `rag.rerank`를 다시 돌리지 않으면 `rag.search`가 EXP-017 점수로 순위를 내고, 생성 레시피에는 새 모델명이 남는다. 후보 쌍을 다시 만든 뒤 점수를 다시 내도 생성 기록은 같은 레시피로 이어 붙는다 | 점수 파일 옆에 basis(재정렬 설정과 후보 쌍 sha256)를 쓰고 읽을 때 대조한다(`rewrite.basis` 방식). 레시피에 점수 파일 sha256을 넣는다. 2\~3파일 | 메인 |
| B-2 | 1d | `src/rag/rerank.py:51`, `:76`, `:124`, `:138`, `configs/exp/exp017.yaml:22-23` | 점수·지연 파일을 `open("w")`로 쓴다. exp017 기본값은 `cpu`·`float32`이고 경로에 device·dtype이 없다 | 로컬에서 `rag.rerank +exp=exp017`을 다시 돌리면 Colab cuda·float16으로 만든 기준 점수 파일이 CPU float32 점수로 바뀌고, 기준 순위와 생성 근거가 같이 달라질 수 있다 | `write_guarded`를 거친다(B-7의 위치 이동과 묶음). 1\~2파일 | 메인 |
| C-1 (B-3) | 3c | `src/rag/generate.py:103-120`, `src/rag/conditions.py:178-190` | 생성 레시피에 `cfg.retriever`는 있지만 조건 추출 입력인 최상위 `cfg.conditions`와 `cfg.ingest.name_titles`가 없다 | `conditions.committee_aliases`에 약칭 하나를 더하고 `rag.gen_eval.generate +exp=exp017`을 이어 돌리면 근거가 바뀌어도 `done_qids`(`gen_eval/common.py:57`)를 통과해 같은 파일에 다른 검색의 기록이 섞인다 | 레시피에 두 설정(또는 해시)을 넣는다. 검색 레시피를 `rag.retrieve`가 만들게 하면 B-5와 같이 정리된다. 1\~2파일과 테스트 | 메인 |

### 중간

| ID | 기준 | 위치 | 문제 | 영향 | 제안 | 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| C-3 (B-4) | 3b, 1a | `src/rag/generate.py:160-174`, `src/rag/retrieve.py:327-337`, `src/rag/search.py:208-210` | 생성은 `retriever.rewrite.enabled`를 보지 않는다. `explain`의 `rewrite` 인자는 어디서도 호출되지 않는다 | `rag.generate +exp=exp013`은 재작성 없이 근거를 내고 레시피에는 `rewrite.enabled: true`가 남는다. EXP-013 기각이라 기준 경로에는 닿지 않는다 | 생성에서 rewrite가 켜져 있으면 멈추고, `explain`의 인자를 지운다. 1\~2파일 | 메인 |
| C-4 | 3c | `src/rag/gen_eval/common.py:15`, `:47-60`, `src/rag/gen_eval/judge.py:228-230` | 이어 쓰기는 `git_commit`을 무시하는데 judge는 커밋을 포함한 레시피로 "레시피가 여럿"을 낸다 | 커밋 A에서 n=10, 문서만 바꾼 커밋 B에서 n=20으로 이어 생성하면 생성은 통과하고 judge에서 멈춘다. 유료 생성을 마친 뒤에야 걸린다 | 한 규칙으로 맞춘다. 1\~2파일 | 에이전트 |
| C-5 | 3c, 1c | `src/rag/gen_eval/judge.py:70-78`, `src/rag/gen_eval/report.py:94` | judge 레시피에 `gen_eval.refusal`·`filler_phrases`·`chunk_key_min`과 커밋이 없다. report는 지금 cfg의 `chunk_key_min`을 출력한다 | judge를 0.5로 돌린 뒤 `report gen_eval.chunk_key_min=0.6`을 실행하면 0.5로 계산된 값에 "잠정 경계 0.6"이 찍힌다 | judge 레시피에 판정 키와 커밋을 넣고 report는 레시피 값을 쓴다. 2파일 | 에이전트 |
| C-6 | 1b | `configs/prompt/v1.yaml:7`, `configs/prompt/v2.yaml:9`, `configs/config.yaml:226` | 거부 문구가 생성 프롬프트와 `gen_eval.refusal`에 따로 있다 | 프롬프트 v3에서 거부 문구만 바꾸면 `refusal_split`(`gen_eval/checks.py:18-22`)이 거부를 찾지 못해 거부율 0, 거부 답변이 충실성 채점에 들어간다. 오류는 없다 | 거부 문구를 prompt 파일 한 곳에 두고 판정이 그 값을 읽는다. config 2\~3개와 코드 1파일 | 에이전트 |
| B-5 | 1b, 3b | `src/rag/search.py:201`, `:212-217`, `src/rag/generate.py:142`, `src/rag/retrieve.py:316-317`, `:340-341` | `final_order`는 한 곳이지만 그 앞뒤(RRF 정렬, 재정렬을 쓸지의 조건, depth, `top_k` 자르기)가 평가와 생성에 따로 있다 | `search.py:201` 조건만 고치면 평가 순위와 생성 근거가 조용히 달라진다 | `Retriever`가 "후보 → 최종 top_k"를 한 메서드로 내고 search·generate가 같이 부른다. 3파일 | 에이전트 |
| B-6 (C-7, A-4) | 1b, 3b | 청크 하나: `src/rag/search.py:228`, `src/rag/generate.py:51-57`, `src/rag/g2.py:120` / 본문 읽기: `search.py:26-35`, `generate.py:60-84`, `g2.py:67-77` / 인덱스 파일 이름: `index.py`, `bm25.py`, `retrieve.py`, `search.py`, `generate.py`, `g2.py` | D-05 규칙과 전역 청크 번호로 본문을 읽는 규칙이 각각 3곳에 있다. 재정렬 입력과 생성 근거가 같은 청크라는 전제가 두 구현이 우연히 같아서 성립한다 | H10에서 `best_chunks`만 바꾸면 재정렬 점수는 옛 청크 기준으로 남는다. 실시간 재정렬을 붙이면 네 번째 구현이 생긴다 | `rag.retrieve`에 청크 선택·본문 읽기 함수를 두고 같이 쓴다. 3\~4파일 | 에이전트 |
| B-7 (C-12, C-13) | 3a | `src/rag/rewrite.py:22`, `src/rag/gen_eval/judge.py:35`, `:242`, `src/rag/gen_eval/checks.py:5` | 검색(rewrite)이 생성 모듈을, 생성 평가가 `search.write_guarded`·`cfg.search.overwrite`와 조건 정규식을 import한다 | `conditions.DATE`를 검색 개선으로 바꾸면 judge의 일자 불일치 판정이 같이 바뀌고 judge 레시피는 잡지 못한다(C-5) | `split_thought`, `write_guarded`를 공용 모듈로 옮긴다. 정규식 공유는 C-5로 기록되게 한다. 4\~5파일 | 에이전트 |
| C-8 | 1d | `src/rag/gen_eval/review.py:86-88` | 사람이 채우는 검수 CSV를 덮어쓰기 방지 없이 쓴다 | 검수 칸을 채운 뒤 review를 다시 실행하면 빈 칸으로 덮인다 | 파일이 있으면 멈춘다. 1파일 | 에이전트 |
| D-2 | 1b, 1e | `src/rag/eval/bootstrap.py:20-25`, `src/rag/eval_multi/compare.py:1-3` | SPEC "메타데이터 가설의 판정"(D-18)이 코드에 없다. exp-judge가 JSON을 읽어 손으로 적용한다 | [메타데이터] EXP에서 recall@5·complete@5 행을 잘못 읽어도 잡아내는 코드가 없다 | 판정 함수를 두고 multi compare가 결과를 낸다. 2파일과 테스트. 보호 경로 | 메인 |
| E-1 | 2b | `src/rag/bm25.py:70`, `tests/test_bm25.py:72`, `:74` | `BM25Retriever`가 만들 때마다 `Kiwi()`를 새로 만든다. 상위 8개 테스트에서 인스턴스 12개 | 상위 8개 35.8초 → 공유 시 7.7초, 전체 60.7 → 33.2초 | 운영 코드에서 Kiwi를 모듈 수준에서 한 번 만들거나 테스트 픽스처로 공유한다. Kiwi는 `tokenize`·`split_into_sents`만 써서 공유해도 결과가 같다. 2파일 | 메인 |
| E-2 | 2b | `src/rag/rerank.py:23`, `:26`, `tests/test_rerank.py:3` | `rag.rerank`가 모듈 첫머리에서 torch·sentence_transformers를 import하는데 테스트는 순수 함수 `jev_body` 하나다 | 수집 25.1 → 12.7초(파일 제외로 측정) | import를 cross-encoder 함수 안으로 옮긴다(`rag.index.load_model` 방식). 1파일 | 메인 |
| A-11, B-13, C-17, D-8 | 2e | `tests/test_index.py`, `test_chunking.py`, `test_search.py:266-278`, `test_fusion.py:49-68`, `test_generate.py`, `test_gen_eval.py`, `test_eval.py` | 위 높음 지적의 경로와 기준 경로에 테스트가 없다: 청크 재사용·조각 재개(A-1·A-2), `chunk_sentences`와 실제 Kiwi, 조건 목록 결합과 최다 일치 필터의 Retriever 수준 경로, `explain`과 `search.finish`의 순위 일치, 모든 `configs/exp/*.yaml` 조합(지금 001·002·009·011·013·017만), 레시피 키(C-1·C-2·C-4), `eval.metrics.load_gold`(검색·채점·생성 평가의 질의 목록을 정하고 test 차단을 맡음) | 예: `load_gold`의 dev-small 필터가 바뀌면 검색 질의, 채점, 생성 평가 질의가 함께 바뀌는데 실패하는 테스트가 없다 | 고치는 지적과 같은 SLICE에 테스트를 붙인다. exp 전체 조합 parametrize 1개, explain·finish 일치 1개, `load_gold` 합성 파일 1\~2개. 테스트 파일 4\~5개 | 메인(D-8, B-13 일부) |

### 낮음

| ID | 기준 | 위치 | 문제와 제안 |
| --- | --- | --- | --- |
| A-5 (B-14) | 1b | `src/rag/chunk_sweep.py:37`, `src/rag/g2.py:86`, `src/rag/search.py:244-246` | 순위 파일 이름 규칙이 세 곳에 있다. `run_name`이 없는 설정(exp001)으로 g2를 돌리면 `...-None-dev-full.csv`를 찾는다. search에 이름 함수를 둔다. chunk_sweep(S4 일회성)을 지울지는 사용자 판단 |
| A-6 (D-5) | 1b, 4 | `src/rag/ingest.py:124`, `splits.py:58`, `sample_review.py:25`, `eval/metrics.py:17` | config 로드가 `rag.index.load_cfg` 밖에 세 번 더 있고 ingest·splits는 명령 override를 오류 없이 무시한다. `load_cfg(sys.argv[1:])`로 통일한다. eval은 보호 경로이고 override를 받지 않는 편이 평가 고정 취지에 맞다 |
| A-7 | 1d | `ingest.py:116-120`, `meta_dict.py:39-41`, `chunk_sweep.py:76-77` | 덮어쓰기 방지가 없다. 결정적 출력이라 A-1의 코퍼스 지문 대조로 충분하다 |
| A-8 | 1e | `configs/config.yaml:134-137` | 기본 임베딩 KURE-v1에 `revision`이 없어 HF main을 쓴다. EXP-001\~008 재현에 당시 revision을 적는다(값은 확인 필요) |
| A-9 | 1e | `index.py:136`, `chunk_sweep.py:15-16` | 특수 토큰 수 2와 chunk_sweep 비교 층·지표를 코드에 썼다. `num_special_tokens_to_add()`와 config로 옮긴다 |
| A-10 | 4 | `bm25.py:78-82` | settings.json이 없는 옛 BM25 인덱스 처리 분기. 기존 인덱스에 settings.json이 모두 있으면 지운다(사용자가 `data/index/*/bm25-*/` 확인) |
| C-9 | 1e | `gen_eval/report.py:111`, `configs/generator/gemma.yaml` | gemma.yaml에 `price_per_mtok`가 없어 report가 멈춘다. 비용을 지금 설정으로 계산한다 |
| C-10 | 1e | `gen_eval/review.py:71` | "근거 5개"를 코드에 썼다. `len(g["contexts"])` |
| C-11 | 1b, 1c | `generate.py:146-153`, `gen_eval/generate.py:31-34`, `configs/config.yaml:56` | 질의 원문·임베딩 캐시 읽기가 두 곳에 있고, 캐시 경로와 레시피에 `embedding.revision`·`query_prompt`가 없다. `rag.search`도 qid 목록만 대조한다(`search.py:115-118`). revision만 바꾸면 옛 질의 임베딩을 쓴다 |
| C-14 | 추적 | `generate.py:273`, `gen_eval/generate.py:44`, `gen_eval/judge.py:240` | LangSmith `flush`가 `finally` 밖에 있다(`rerank.py:122`는 안). 예외 때 추적이 빠지는지는 불확실 |
| C-15 | 1e, 4 | `generate.py:179-189` | 근거의 `score`는 `rrf_score`인데 재정렬을 켜면 순위를 정한 점수가 아니다. docstring과 출력이 어긋난다 |
| C-16 | 4 | `gen_eval/review.py`, `configs/config.yaml:235-237` | judge 두 설정 비교용 일회성 도구. D-40으로 결정이 났다. 남길지는 사용자 판단 |
| B-8 | 1a | `retrieve.py:205-212`, `:231-236`, `:264-305` | `lists()`에 플래그 6개(EXP-007 기각, EXP-013 기각, EXP-015·016 보류 포함)가 얽혀 있다. `fuse: false`와 `method: rrf` 조합은 `named["cc"]` KeyError. 분기마다 EXP 주석을 달고 기각 분기를 작은 함수로 뗀다 |
| B-9 | 4, 1a | `retrieve.py:95-103`, `:353-356` | `rrf()`와 `Retriever.rank`는 테스트에서만 쓰이고, `rank`는 재정렬을 받지 않아 기준 경로와 다르다. 테스트를 `explain`(B-5의 공용 메서드)으로 옮기고 지운다 |
| B-10 | 1e | `retrieve.py:307-310` | `fusion.weights`를 목록 삽입 순서에 위치로 대응한다. 조건 목록이 없는 질의에서 가중치가 다른 목록에 붙는다(지금 어느 exp도 닿지 않음). 이름 dict로 바꾼다 |
| B-11 | 1e | `retrieve.py:206`, `:275`, `:278`, `search.py:244` | 기본값이 `configs/retriever/dense.yaml`이 아니라 코드의 `get(..., 기본값)`에 있다 |
| B-12 | 1d | `search.py:108-121`, `g2.py:196` | 질의 임베딩 캐시를 qid 목록이 다르면 로컬에서 다시 만들어 덮어쓰고, g2 review는 사람이 체크한 파일을 덮어쓴다(G2는 끝남) |
| B-15 | 1e | `configs/exp/exp003.yaml:3`, `:9`, `exp008.yaml:3`, `:17`, `exp009.yaml:3` | S12 이전 절차(조건 파일을 먼저 만듦)를 적은 주석이 남았다. 결과 영향은 없다 |
| B-16 | 1e | `configs/h8/judge_v1.yaml`, `configs/rewriter/prompt/rwctx_v1.yaml` | `src/`에 읽는 코드가 없다. 노트북 전용으로 보인다(불확실). 머리 주석에 적는다 |
| D-1 | 1b | `eval/metrics.py:71-90` ↔ `eval_multi/metrics.py:34-53` | 순위 검증·중복 제거·표 출력이 두 번 구현돼 있다. 보호 경로 |
| D-3 (D-4) | 1d | `eval/score.py:42`, `eval/compare.py:60`, `eval_multi/score.py:38`, `eval_multi/compare.py:64`, `sample_review.py:48-50` | `--out` JSON과 G1 표본 CSV를 덮어쓴다. 순위 파일은 보호돼 다시 만들 수 있다. 보호 경로 |
| D-6 | 1e | `eval_multi/compare.py:28` | 재표본 단위 `pool_id`를 코드에 썼다(slices/09에 의도로 적힘). 보호 경로 |
| D-7 | 1b | `eval/compare.py:45-56` | single compare는 층별 차이를 내지 않아 D-33·D-35 선례 확인을 손으로 한다. 보호 경로 |
| D-9 | 2e | `eval/bootstrap.py:21`, `:23` | 판정 경계(점 추정 = min_gain, 하한 = 0) 테스트가 없다 |
| D-10 | 2e | `tests/test_eval_multi.py:73` | `pytest.raises(ValueError)`에 match가 없다 |
| D-11 | 형식 | `eval/metrics.py:59-60`, `:83-85` | 빈 doc_id가 NaN으로 읽혀 문서 하나로 세어지고 문서 하한을 채운다. search가 빈 doc_id를 쓸 수 있는지는 확인하지 않았다. 보호 경로 |
| E-3 | 2c | `tests/test_search.py:251`, `:266` | 두 테스트의 준비가 글자까지 같다(각 3.1초). E-1 뒤에는 0.2초 수준 |
| E-4 | 2c | `tests/test_bm25.py:23-55` | 캐시 재읽기를 두 테스트가 확인한다. E-1 뒤에는 거의 0초 |
| E-5 | 2c | `tests/test_bm25.py:13-20`, `tests/test_search.py:165` | rrf 테스트가 두 파일에 있고 동점 규칙을 두 번 확인한다 |
| E-6 | 2b | `tests/test_conditions.py:123-131` | 실제 `data/` 값 사전을 읽고 없으면 skip한다. data가 없는 환경에서는 조용히 빠진다 |
| E-7 | 2d | `pyproject.toml`, `tests/` | marker와 conftest가 없고, test_fusion·test_rewrite가 `test_search`에서 픽스처를 import한다. E-1·E-2 뒤 marker 분리로 더 줄일 수 있는 시간은 약 5초다 |

### 기준 3 정리: 검색과 생성의 결합

- 3a 의존: 생성은 `Retriever`의 속성(`dense_ids`, `dirs`, `chunk_emb`, `hybrid`, `use_cond`)과 `explain`, `chunks_by_doc`, `read_rerank_scores`, `build_extractor`, 단계 dict 키(`rrf_score`, `rerank_score`)에 기댄다. 생성 평가는 `search.write_guarded`, 조건 정규식, 보호 경로의 `eval.metrics.load_gold`에 기댄다. 반대 방향으로 `rewrite`가 `generate.split_thought`를 import한다(B-7)
- 3b 공유 규칙: 순위 순서(결합 → 재정렬 → 최다 일치 필터)는 `final_order` 한 곳이다. 재정렬을 쓸지의 조건과 `top_k` 자르기(B-5), D-05 청크 선택과 본문 읽기(B-6), 거부 문구(C-6)는 따로 있다. rewrite는 search에만 있다(C-3)
- 3c 레시피에 빠진 입력: 조건 추출 설정(C-1), 재정렬 점수 파일(B-1), 질의 임베딩 revision·query_prompt(C-11), judge의 판정 키와 커밋(C-5)
- 3d 다음 변경의 비용
  - 실시간 재정렬: 4\~5곳. `rerank.py`에서 메모리 안 채점 함수를 떼고, 후보 쌍 규칙(`search.py:38-46`, `:227-229`)을 생성과 같게 하고, `generate.py:140-144`의 파일 읽기를 바꾸고, `explain`이 점수 dict 대신 채점 함수를 받게 하고, 레시피에 재정렬 설정을 넣는다. B-5·B-6을 먼저 하면 두 곳이 한 곳으로 준다
  - H10 근거 구성: 5\~6곳. `best_chunks`, `Pipeline.retrieve`의 문서 하나당 근거 하나 전제(`zip(strict=True)`), 설정 키와 레시피, 프롬프트 `context` 템플릿, judge의 `gold_position`(`gen_eval/checks.py:91-93`)과 `contexts[gold_n - 1]`(`judge.py:207`), `review.py:71`. 정답 문서에서 청크를 둘 이상 넣으면 `answer_in_chunk`는 첫 청크만 본다. 검색 쪽 재정렬 입력(`search.py:228`)을 같이 바꾸면 EXP-017 점수 파일을 다시 만들어야 한다(Colab)

### 보호 경로가 걸린 항목

수정 전에 사용자 승인과 DECISIONS 기록이 필요하다: D-1, D-2, D-3, D-6, D-7, D-11, A-3의 채점 결과 분할 해시. A-3의 `splits.py` 덮어쓰기 방지는 코드가 보호 경로 밖이고 `data/splits/`의 내용을 바꾸지 않는다.

### 고칠 항목 (사용자 선택 2026-10-21)

묶음마다 리팩터링 SLICE 하나로 하고, 그 묶음의 테스트 빈 곳을 같이 채운다. 낮음은 고치지 않는다.

| 묶음 | 항목 | 같이 채울 테스트 |
| --- | --- | --- |
| 산출물 지문·덮어쓰기 | A-1, A-2, A-3(splits.py만), B-1, B-2, C-1, C-4, C-5, C-8 | A-11 청크 재사용·조각 재개, C-17 레시피 키 |
| 검색·생성 규칙 한 곳으로 | B-5, B-6, B-7, C-3, C-6 | B-13 explain·finish 순위 일치, 조건 목록 경로, exp 전체 조합 |
| 평가 쪽 | D-8, D-2 | D-8 `load_gold` 합성 파일 테스트. D-2는 보호 경로라 지시서에서 승인을 받고 DECISIONS에 기록한 뒤 고친다 |

고르지 않은 것: 테스트 속도(E-1, E-2). 측정값은 위 "테스트 측정"에 남긴다.
