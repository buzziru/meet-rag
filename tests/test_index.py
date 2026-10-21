import json
import sys

import numpy as np
import pytest

from rag.index import embed_shards, index_path, load_cfg, load_embeddings, token_batches
from rag.index import main as index_main


def test_token_batches_respect_budget_and_cover_all():
    lengths = [5, 100, 30, 30, 8, 100, 1]
    batches = token_batches(lengths, max_batch_tokens=120, max_batch_size=3)

    assert sorted(i for b in batches for i in b) == list(range(len(lengths)))
    assert all(len(b) <= 3 for b in batches)
    assert all(len(b) * max(lengths[i] for i in b) <= 120 or len(b) == 1 for b in batches)


def fake_encode(texts):
    return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)


def test_embed_shards_keeps_order_and_resumes(tmp_path):
    texts = [f"t{'x' * i}" for i in range(7)]
    lengths = [len(t) for t in texts]
    args = dict(shard_size=3, max_batch_tokens=10, max_batch_size=2)

    assert embed_shards(texts, lengths, tmp_path / "emb", encode=fake_encode, **args) == 3
    full = load_embeddings(tmp_path)
    assert full[:, 0].tolist() == lengths

    (tmp_path / "emb" / "part-00001.npy").unlink()
    calls = []
    assert embed_shards(texts, lengths, tmp_path / "emb",
                        encode=lambda t: calls.append(t) or fake_encode(t), **args) == 1
    assert sum(len(c) for c in calls) == 3  # 지운 조각만 다시 만든다
    assert np.array_equal(load_embeddings(tmp_path), full)


def test_embed_shards_stops_when_shard_size_changes(tmp_path):
    texts = [f"t{i}" for i in range(7)]
    lengths = [2] * 7
    embed_shards(texts, lengths, tmp_path / "emb", 3, fake_encode, 10, 2)
    with pytest.raises(SystemExit, match="shard_size"):  # 조각 0은 3행인데 새 규칙으로는 4행
        embed_shards(texts, lengths, tmp_path / "emb", 4, fake_encode, 10, 2)


def _existing_index(tmp_path, n_emb=1):
    """지문 없는 기존 인덱스(S15 전)와 그 인덱스를 가리키는 명령 인자."""
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps({"doc_id": "d1", "context": "가나"}) + "\n", encoding="utf-8")
    template = (tmp_path / "${embedding.slug}-${chunking.chunk_tokens}" / "${index.scope}")
    args = [f"paths.index_dir='{template.as_posix()}'", f"paths.corpus='{corpus.as_posix()}'",
            "index.scope=full"]
    d = index_path(load_cfg(args), load_cfg(args).chunking)
    (d / "emb").mkdir(parents=True)
    (d / "chunks.jsonl").write_text(json.dumps({"doc_id": "d1", "text": "가나"}) + "\n",
                                    encoding="utf-8")
    np.save(d / "emb" / "part-00000.npy", np.zeros((n_emb, 2), dtype=np.float32))
    return d, args


def _run_index(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["rag.index", *args])
    index_main()


def test_index_without_basis_stops_until_adopted(tmp_path, monkeypatch):
    d, args = _existing_index(tmp_path)
    with pytest.raises(SystemExit, match="adopt_basis"):
        _run_index(monkeypatch, args)
    _run_index(monkeypatch, [*args, "adopt_basis=true"])  # 지문만 쓰고 모델은 불러오지 않는다
    basis = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    assert basis["scope"] == "full" and basis["max_docs"] is None and basis["corpus_sha256"]


def test_index_stops_when_settings_differ_from_basis(tmp_path, monkeypatch):
    d, args = _existing_index(tmp_path)
    _run_index(monkeypatch, [*args, "adopt_basis=true"])
    with pytest.raises(SystemExit, match="max_docs"):  # max_docs=20 인덱스를 전체로 쓰는 경우
        _run_index(monkeypatch, [*args, "index.max_docs=20"])
    (tmp_path / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="corpus_sha256"):  # 코퍼스를 다시 적재한 경우
        _run_index(monkeypatch, args)


def test_adopt_checks_chunk_and_embedding_rows(tmp_path, monkeypatch):
    d, args = _existing_index(tmp_path, n_emb=2)
    with pytest.raises(SystemExit, match="임베딩 2행"):
        _run_index(monkeypatch, [*args, "adopt_basis=true"])
    assert not (d / "basis.json").exists()  # 행 수가 다른 인덱스에는 지문을 남기지 않는다
