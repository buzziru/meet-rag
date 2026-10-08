# EXPERIMENTS (평가 프로토콜 v1: SPEC 기준)

dev-full Recall@5, 기준 대비 차이는 회의 단위 paired bootstrap 95% 구간. multi-doc의 R@5는 Recall@5, C@5는 Complete@5이고 구간은 `pool_id` 단위 95% 구간이다. 판정 단계는 판정이 정해진 평가다: single-doc(SPEC 판정 절) 또는 multi-doc(메타데이터 가설이 single-doc 보류일 때, SPEC "메타데이터 가설의 판정", D-18). multi-doc 단계 채택은 test로 다시 확인할 수 없다.

| EXP | 기준 | 바꾼 것 | dev-full R@5 | 차이 (95% 구간) | multi-doc R@5 차이 (95% 구간) | multi-doc C@5 차이 (95% 구간) | 판정 (단계) |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 002 | 001 | BM25 문서에 메타데이터 6개 필드(date·committee_name·meeting_name·meeting_number·session_number·agenda) 접두 | 0.8906 | −2.62%p [−4.02, −1.39] | +15.32%p [+13.19, +17.49] | +13.50%p [+10.67, +16.50] | 기각 (single-doc) |
| 001 | base | hybrid: dense + BM25(Kiwi) RRF(k 60, 깊이 100) | 0.9168 | +5.84%p [+4.93, +6.76] | −3.21%p [−5.03, −1.42] | −1.83%p [−4.17, +0.50] | 채택 (single-doc) |
| base | - | S5 dense (KURE-v1, 512/64, 전수 검색) | 0.8584 | - | - | - | - |
