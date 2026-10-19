import pytest

from rag.g2 import final_class, rank_type


@pytest.mark.parametrize("ranks, expected", [
    ({"dense": 3, "bm25": 40}, "결합 손실"),
    ({"dense": 12, "bm25": None}, "근접"),
    ({"dense": 25, "bm25": None, "conditions": None}, "전 목록 실패"),
    ({"dense": None, "bm25": None}, "전 목록 실패"),
])
def test_rank_type_uses_best_list_rank(ranks, expected):
    assert rank_type(ranks, 5, 20) == expected


@pytest.mark.parametrize("identifiable, other, expected", [
    (True, False, "개선 가능"),
    (False, False, "좁힐 수 없음"),
    (True, True, "좁힐 수 없음"),
])
def test_final_class(identifiable, other, expected):
    assert final_class({"identifiable": identifiable}, {"other_answer": other}) == expected
