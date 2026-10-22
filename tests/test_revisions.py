"""HF 모델·토크나이저의 revision 고정 점검(D-46).

고정을 빠뜨리면 같은 설정이 다른 가중치를 받아 재현되지 않는다. 불러오는 코드는 revision을
rag.index.pinned로만 넘기고(config 키가 어디든 받기 전에 멈춤), 알려진 config는 pytest에서도 본다.
"""

import ast

import pytest
from omegaconf import OmegaConf

from rag.index import COMMIT, ROOT, load_cfg, pinned

EXPS = sorted(p.stem for p in (ROOT / "configs" / "exp").glob("exp*.yaml"))
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


def _is_pinned(node) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", None) == "pinned"


def test_loader_calls_pass_pinned_revision():
    """HF 로딩 호출은 revision=pinned(...)만 받는다. `.get("revision")`처럼 빠진 값을 None으로
    넘기는 식이면 새 모델의 config에 revision이 없어도 오류 없이 main을 받는다."""
    bad = []
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            rev = next((k.value for k in node.keywords if k.arg == "revision"), None)
            if name in LOADERS and not _is_pinned(rev):
                bad.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
    assert not bad, bad


@pytest.mark.parametrize("section", [
    {"model": "org/new-model"},  # revision 키가 없음
    {"model": "org/new-model", "revision": None},
    {"model": "org/new-model", "revision": "main"},
    {"model": "org/new-model", "revision": "8b418a5"},  # 짧은 해시
])
def test_pinned_stops_without_commit(section):
    with pytest.raises(SystemExit, match="revision"):
        pinned(OmegaConf.create(section))


def test_pinned_returns_commit():
    rev = "8b418a58414668e75532ed045c22d9ca018ae2b2"
    assert pinned(OmegaConf.create({"model_name": "m", "revision": rev})) == rev
