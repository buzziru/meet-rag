# EXPERIMENTS (평가 프로토콜 v1: SPEC 기준)

dev-full Recall@5, 기준 대비 차이는 회의 단위 paired bootstrap 95% 구간. multi-doc은 전체 Recall@5 차이다. 판정에는 쓰지 않고, 메타데이터 가설만 single-doc이 보류일 때 multi-doc으로 판정한다(SPEC "메타데이터 가설의 판정", D-18). 그 경우 Complete@5 조건은 EXP 문서 결론에 적는다.

| EXP | 기준 | 바꾼 것 | dev-full R@5 | 차이 (95% 구간) | multi-doc R@5 차이 | 판정 |
| --- | --- | --- | ---: | --- | --- | --- |
| 001 | base | hybrid: dense + BM25(Kiwi) RRF(k 60, 깊이 100) | 0.9168 | +5.84%p [+4.93, +6.76] | −3.21%p [−5.03, −1.42] | 채택 |
| base | - | S5 dense (KURE-v1, 512/64, 전수 검색) | 0.8584 | - | - | - |
