"""HF 모델·토크나이저의 revision 고정 점검(D-46).

고정을 빠뜨리면 같은 설정이 다른 가중치를 받아 재현되지 않는다. config와 불러오는 코드를 함께 본다.
"""

import ast
import re

import pytest

from rag.index import ROOT, load_cfg

EXPS = sorted(p.stem for p in (ROOT / "configs" / "exp").glob("exp*.yaml"))
COMMIT = re.compile(r"[0-9a-f]{40}")
# HF에서 가중치·토크나이저를 받는 호출. 새 로더를 쓰면 여기에 더한다
LOADERS = {"SentenceTransformer", "CrossEncoder", "from_pretrained", "hf_hub_download",
           "snapshot_download"}


@pytest.mark.parametrize("exp", [None, *EXPS])
def test_hf_models_pin_commit(exp):
    cfg = load_cfg([f"+exp={exp}"] if exp else [])
    assert COMMIT.fullmatch(str(cfg.embedding.get("revision"))), "embedding.revision"
    rr = cfg.retriever.get("rerank")
    if rr is not None and rr.get("backend") == "cross-encoder":
        assert COMMIT.fullmatch(str(rr.get("revision"))), "retriever.rerank.revision"


def test_loader_calls_pass_revision():
    missing = []
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in LOADERS and not any(k.arg == "revision" for k in node.keywords):
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
    assert not missing, missing
