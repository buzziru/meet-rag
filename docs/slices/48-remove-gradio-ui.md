# S48 Gradio 화면 제거

방문자 화면은 Vercel 페이지이고 Space의 Gradio 화면은 쓰지 않는다. 두 화면을 유지하면 채팅 경로가 둘로 남아(`respond`, `chat_events`) S40 대화 이어 가기를 두 번 고쳐야 한다. Space는 API만 맡는다(D-88 결정 2).

## 만드는 것

- **`rag.app` 화면 제거**: `build`에서 사이드바, 탭, 채팅 칸과 그 이벤트를 지우고 `gr.api` 등록만 남긴다. 화면에만 쓰던 `ask`, `respond`, `format_contexts`, `evidence_link`, `parse_evidence`, 스크립트 상수, `CSS`와 `rag.docs.format_doc`을 지운다
- **config**: `app`에서 화면에만 쓰던 값(`placeholder`, `contexts_title`, `browse_notice`, `doc_placeholder`, `evidence_placeholder`, `sidebar_width`, `notice`, 탭·선택 칸 라벨)을 지운다. `doc_payload`가 쓰는 `labels.chunk_start`, `chunk_end`, 채팅이 쓰는 `no_answer`, `concurrency`, `meeting_info_max_name`, Blocks 제목 `title`은 남긴다
- **로컬 확인 `?api=` 제거**: `deploy/web/app.js`의 분기를 지운다. 대상은 `SPACE` 하나다. 미리보기 배포로 병합 전에 볼 수 있어 필요가 없다(PR #229)
- **명령**: `CLAUDE.md`의 채팅 앱 줄을 API 서버로 고치고, 화면 배포 줄의 로컬 확인을 지운다
- **테스트**: `tests/test_app.py`에서 화면 함수 시험을 지우고, 변환·근거·추적 시험은 `chat_events`로 옮겨 남긴다
- **Space 반영**: 이 브랜치의 `src/`, `configs/`, `deploy/space/`를 `ingyoun/meet-rag`에 올린다. Dataset은 바꾸지 않는다

## 결정 사항

1. **Space 주소에 남는 것(메인 판단, D-88 결정 2)**: 빈 페이지다. Gradio Space는 뿌리 주소에 Blocks를 내므로 페이지 자체는 없앨 수 없다. 로컬 시험(gradio 6.31.0)에서 `gr.api`만 있는 Blocks의 구성 요소는 `api`뿐이고 일반 함수 호출이 됐다. 안내 문구는 대표 주소가 정해지는 S41에서 필요하면 더한다. 입력→동작: Space 주소를 열면 입력 칸 없는 빈 화면이고, 페이지와 재정렬 호출은 지금과 같다
2. **채팅 앱 명령(메인 판단)**: `rag.app`은 그대로 시작할 수 있고 API만 연다. 페이지가 로컬을 부르지 않으므로 값 확인 스크립트용이다
3. **`concurrency_id`(메인 판단)**: 그룹을 함께 쓰던 화면 채팅이 사라져도 페이지 API에 그대로 두어 동시 처리 수(S4)를 유지한다
4. **외부 호출과 재시작(승인 필요)**
   - OpenRouter: 지어낸 질의 2번(미리보기 1, production 1), $0.01 이하로 본다(1,000질의당 약 $0.37, S39b). 재정렬은 무료 ZeroGPU 할당량 안이고 Colab과 유료 HF 하드웨어는 쓰지 않는다. 지시서 확인 뒤 production 1번을 뺐다. 처음 지시는 production에서도 질의를 보내는 것이었고, 생성 변경이 없으면 답변으로 검증하지 않는다는 사용자 지시로 바꿨다(2026-11-05)
   - Space 재시작 1번: 그동안 페이지는 연결 대기에 머문다. 걸리는 시간은 S39 결과 절의 재시작 측정과 비슷할 것으로 보고 이번에 다시 재지 않는다. 시작 전에 공유 기록에 적는다
5. **사용자 작업**: 토큰 입력 0번(미리보기에는 `aside repl` 스크립트가 production 저장소에서 옮긴다, S47 토큰 절차 3). 지시서 확인 1번, 호출 승인 1번(위 4), PR 리뷰 1번. 화면 확인은 요청하지 않고, 병합 뒤 보고 싶으면 production 주소에서 보면 된다
6. **스킬 문구(메인 적용, meet-rag F2)**: "화면 검증" 절의 Gradio 선택 칸 사례는 작업 PR과 섞지 않고 하네스 대기 항목과 함께 `chore/` PR로 고친다. PLAN S48 줄의 이 항목을 대기 목록으로 옮긴다

## 노트북과 결정의 순서

데이터를 보고 정하는 결정이 없어 노트북을 쓰지 않는다.

## 완료 기준

질의는 지어낸 것만 보낸다.

| # | 명령 | 기대 결과 |
| --- | --- | --- |
| 1 | `uv run pytest -q`, `uv run ruff check .` | 통과. `src/rag/`에 지운 함수 참조가 없다 |
| 2 | `hf upload` 뒤 저장소 정보와 파일 목록, 토큰 스크립트로 Space `/config` | 비공개 유지, 표 밖 파일과 `queries`가 없다. 구성 요소는 `api`뿐이고 `chat`, `years`, `meetings`, `documents`, `document`, `score_pairs`가 있다 |
| 3 | 미리보기 주소에서 Aside(토큰은 스크립트로 옮김), 지어낸 질의 1번 | 답변이 조각으로 나오고 근거 5개, 연도·회의·문서를 골라 문서가 열린다. 콘솔 오류 없음 |
| 4 | Space 로그 | 3의 질의에서 재정렬이 돈다(`재정렬 N초`). 질의 원문은 로그에 없다 |
| 5 | 페이지 커밋 뒤에 문서 커밋을 함께 push | 미리보기가 빌드된다(S47에서 보지 못한 경우). `Vercel` 상태와 배포 기록을 적는다 |
| 6 | 병합 뒤 production 주소에서 Aside, 질의 없음 | 연결되고 연도·회의·문서를 골라 문서가 열린다. 콘솔 오류 없음. 결과는 PR 댓글에 적는다. 처음 지시는 질의 1번을 보내는 것이었고, 생성 변경이 없으면 답변으로 검증할 필요가 없다는 사용자 지시로 바꿨다(2026-11-05) |

## 수정 허용 파일

`src/rag/app.py`, `src/rag/docs.py`, `configs/config.yaml`(`app` 절), `tests/test_app.py`, `deploy/web/app.js`, `CLAUDE.md`(명령 두 줄), 이 문서, `docs/PLAN.md`, `docs/PLAN-done.md`, `docs/DECISIONS.md`(D-84·D-88 표시), `docs/slices/35-chat-app.md`, `docs/slices/39b-vercel-front.md`, `docs/slices/36-doc-browser.md`, `docs/slices/45-meeting-info.md`(`이후 변경` 표시), `tests/test_docs.py`

## 범위 밖

- 대화 이어 가기(S40), 추천 질의와 첫 구동 안내, 공개, 토큰 코드 삭제(S41)
- 첫 토큰 3초 재측정(S41에서 1회)
- 페이지 화면 변경
- 하네스 문구(결정 사항 6)

## 결과 (2026-11-05)

커밋: 구현 8ef6b6b. Space 코드 커밋은 Hub의 1ed5b2a(비공개, 이 브랜치 코드). Dataset은 바꾸지 않았다

| # | 결과 |
| --- | --- |
| 1 | `uv run pytest -q` 552개 통과(화면 시험을 지워 559개에서 줄었다), `uv run ruff check .` 통과. 지운 함수 참조 없음 |
| 2 | 올리기 전과 후 비공개. 질의·라벨 파일 없음(`configs/gen_eval/dev_queries.yaml`은 qid뿐이고 이미 Hub와 공개 저장소에 있다). `/config` 구성 요소는 `api` 13개뿐, API는 `chat`, `document`, `documents`, `meetings`, `score_pairs`, `years`. `years` 호출 28개(2023\~1996) |
| 3 | 미리보기(Aside, 토큰은 스크립트로 옮김), 지어낸 질의 1번: 답변 49자에서 842자로 늘어남, 근거 5개, 연도·회의·문서를 골라 문서 탭에 본문이 열림, 화면·콘솔 오류 없음 |
| 4 | Space 로그 `재정렬 4.58초`, `첫 글자 지연: 0.343초`. 질의 원문 없음 |
| 5 | 8ef6b6b(페이지)와 baadcfe(문서)를 함께 push해 빌드됐다. 다만 새 브랜치의 첫 push라 비교 대상이 없어서 빌드된 것일 수 있다. S47 수정이 같은 브랜치의 이어진 push에서도 맞는지는 이번에도 가리지 못했다 |
| 6 | 병합 뒤 확인(PR 댓글) |

OpenRouter: 미리보기 1번(승인 2번 중). production 확인은 질의 없이 해 나머지 1번은 쓰지 않는다. 비용은 재지 않았다(1,000질의당 약 $0.37로 어림).

### 지시서와 다르게 하거나 더한 것

- `tests/test_docs.py`의 `format_doc` 시험을 `doc_body`로 옮겼다. 처음 수정 허용 파일에 없어 `format_doc` 삭제에 따라 더했다. 회의록 링크 단언은 머리 줄과 함께 사라졌다. 페이지 경로의 링크는 `doc_payload`가 값으로 넘긴다
- `history`를 시험하던 `test_history_does_not_change_search_query`를 지웠다. 이력 동작은 S40에서 정한다

### 관찰

- 재시작 시작 로그는 인덱스·코퍼스 10.1초다. 재시작 전체 시간은 재지 않았다
- 답변의 인용별 뒤 문장은 이번에도 괄호 없이 번호만 붙었다(`…답했습니다 [2].`). S47의 미적용 1건과 같은지는 알 수 없다
