# STATUS (세션 종료 시 덮어씀)

## 현재 위치
- 검색 기준: EXP-011 설정(D-29). EXP-009(snowflake-ko hybrid + 조건 목록 + 최다 일치 필터 + 법률명 조건)의 dense에 256/32 청크를 더함. dev-full Recall@5 0.9337, Recall@1 0.8369, multi-doc Recall@5 0.9514. 실행 `rag.search +exp=exp011`(조건은 실행 때 추출, S12)
- 이번 세션: EXP-012 문장 경계 청킹(H4) 보류. dev-full Recall@5 0.9350(+0.13%p [−0.23, +0.51]), multi-doc 변화 없음. 순위 이동은 dense가 양쪽으로 움직여 상쇄. 질의당 검색 p50 91.7ms, 콜드 스타트 35.4초. 기준 EXP-011 유지, H4 다음 변형 없음
- 병합 대기 PR: EXP-012(`exp/exp012-sentence-chunk`, 이 STATUS 포함)
- 진행 중 EXP: 013 질의 재작성(H8, 초안만, `exp/exp013-query-rewrite`)

## 실행 중 작업
- 없음(Colab 세션 없음). EXP-012 Colab은 두 세션 합계 약 165분, 약 4.3 CU(요율 환산). 1차 세션은 다운로드 중 회수돼 인덱스를 잃었다(EXP-012 실행 기록)
- EXP-012는 worktree `C:\workspace\meet-rag-exp012`에서 했다(`data/`·`_workspace/`는 원래 폴더 junction). PR 병합 뒤 `git worktree remove ../meet-rag-exp012`로 지운다(junction은 원래 폴더를 가리키므로 worktree 폴더만 지워진다)

## 이번 세션 결정
- EXP-012 보류: 성능 근거가 없고 재구축 CPU 청킹이 약 38분 늘어 D-28 예외 채택 근거도 없다고 판단(사용자 확인은 PR에서)
- PLAN 다음 순서(2026-10-14): H8 → H3 → H5 dense 접두
- 데이터는 그대로 두고 캐시만 확인(사용자): uv 캐시 7.7GB, HF 2.8GB(snowflake-ko 2.2GB, KURE-Reranker-nano 571MB). 정리는 사용자 결정 대기

## 다음 행동
1. [C] EXP-012 PR 리뷰·병합(사용자). 판단할 곳은 PR 본문 리뷰 가이드. 병합 뒤 worktree 제거
2. [B] EXP-013 구현(`exp/exp013-query-rewrite`, 초안 확정): 사용자 착수 지시를 받은 뒤 시작한다. 기준은 EXP-011 그대로라 B′ 임계값(0.0588)을 다시 계산하지 않는다. dev-small 작동 확인(Google 경로 10개 지연 포함) → 신호 C 결정 → dev-full(승인)
3. [F] 하네스 대기 목록: 승인 없이 EXP 구현 착수(B2 규칙 보강), D-31에 맞춘 평가 질의 전송 점검(protocol-guard P6 등), `colab_job.py fetch` 개선(다운로드 중 커널 깨우기, 압축 exec와 깨우기 겹침 회피, 무압축 tar, worktree junction, 로컬에 있는 파일은 받지 않기), 새 세션 직후 setup exec 시간 초과(restart-kernel 뒤 성공)
4. [C] 원격 브랜치 정리(사용자): `chore/colab-cli-main-windows`, `chore/harness-notebook-impl-rules`

## 사용자 확인 필요
- EXP-012 보류와 기준 유지(PR에서)
- 캐시 정리 여부: `uv cache prune`, KURE-Reranker-nano HF 캐시
- EXP-013 신호 C(조건이 문서를 좁히지 못함)를 넣을지: dev-small 작동 확인 뒤
- BM25 청크 구성(256 추가)을 PLAN 백로그에 올릴지
