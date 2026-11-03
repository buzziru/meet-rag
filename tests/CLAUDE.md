# 테스트 규약

판정·동결·산출물 보호 코드(채점·비교·판정, 동결 대조, `data/` 덮어쓰기 방지)의 테스트에 적용한다.

- 사용자가 부르는 진입점(`main`, `search()`, 생성자)을 그대로 지나 결과 값을 단언한다. 내부 함수만 부르거나 생성자를 건너뛰면 진입점이 틀려도 통과한다(`docs/reviews/2026-10-test-review.md` T2-1, T3-1)
- 그 코드를 일부러 망가뜨린 사본에서 테스트가 실패하는지 한 번 확인한다. 저장소 파일은 고치지 않고 pytest 플러그인으로 사본을 끼운다(`docs/slices/30-test-fixes.md` 완료 기준 2). 예: `eval.compare.main`의 diff를 `base - cand`로 뒤집은 사본에서 `tests/test_eval.py`가 실패해야 한다
