"""BM25 검색기(EXP-001). dense 인덱스의 청크를 Kiwi 형태소로 토큰화해
bm25s 인덱스를 만들고 캐시한다.

설정은 retriever.bm25. 인덱스는 dense 인덱스 디렉터리의 bm25-{name}/에 둔다.
meta_fields가 있으면 문서 메타데이터를 청크 텍스트 앞에 붙여 색인한다(EXP-002).
"""

import json
from collections.abc import Iterable
from functools import cache
from pathlib import Path

import bm25s
import numpy as np
from kiwipiepy import Kiwi
from omegaconf import OmegaConf

from rag.index import CHUNKS, ROOT

# 인덱스를 만든 retriever.bm25 설정. 읽을 때 지금 설정과 다르면 멈춘다
# (이름만 같은 이전 인덱스를 조용히 읽지 않게)
SETTINGS = "settings.json"


def forms(kiwi: Kiwi, texts: Iterable[str], tags: set[str]):
    """텍스트마다 남길 품사의 형태 목록을 낸다. 불규칙 활용 표시(VV-R 등)는 떼고 비교한다."""
    for tokens in kiwi.tokenize(texts):
        yield [t.form for t in tokens if t.tag.split("-")[0] in tags]


def doc_meta(corpus_path: Path, fields) -> dict[str, str]:
    """문서마다 메타데이터 값을 공백으로 이은 문자열. 빈 값은 건너뛴다."""
    meta = {}
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            meta[d["doc_id"]] = " ".join(str(d[k]) for k in fields if d.get(k))
    return meta


def build(chunks_path: Path, out: Path, b, kiwi: Kiwi, meta: dict[str, str] | None = None) -> None:
    """청크를 스트리밍으로 토큰화해 id 배열(int32)로 쌓는다.

    형태 문자열 목록을 한꺼번에 들지 않아 로컬 RAM 8GB에서 전체 청크를 처리한다.
    meta가 있으면 청크 문서의 메타데이터 문자열을 텍스트 앞에 붙인다.
    """
    vocab: dict[str, int] = {}
    ids = []
    with chunks_path.open(encoding="utf-8") as f:
        rows = map(json.loads, f)
        if meta is None:
            texts = (r["text"] for r in rows)
        else:
            texts = (f"{meta[r['doc_id']]} {r['text']}" for r in rows)
        for doc in forms(kiwi, texts, set(b.tags)):
            ids.append(np.array([vocab.setdefault(w, len(vocab)) for w in doc], dtype=np.int32))
    model = bm25s.BM25(method=b.method, k1=b.k1, b=b.b)
    model.index((ids, vocab))
    model.save(out)


def write_settings(out: Path, settings: dict) -> None:
    text = json.dumps(settings, ensure_ascii=False, indent=2)
    (out / SETTINGS).write_text(text, encoding="utf-8")


@cache
def shared_kiwi() -> Kiwi:
    """프로세스에서 하나만 만든다. 생성과 첫 tokenize에 몇 초씩 들고(리뷰 E-1), tokenize만 쓰고
    사용자 사전을 더하지 않아 공유해도 토큰화 결과가 같다(S16)."""
    return Kiwi()


class BM25Retriever:
    def __init__(self, cfg, index_dir: Path):
        b = cfg.retriever.bm25
        self.tags = set(b.tags)
        self.kiwi = shared_kiwi()
        out = index_dir / f"bm25-{b.name}"
        settings = OmegaConf.to_container(b)
        if not (out / "params.index.json").exists():
            fields = b.get("meta_fields")
            meta = doc_meta(ROOT / cfg.paths.corpus, fields) if fields else None
            build(index_dir / CHUNKS, out, b, self.kiwi, meta)
            write_settings(out, settings)
        elif not (out / SETTINGS).exists():
            # 설정 기록 전에 만든 인덱스(kiwi-v1, kiwi-meta-v1).
            # 지금 설정으로 만들었다고 보고 한 번 기록한다
            write_settings(out, settings)
            print(f"{out.name}: 설정 기록이 없어 지금 설정을 {SETTINGS}에 기록함")
        else:
            saved = json.loads((out / SETTINGS).read_text(encoding="utf-8"))
            if saved != settings:
                raise SystemExit(
                    f"{out} 인덱스는 다른 retriever.bm25 설정으로 만들어졌다. "
                    f"설정을 바꾸면 bm25.name도 바꾼다\n저장: {saved}\n현재: {settings}"
                )
        self.model = bm25s.BM25.load(out, load_vocab=True)

    def query_ids(self, texts: list[str]) -> list[list[int]]:
        return [self.model.get_tokens_ids(doc) for doc in forms(self.kiwi, texts, self.tags)]

    def scores(self, ids: list[int]) -> np.ndarray:
        """청크마다 BM25 점수. 어휘에 있는 형태가 없는 질의는 모두 0이다."""
        return self.model.get_scores_from_ids(ids)
