# PLAN: 국회 회의록 RAG (SPEC.md 기준)

naive RAG(고정 길이 청킹 → KURE-v1 dense 검색 → 생성)로 베이스라인을 세우고, advanced RAG 기법을 한 부분씩 더해 검색 성능을 높인다. 검색 단계 판정은 SPEC의 dev-full Recall@5로 한다.

## 베이스라인

- [x] S1 데이터 적재: 라벨 zip에서 코퍼스(`corpus_context.jsonl`)와 질의(`queries_summary_q.jsonl`)를 재생성 → slices/01-data.md
- [x] S2 평가 분할: `data/splits/queries.csv`, `data/splits/dev_small_docs.txt` 생성 (S1 필요) → slices/02-splits.md
- [x] G1 `summary_q` 검수: dev 100건을 사람이 검수하고 필터 규칙 여부를 정한다. SPEC 미결 1 (S2 필요, S5 평가 실행 전에 끝낸다) → DECISIONS D-03
- [x] S3 평가 모듈: 순위 파일(`qid`, `rank`, `doc_id`) → Recall@1·5·10, MRR@10, 회의구분·`qna_type`별 지표, 회의 단위 paired bootstrap. 합성 입력으로 검증한다. 완료 후 수정 금지 대상 → slices/03-eval.md
- [x] S4 청킹·임베딩·인덱스: 고정 토큰 길이 청킹, KURE-v1 임베딩, 중간 산출물 저장 후 재개 가능. dev-small은 노트북, 전체는 Colab (S1 필요) → slices/04-index.md
  - 인덱스 경로에 설정 식별자를 넣고(예: `data/index/{임베딩모델}-{청킹}-{청크크기}/`) 어느 인덱스를 쓸지 config에 적는다. `data/`는 브랜치를 따라 바뀌지 않으므로, 브랜치를 옮기면 코드와 인덱스가 어긋날 수 있다
  - Colab에서는 저장소를 clone해 실행하고, 인덱스는 git에 올리지 않고 내려받아 로컬 `data/`에 둔다
- [x] S5 dense 검색 + 평가 실행: dev-small, dev-full 순위 파일 생성과 평가. 같은 명령을 두 번 실행해 점수가 같아야 한다 (S2, S3, S4, G1 필요) → slices/05-retrieve.md
- [ ] S6 생성: 검색 결과를 넣은 프롬프트로 Gemma 4 31B(Google AI Studio, OpenAI 호환 엔드포인트, DECISIONS D-01)를 호출하고 답변과 근거 URL(`original`)을 낸다. 직접 쓴 질의로 동작만 확인하고 정량 평가는 하지 않는다 (S5 필요) → slices/06-generate.md

S5 완료 후 베이스라인 dev-full 점수로 SPEC 미결 2(수치 목표)를 정한다. → DECISIONS D-09(Recall@5 0.90)

## 실험 백로그

예상 효과는 사전 추정이다. 재임베딩이 필요한 실험은 Colab 크레딧을 쓰므로 비용 칸에 표시했다.

- [대기] H1 hybrid: dense + BM25(Kiwi 형태소), RRF 결합 (효과 큼 / 인덱스 재사용, BM25 인덱스 CPU 구축)
- [대기] H2 reranker: 상위 후보를 cross-encoder로 재정렬 (효과 큼 / 재임베딩 없음, CPU 지연 증가. SPEC 미결 3과 연결)
- [대기] H3 청크 길이·overlap 변경 (효과 중 / 재임베딩)
- [대기] H4 문장 경계 청킹: Kiwi 문장 분리 후 길이에 맞춰 묶음 (효과 중 / 재임베딩)
- [대기] H5 청크에 메타데이터 접두(회의명·위원회·안건·날짜) (효과 중 / 재임베딩)
- [대기] H6 임베딩 모델 교체: `BAAI/bge-m3`, `dragonkue/BGE-m3-ko` (효과 불명 / 재임베딩 2회)
- [대기] H7 청크 점수의 문서 집계 방식: 최고점 대신 상위 n개 합 등 (효과 소 / 비용 없음)
- [대기] H8 질의 재작성·HyDE (dev 질의를 무료 쿼터로 보낼 수 있다(D-10). 질의 전체 재작성은 호출 수·소요 시간을 보고하고 승인 후)
- [대기] H9 다중 크기 청킹: 한 문서를 여러 크기(예: 256·512·1024)로 나눠 함께 검색하고 문서 순위로 합침. 자료는 S4 `data/runs/chunk_sweep.json`과 dev-small 네 인덱스 (효과 중 / 재임베딩)
- [대기] H10 생성 컨텍스트 단위: 청크 / 앞뒤 청크 확장 / 문서 전체 비교 (DECISIONS D-05). 생성 평가를 SPEC에 추가한 뒤 시험 (효과 미상 / 재임베딩 없음)

순서는 예상 효과 대비 비용 순이다. 실험 결과가 나올 때마다 다시 정렬한다. 결과 수치는 EXPERIMENTS.md에 둔다.

## 이후 단계

- [ ] G2 질의 문서 특정 가능성 보조 분석: 검색 단계 종료 시, 검색 결과를 보지 않은 채 dev 무작위 표본을 "질의만으로 정답 문서를 특정할 수 있는가"로 사람이 검수하고, 특정 가능한 질의에서의 Recall@5를 주 지표와 따로 보고한다. 주 지표와 질의 집합은 바꾸지 않는다 (DECISIONS D-09)
- 생성 단계 평가: 검색 단계 종료(test 1회 보고) 후 SPEC을 개정해 지표를 정하고, 그 뒤 백로그를 만든다.
- 배포(HF Spaces): 생성 단계 이후 조각으로 추가한다.
