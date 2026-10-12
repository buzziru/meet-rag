from omegaconf import OmegaConf

from rag.rerank import jev_body


def test_jev_body_one_question_per_candidate():
    jv = OmegaConf.create({"model": "m", "instructions": "답하는가?", "levels": ["a", "b"]})
    group = [{"query": "q", "text": f"t{i}", "doc_id": f"d{i}"} for i in range(2)]
    body = jev_body(group, jv)
    assert body["state"] == {"query": "q", "candidates": {"0": "t0", "1": "t1"}}
    assert body["questions"]["c1"] == {"type": "score", "instructions": "후보 1: 답하는가?",
                                       "criteria": ["a", "b"]}
