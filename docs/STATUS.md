# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-011 설정(D-29). EXP-009(snowflake-ko hybrid + 조건 목록 + 최다 일치 필터 + 법률명 조건)의 dense에 256/32 청크를 더함. dev-full Recall@5 0.9337, Recall@1 0.8369, multi-doc Recall@5 0.9514. 실행 `rag.search +exp=exp011`(조건은 실행 때 추출, S12)
- 이번 세션: EXP-011 채택(D-29), S12 인덱스 경로·공유 검색기(`rag.retrieve`)·덮어쓰기 방지, D-30(검색 질의당 3초), D-31(재배포 제한은 공개 금지, 외부 API 처리 허용), 하네스 ADR-0038\~0040, colab CLI 공식 main d4f855d로 설치(Windows)
- 진행 중 EXP: 012 문장 경계 청킹(H4, `exp/exp012-sentence-chunk`), 013 질의 재작성(H8, 초안만, `exp/exp013-query-rewrite`)

## 실행 중 작업
- 없음. EXP-012 Colab 세션 `meet-rag-exp012`(L4)는 08:41 UTC에 회수됐다(07:24\~08:41, 약 2.0 CU 요율 환산). full 임베딩을 마친 뒤 다운로드 중 커널 비활성으로 회수된 것으로 추정하고, VM의 full 인덱스를 잃었다(`_workspace/exp012_main_progress.md`)

## 이번 세션 결정
- EXP-012: BM25도 문장 경계 청크로, 청킹은 로컬(`index.chunk_only`)에서 하고 VM은 임베딩만
- EXP-013: 재작성 판단 규칙 ③(dense·BM25 상위 5 교집합 없음 또는 dense 1위−10위 점수 차 ≤ 0.0588, 라벨 미사용), Gemma 4 31B(실험 OpenRouter, 배포 Google, `rewriter` config), 사고 과정 끔, 지시 `rw_v1`, 재작성 1개
- 하네스: 커널은 PR 전 stop, CU는 요율 환산, 기록된 노트북 보존, 판정과 무관한 원인 분석, 구현 원칙(과거 코드 병용 금지·덮어쓰기 방지·설정 의존 입력은 실행 시점)

## 다음 행동
1. [B] EXP-012 재개(`exp/exp012-sentence-chunk`): 새 L4 세션 할당은 사용자 승인 뒤(약 50분, 약 1.3 CU 요율 환산). 로컬 `data/index/snowflake-ko-sentence-{512-64,256-32}/full/chunks.jsonl` 업로드 → full 512 임베딩 → 바로 회수 → 256 임베딩 → 바로 회수. 다운로드 중에는 짧은 exec를 1\~2분마다 보내 커널을 깨운다. dev-small 인덱스는 로컬에 있고 dev-small 결과는 EXP-011과 같았다(R@5 0.9865). 이어서 dev-full·multi-doc 검색, exp-judge·감사, 원인 분석 노트북(21_xx), PR
2. [B] EXP-013 구현(`exp/exp013-query-rewrite`, 초안 확정): 사용자 착수 지시를 받은 뒤 시작한다. EXP-012가 채택되면 기준과 B′ 임계값을 라벨 없이 다시 계산해 문서에 적는다. dev-small 작동 확인(Google 경로 10개 지연 포함) → 신호 C 결정 → dev-full(승인)
3. [F] 하네스 대기 목록 3건: 승인 없이 EXP 구현 착수(B2 규칙 보강), D-31에 맞춘 평가 질의 전송 점검(protocol-guard P6 등), 새 CLI 다운로드 중 세션 회수(`colab_job.py fetch`에 커널 깨우기)
4. [C] 원격 브랜치 정리(사용자): `chore/colab-cli-main-windows`, `chore/harness-notebook-impl-rules`

## 사용자 확인 필요
- EXP-012 Colab 재할당 승인
- EXP-013 신호 C(조건이 문서를 좁히지 못함)를 넣을지: dev-small 작동 확인 뒤
- BM25 청크 구성(256 추가)을 PLAN 백로그에 올릴지
