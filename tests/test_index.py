import numpy as np

from rag.index import embed_shards, load_embeddings, token_batches


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
