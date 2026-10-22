import pytest

from rag.sample_review import sample_qids


def test_sample_qids_is_deterministic_sorted_and_order_independent():
    qids = [f"q{i:03d}" for i in range(50)]
    picked = sample_qids(qids, seed=1, n=10)

    assert picked == sorted(picked)
    assert len(set(picked)) == 10 and set(picked) <= set(qids)
    assert sample_qids(list(reversed(qids)), seed=1, n=10) == picked


def test_main_stops_before_reading_when_sample_exists(tmp_path, monkeypatch):
    from omegaconf import OmegaConf

    import rag.sample_review as sr
    sample = tmp_path / "g1.csv"
    sample.write_text("qid\n", encoding="utf-8")
    # 표본 경로만 둔 config. 멈추지 않으면 없는 paths.splits를 읽다 다른 오류가 난다
    monkeypatch.setattr(sr, "compose", lambda **_: OmegaConf.create(
        {"paths": {"g1_sample": sample.as_posix()}}))
    with pytest.raises(SystemExit, match="g1.csv"):
        sr.main()
    assert sample.read_text(encoding="utf-8") == "qid\n"
