# meet-rag

AI Hub 국회 회의록 데이터(1996\~2023년)로 만든 한국어 RAG 질의응답 데모다. 질문하면 회의록에서 근거를 찾아 답하고, 답변의 근거 번호를 누르면 해당 회의록 대목으로 이동한다. 왼쪽 문서 찾기에서 회의록을 직접 골라 읽을 수도 있다.

- 데모: https://meet-rag.vercel.app
- 프로젝트 회고: [RAG 내용](docs/retrospective/project-rag.md), [하네스와 운영](docs/retrospective/harness-and-operations.md)

## 응답 시간

무료 공유 GPU(Hugging Face ZeroGPU)에서 재정렬을 돌린다. 오랜만에 접속하면 서버가 깨어나는 데 약 1분이 걸린다.

질문을 보낸 때부터 답변 첫 글자가 나올 때까지를 기준으로 쟀다. 2026-11-06 공개 직후, 대화의 첫 질문 20개 중앙값은 2.80초다(목표 3초 이내). 공유 GPU라 재정렬이 가끔 늦어져 일부 질문은 3초를 넘는다(최대 8.50초). 앞 대화가 있는 후속 질문은 검색 질의를 한 번 고쳐 쓰는 과정이 더해져 중앙값 3.54초다. 측정 방법과 기록은 `docs/slices/41-public-launch.md`에 있다.
