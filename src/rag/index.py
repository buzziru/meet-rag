"""범위(dev-small·full)의 문서를 청킹·임베딩해 인덱스 디렉터리에 저장한다.

임베딩은 조각(shard) 단위로 저장하고, 이미 있는 조각은 건너뛰어 끊긴 작업을 잇는다.
명세는 docs/slices/04-index.md. 인자는 Hydra override (예: chunking.chunk_tokens=512).
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from functools import cache
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from rag.chunking import make_chunker

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = "chunks.jsonl"  # 인덱스 디렉터리의 청크 파일. 줄 순서가 임베딩 행 순서다

# HF_HOME은 .env에서 읽는다. transformers를 import하기 전에 정해야 캐시 위치가 바뀐다
load_dotenv(ROOT / ".env")
if os.environ.get("HF_HOME") and not Path(os.environ["HF_HOME"]).is_absolute():
    os.environ["HF_HOME"] = str(ROOT / os.environ["HF_HOME"])


def load_cfg(overrides=()):
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        return compose(config_name="config", overrides=list(overrides))


def corpus_meta(cfg) -> list[dict]:
    """코퍼스 문서 목록(본문 context 제외). 한 프로세스에서 같은 파일은 한 번만 읽는다.

    조건 색인·조건 추출기·생성의 회의 정보가 같이 쓴다. 전체 코퍼스 읽기는 한 번에 8~11초라
    셋이 따로 읽으면 실행마다 그만큼 반복됐다(S17). 파일이 바뀌면(수정 시각·크기) 다시 읽는다.
    돌려준 목록과 dict는 공유하므로 고치지 않는다.
    """
    path = ROOT / cfg.paths.corpus
    st = path.stat()
    return _read_corpus_meta(path, st.st_mtime_ns, st.st_size)


@cache
def _read_corpus_meta(path: Path, mtime_ns: int, size: int) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [{k: v for k, v in json.loads(line).items() if k != "context"} for line in f]


def git_state() -> tuple[str, bool]:
    """(HEAD 커밋, 추적 파일에 커밋하지 않은 변경이 있는지). 생성·judge 레시피에 남긴다."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8").stdout.strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain", "--untracked-files=no"))


OVERWRITE_HINT = "retriever.run_name·경로를 확인하고, 바꾸려면 search.overwrite=true"


