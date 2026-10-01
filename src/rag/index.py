"""범위(dev-small·full)의 문서를 청킹·임베딩해 인덱스 디렉터리에 저장한다.

임베딩은 조각(shard) 단위로 저장하고, 이미 있는 조각은 건너뛰어 끊긴 작업을 잇는다.
명세는 docs/slices/04-index.md. 인자는 Hydra override (예: chunking.chunk_tokens=512).
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from hydra import compose, initialize_config_dir

from rag.chunking import chunk_text

ROOT = Path(__file__).resolve().parents[2]

# HF_HOME은 .env에서 읽는다. transformers를 import하기 전에 정해야 캐시 위치가 바뀐다
load_dotenv(ROOT / ".env")
if os.environ.get("HF_HOME") and not Path(os.environ["HF_HOME"]).is_absolute():
    os.environ["HF_HOME"] = str(ROOT / os.environ["HF_HOME"])


def load_cfg(overrides=()):
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        return compose(config_name="config", overrides=list(overrides))


def scope_docs(cfg) -> list[dict]:
    """범위의 문서를 doc_id 오름차순으로 읽는다."""
    keep = None
    if cfg.index.scope == "dev-small":
        keep = set((ROOT / cfg.paths.dev_small_docs).read_text(encoding="utf-8").split())
    elif cfg.index.scope != "full":
        raise ValueError(f"알 수 없는 범위: {cfg.index.scope}")
    docs = []
    with (ROOT / cfg.paths.corpus).open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if keep is None or d["doc_id"] in keep:
                docs.append({"doc_id": d["doc_id"], "context": d["context"]})
    docs.sort(key=lambda d: d["doc_id"])
    return docs[: cfg.index.max_docs] if cfg.index.max_docs else docs


def token_batches(lengths, max_batch_tokens: int, max_batch_size: int) -> list[list[int]]:
    """긴 것부터 정렬해, 배치 크기 × 배치 안 최대 길이가 상한을 넘지 않게 묶는다."""
    order = sorted(range(len(lengths)), key=lambda i: -lengths[i])
    batches, cur = [], []
    for i in order:
        width = lengths[cur[0]] if cur else lengths[i]  # 정렬돼 있어 첫 항목이 최대 길이
        if cur and ((len(cur) + 1) * width > max_batch_tokens or len(cur) == max_batch_size):
            batches.append(cur)
            cur = []
        cur.append(i)
    if cur:
        batches.append(cur)
    return batches


def embed_shards(texts, lengths, out_dir: Path, shard_size: int, encode, max_batch_tokens,
                 max_batch_size) -> int:
    """청크를 shard_size개씩 임베딩해 out_dir/part-NNNNN.npy로 쓴다. 있는 조각은 건너뛴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for k, start in enumerate(range(0, len(texts), shard_size)):
        path = out_dir / f"part-{k:05d}.npy"
        if path.exists():
            continue
        part_texts = texts[start : start + shard_size]
        part_lens = lengths[start : start + shard_size]
        emb = None
        for batch in token_batches(part_lens, max_batch_tokens, max_batch_size):
            vecs = encode([part_texts[i] for i in batch])
            if emb is None:
                emb = np.zeros((len(part_texts), vecs.shape[1]), dtype=np.float32)
            emb[batch] = vecs
        tmp = path.with_suffix(".tmp.npy")
        np.save(tmp, emb)
        tmp.replace(path)
        made += 1
        print(f"shard {k} ({start + len(part_texts)}/{len(texts)})", flush=True)
    return made


def load_embeddings(index_dir: Path) -> np.ndarray:
    return np.concatenate([np.load(p) for p in sorted((index_dir / "emb").glob("part-*.npy"))])


def load_model(cfg, max_seq_length: int):
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(cfg.embedding.model_name, device=cfg.embedding.device)
    model.max_seq_length = min(max_seq_length, model.max_seq_length)
    if cfg.embedding.dtype == "float16":
        model = model.to(torch.float16)
    return model


def encoder(model, cfg):
    def encode(texts):
        return model.encode(texts, batch_size=len(texts), convert_to_numpy=True,
                            normalize_embeddings=cfg.embedding.normalize).astype(np.float32)
    return encode


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    ch = cfg.chunking
    index_dir = ROOT / cfg.paths.index_dir
    index_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    model = load_model(cfg, ch.chunk_tokens + 2)  # 특수 토큰 2개
    chunks_path = index_dir / "chunks.jsonl"
    if not chunks_path.exists():
        rows = []
        for d in scope_docs(cfg):
            for start, end, n in chunk_text(model.tokenizer, d["context"], ch.chunk_tokens,
                                            ch.overlap_tokens):
                rows.append({"chunk_id": len(rows), "doc_id": d["doc_id"], "start": start,
                             "end": end, "n_tokens": n, "text": d["context"][start:end]})
        tmp = chunks_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(chunks_path)
    with chunks_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    made = embed_shards([r["text"] for r in rows], [r["n_tokens"] for r in rows],
                        index_dir / "emb", cfg.index.shard_size, encoder(model, cfg),
                        cfg.embedding.max_batch_tokens, cfg.embedding.max_batch_size)
    emb = load_embeddings(index_dir)
    meta_path = index_dir / "meta.json"
    before = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta = {
        "model": cfg.embedding.model_name, "scope": cfg.index.scope,
        "chunk_tokens": ch.chunk_tokens, "overlap_tokens": ch.overlap_tokens,
        "max_docs": cfg.index.max_docs, "n_docs": len({r["doc_id"] for r in rows}),
        "n_chunks": len(rows), "dim": int(emb.shape[1]), "device": cfg.embedding.device,
        "dtype": cfg.embedding.dtype, "shards_made": made,
        "seconds": round(before.get("seconds", 0) + time.time() - started, 1),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
