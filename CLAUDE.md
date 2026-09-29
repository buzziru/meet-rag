# meet-rag

AI Hub 국회 회의록 데이터로 만드는 한국어 RAG 질의응답 시스템. 데이터 명세는 `docs/data.md`에 있다.

## 명령

- 환경: `uv sync --extra cpu` (GPU 환경은 `--extra cu126`)
- 테스트: `uv run pytest -q`
- 린트: `uv run ruff check .`
- 파이프라인 명령(데이터 적재, 분할, 인덱스, 검색, 평가, 생성)은 해당 SLICE가 끝날 때 여기에 추가한다. 빠른 확인은 dev-small로 한다

한글 출력이 깨지면 `PYTHONUTF8=1`로 실행한다. 파일은 `encoding="utf-8"`로 연다.

## 금지

- `src/rag/eval/`(S3 완료 후), `configs/eval/`, `data/splits/`(S2 완료 후)를 수정하지 않는다. 바꿔야 하면 사용자 승인 후 DECISIONS.md에 기록한다
- test 분할의 질의를 읽거나 test 점수를 계산하지 않는다. 검색 단계 종료 시 사용자 지시로 1회만 실행한다
- `docs/SPEC.md`의 평가 프로토콜은 사용자 승인 없이 바꾸지 않는다
- 파라미터를 코드에 직접 쓰지 않는다. `configs/`로만 바꾸고, 실험 설정은 `configs/exp/expNNN.yaml`에 둔다
- 평가 질의(`summary_q`)를 Google AI Studio·Gemini 무료 쿼터로 보내지 않는다
- 외부 GPU(Colab) 실행과 유료 API(OpenRouter) 호출은 예상 시간·비용을 보고하고 사용자 승인 후에만 한다. dev-small은 노트북에서 자유롭게 실행한다
- `data/`와 `.env`는 어떤 형태로도 커밋하지 않는다 (AI Hub 재배포 제한)
- `owner/`는 사용자가 의도를 전달하는 메모다. 읽고 의도를 파악하되 어떤 문서·코드에서도 참조하지 않고, 사용자 요청 없이 수정하지 않는다

## 문서

- 성공 기준·평가 프로토콜: `docs/SPEC.md`
- 베이스라인 조각·실험 백로그: `docs/PLAN.md`
- 조각 지시서: `docs/slices/NN-이름.md`
- 실험 지시서: `docs/experiments/EXP-NNN.md` (config는 `configs/exp/expNNN.yaml`)
- 실험 결과 요약: `docs/EXPERIMENTS.md`
- 채택 설정·방향 결정: `docs/DECISIONS.md`
- 현재 상태: `docs/STATUS.md`
- 브랜치·커밋·PR, 노트북 규약: `.claude/rules/`

## 세션 마무리

1. 끝난 실행이 있으면 평가하고 EXP 문서의 결과·결론을 채운다
2. 판정한 실험을 EXPERIMENTS.md에 한 줄 추가하고, 채택이면 DECISIONS.md를 갱신한다
3. PLAN.md 백로그 상태를 갱신하고 우선순위를 다시 정한다
4. 커밋할 수 있는 상태면 커밋한다
5. STATUS.md를 덮어쓴다 (한 화면 이내). 실행 중인 Colab 작업이 있으면 위치와 예상 종료 시각을 적는다