def write_guarded(path: Path, text: str, overwrite: bool, hint: str = OVERWRITE_HINT) -> str:
    """실험 산출물(순위·후보 쌍·점수·지문·분할 파일)을 쓴다. 같은 경로에 내용이 다른 파일이 있으면
    overwrite가 아닐 때 멈춘다(S12, S15).

    run_name을 빠뜨린 실행이 과거 실험 기록(판정 기준 등)을 되돌릴 수 없게 덮어쓰지 않게 한다.
    """
    if path.exists() and not overwrite:
        if path.read_text(encoding="utf-8") == text:
            return "같은 내용, 그대로 둠"
        raise SystemExit(f"{path}에 내용이 다른 파일이 있다. {hint}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return "씀"


def refuse_existing(path: Path, overwrite: bool) -> None:
    """작업 전에 출력이 이미 있으면 멈춘다. 다시 만들면 내용이 달라지는 산출물(채점, 측정, judge
    기록)은 끝에 write_guarded로 멈추면 작업 시간을 잃으므로 시작할 때 본다(S15, PR #122 리뷰)."""
    if path.exists() and not overwrite:
        raise SystemExit(f"{path}가 있다. 덮어쓰려면 search.overwrite=true")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_basis(path: Path, expect: dict) -> None:
    """산출물을 만든 설정(지문 파일 path)이 expect와 같은지 본다. expect의 키만 대조한다(S15)."""
    if not path.exists():
        raise SystemExit(f"{path}가 없다. 산출물을 만든 설정을 실행 기록과 "
                         "대조한 뒤 adopt_basis=true로 지문을 쓴다(S15)")
    have = json.loads(path.read_text(encoding="utf-8"))
    diff = sorted(k for k in expect if have.get(k) != expect[k])
    if diff:
        raise SystemExit(f"{path}의 지문이 지금 설정과 다르다({', '.join(diff)})")


def index_basis(cfg, chunking) -> dict:
    """인덱스를 읽을 때 대조하는 지문. 만들 때는 index_build_basis로 더 많이 대조한다."""
    return {"model": cfg.embedding.model_name, "revision": cfg.embedding.get("revision"),
            "chunking": OmegaConf.to_container(OmegaConf.create(chunking), resolve=True),
            "scope": cfg.index.scope}


def index_build_basis(cfg) -> dict:
    small = cfg.index.scope == "dev-small"
    return {**index_basis(cfg, cfg.chunking), "max_docs": cfg.index.max_docs,
            "shard_size": cfg.index.shard_size,
            "corpus_sha256": file_sha256(ROOT / cfg.paths.corpus),
            "dev_small_sha256": file_sha256(ROOT / cfg.paths.dev_small_docs) if small else None}


def index_path(cfg, chunking) -> Path:
    """청킹 설정 하나(name, chunk_tokens, overlap_tokens)로 paths.index_dir 템플릿을 푼 경로.

    인덱스 경로는 이 함수에서만 만든다(S12). 추가 청크 인덱스(retriever.extra_chunks)도 같다.
    """
    merged = OmegaConf.merge(cfg, {"chunking": OmegaConf.to_container(OmegaConf.create(chunking))})
    return ROOT / merged.paths.index_dir


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
    """청크를 shard_size개씩 임베딩해 out_dir/part-NNNNN.npy로 쓴다. 있는 조각은 행 수만 보고
    건너뛴다(shard_size를 바꿔 재개하면 행 수가 달라 멈춘다, S15)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for k, start in enumerate(range(0, len(texts), shard_size)):
        path = out_dir / f"part-{k:05d}.npy"
        part_texts = texts[start : start + shard_size]
        if path.exists():
            rows = np.load(path, mmap_mode="r").shape[0]
            if rows != len(part_texts):
                raise SystemExit(f"{path.name}의 행 수 {rows}가 조각 {k}의 청크 수 "
                                 f"{len(part_texts)}와 다르다. index.shard_size를 확인한다")
            continue
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

    model = SentenceTransformer(cfg.embedding.model_name, device=cfg.embedding.device,
                                revision=cfg.embedding.get("revision"))
    model.max_seq_length = min(max_seq_length, model.max_seq_length)
    if cfg.embedding.dtype == "float16":
        model = model.to(torch.float16)
    return model


def encoder(model, cfg, prompt: str | None = None):
    """prompt는 텍스트 앞에 붙이는 접두다(질의 전용 접두 모델, EXP-009)."""
    def encode(texts):
        return model.encode(texts, batch_size=len(texts), convert_to_numpy=True, prompt=prompt,
                            normalize_embeddings=cfg.embedding.normalize).astype(np.float32)
    return encode


def main() -> None:
    cfg = load_cfg(sys.argv[1:])
    ch = cfg.chunking
    index_dir = index_path(cfg, ch)
    index_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    chunks_path = index_dir / CHUNKS
    basis_path = index_dir / "basis.json"
    basis = index_build_basis(cfg)
    if cfg.adopt_basis:  # 지문 없는 기존 인덱스에 지문만 쓰고 끝낸다. 모델을 불러오지 않는다
        if not chunks_path.exists():
            raise SystemExit(f"{chunks_path}가 없다")
        with chunks_path.open(encoding="utf-8") as f:
            n_rows = sum(1 for _ in f)
        n_emb = sum(np.load(p, mmap_mode="r").shape[0]
                    for p in sorted((index_dir / "emb").glob("part-*.npy")))
        if n_rows != n_emb:  # 행 수가 다른 인덱스에는 지문을 쓰지 않는다
            raise SystemExit(f"청크 {n_rows}개와 임베딩 {n_emb}행이 다르다")
    if not basis_path.exists() and (cfg.adopt_basis or not chunks_path.exists()):
        # 새 인덱스이거나, 지문 없는 기존 인덱스를 지금 설정으로 만들었다고 사용자가 확인한 경우
        basis_path.write_text(json.dumps(basis, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    check_basis(basis_path, basis)
    if cfg.adopt_basis:
        print(f"지문 확인 -> {basis_path} (청크 {n_rows:,}개)")
        return

    if cfg.index.chunk_only:  # 청크만 만든다. 모델 없이 같은 토크나이저만 불러온다(EXP-012)
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(cfg.embedding.model_name,
                                                  revision=cfg.embedding.get("revision"))
    else:
        model = load_model(cfg, ch.chunk_tokens + 2)  # 특수 토큰 2개
        tokenizer = model.tokenizer
    if not chunks_path.exists():
        rows = []
        chunker = make_chunker(ch, tokenizer)
        for d in scope_docs(cfg):
            for start, end, n in chunker(d["context"]):
                rows.append({"chunk_id": len(rows), "doc_id": d["doc_id"], "start": start,
                             "end": end, "n_tokens": n, "text": d["context"][start:end]})
        tmp = chunks_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(chunks_path)
    with chunks_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    if cfg.index.chunk_only:
        took = time.time() - started
        print(f"{len(rows):,} chunks -> {chunks_path.relative_to(ROOT)} ({took:.0f}s)")
        return

    made = embed_shards([r["text"] for r in rows], [r["n_tokens"] for r in rows],
                        index_dir / "emb", cfg.index.shard_size, encoder(model, cfg),
                        cfg.embedding.max_batch_tokens, cfg.embedding.max_batch_size)
    emb = load_embeddings(index_dir)
    if len(emb) != len(rows):
        raise SystemExit(f"청크 {len(rows)}개와 임베딩 {len(emb)}행이 다르다")
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
