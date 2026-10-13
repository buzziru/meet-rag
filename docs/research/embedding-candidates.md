# 한국어 검색 임베딩 후보 조사 (H6, 2026-10-13)

H6(임베딩 모델 교체) 후보를 고르려고 공개 벤치마크와 모델 카드를 조사한 기록이다. EXP-009(snowflake-ko)가 채택되지 않으면 아래 후보에서 다음 변형을 고른다(사용자 결정 2026-10-13).

## 조건

- Hugging Face 오픈 가중치, 상업·연구 사용 가능 라이선스
- Colab L4(24GB) float16으로 청크 118,039개를 임베딩할 수 있는 크기. 운영에서 질의 임베딩을 CPU에서 할 수 있어야 해 작을수록 유리하다
- 현재 모델 `nlpai-lab/KURE-v1`(bge-m3를 한국어로 미세조정, 568M, 1024차원)과 같은 표에서 비교한 근거를 우선한다

## 후보 표

출처: ① KURE-v2 모델 카드의 MTEB(kor, v2) Retrieval 9과제 평균 nDCG@10(단일 벡터 행은 공식 MTEB 결과 저장소 값, KURE-v2 행은 KURE 팀 측정), ② ko-embedding-leaderboard v2 7과제 NDCG@5·@10 평균(제3자), ③ snowflake-ko 모델 카드 7과제 평균 nDCG@10(작성자 자체), ④ pplx-embed 논문 MIRACL-ko HN nDCG@10. 출처마다 과제 구성이 달라 같은 출처 안의 차이만 비교한다. ①과 ③의 snowflake-ko·KURE-v1·bge-m3 수치는 모델 카드에서 직접 확인했고, 나머지는 조사 에이전트가 옮긴 값이다.

| 모델 | 방식·크기 | 라이선스 | ① | ② | ③·④ | 접두 | 판단 |
|---|---|---|---|---|---|---|---|
| nlpai-lab/KURE-v1 (현재) | dense 568M | MIT | 0.7616 | 80.76 | ③ 0.7277 | 없음 | 기준 |
| dragonkue/snowflake-arctic-embed-l-v2.0-ko | dense 568M, XLM-R | Apache-2.0 | 0.7653 | 82.14 | ③ 0.7404 | 질의 `query: ` | EXP-009 |
| perplexity-ai/pplx-embed-v1-0.6b | dense 596M, Qwen3 | MIT | 없음 | 없음 | ④ 70.3 | 없음 | 다음 변형 1순위 후보 |
| telepix/PIXIE-Spell-v1.5-0.6B | dense 0.6B, Qwen3 | Apache-2.0 | 없음 | 없음 | 자체 표 MTEB(ko) 6과제 0.7717(bge-m3 0.7483, KURE-v1 없음) | 질의 `prompt_name="query"` | 다음 변형 후보 |
| Qwen/Qwen3-Embedding-4B | dense 4B | Apache-2.0 | 0.7737 | 81.37 | | 질의 `Instruct: …\nQuery:` | 제외(CPU 질의 임베딩이 무겁고 Colab 비용 수 배) |
| telepix/PIXIE-Rune-v1.5 | dense 568M | Apache-2.0 | 0.7618 | | | 질의 `prompt_name="query"` | 제외(KURE-v1과 동률) |
| Qwen/Qwen3-Embedding-0.6B | dense 0.6B | Apache-2.0 | | 75.88 | ③ 0.6762 | 질의 instruct | 제외(KURE-v1보다 낮음) |
| google/embeddinggemma-300m | dense 303M | Gemma 약관 | | 78.19 | | 질의·문서 접두 | 제외(KURE-v1보다 낮음) |
| BAAI/bge-m3, dragonkue/BGE-m3-ko | dense 568M | MIT 등 | 0.7509, 0.7547 | 79.30 | ③ bge-m3 0.7242 | 없음 | 제외(모두 KURE-v1보다 낮음, 기존 백로그 후보) |
| nlpai-lab/KURE-v2 | late-interaction 154M, ModernBERT | Apache-2.0 | 0.8160 | | | 없음 | 아이디어로만 기록(아래) |
| jinaai/jina-embeddings-v5-text-small | dense | CC-BY-NC-4.0 | | 80.29 | | | 제외(비상업 라이선스) |

## snowflake-ko를 고른 이유

- 같은 표 비교 세 출처가 모두 KURE-v1보다 높다(+0.4\~1.4%p). 차이가 SPEC 채택 기준(+1.0%p)과 비슷한 크기라 우리 데이터에서는 차이가 없을 수 있다
- 구조가 KURE-v1과 같아(XLM-R 568M, 1024차원) 인프라·비용이 그대로다. 토크나이저도 KURE-v1과 같아(어휘 250,002개 일치, 청크 2,000개 토큰화 일치) 청크와 BM25 색인을 재사용한다
- 계열 다양성은 약하다. Arctic-Embed 2.0 large는 bge-m3 계열 체크포인트에서 출발했다고 한다(조사 에이전트가 논문에서 확인)

## KURE-v2를 채택하지 않은 이유 (사용자 결정 2026-10-13)

- 1차 검색기로: 청크마다 토큰 수만큼 128차원 벡터를 저장해 dense 인덱스(404MB)의 약 5배(PLAID 2비트 압축)\~33배(fp16 원본)가 된다(코퍼스 평균 436토큰 기준 추정). MaxSim을 지원하는 벡터스토어로 선택지가 좁아지고 운영 제약이 생긴다
- 리랭커로: 질의마다 후보를 인코딩하면 CPU 지연이 EXP-006의 CPU cross-encoder와 비슷한 수준으로 예상되고, 토큰 벡터를 미리 저장하면 저장 부담이 같다. cross-encoder(EXP-006)는 scale-to-zero 운영이면 비용 부담이 작고 기대 성능이 더 높아 시도할 필요가 낮다

## 다음 변형 후보를 쓸 때 주의

- pplx-embed-v1-0.6b와 PIXIE-Spell-v1.5-0.6B는 KURE-v1과 같은 표 비교가 없다. 우리 데이터에서 앞선다는 사전 근거 없이 계열 다양성(Qwen3)을 보고 시도하는 탐색이다
- pplx-embed-v1-0.6b는 `trust_remote_code=True`가 필요하고 토크나이저가 달라 청크를 다시 나눠야 할 수 있다(512 토큰 청크의 토크나이저 의존). 그러면 BM25 색인도 다시 만든다
- 모든 벤치마크가 위키·RAG 문서·법률·보건 분야라 구어체 회의록과 거리가 있다. 학습 데이터에 평가 과제가 섞였는지는 어느 모델도 명확히 밝히지 않았다

## 출처

- https://huggingface.co/nlpai-lab/KURE-v2
- https://huggingface.co/dragonkue/snowflake-arctic-embed-l-v2.0-ko
- https://github.com/OnAnd0n/ko-embedding-leaderboard
- https://arxiv.org/html/2602.11151v2 (pplx-embed)
- https://arxiv.org/html/2412.04506 (Arctic-Embed 2.0)
- https://huggingface.co/telepix/PIXIE-Spell-v1.5-0.6B, https://huggingface.co/telepix/PIXIE-Rune-v1.5
- https://huggingface.co/Qwen/Qwen3-Embedding-0.6B, https://huggingface.co/google/embeddinggemma-300m, https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b
