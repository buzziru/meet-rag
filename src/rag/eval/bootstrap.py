"""회의 단위 paired bootstrap과 판정. 규칙은 docs/SPEC.md "판정"."""

import numpy as np


def paired_bootstrap(diff, groups, n_resamples: int, seed: int, alpha: float):
    """질의별 차이를 회의 단위로 복원 추출해 (점 추정, 하한, 상한)을 낸다."""
    diff = np.asarray(diff, dtype=float)
    keys, idx = np.unique(np.asarray(groups), return_inverse=True)  # 회의 정렬
    sums = np.bincount(idx, weights=diff, minlength=len(keys))
    counts = np.bincount(idx, minlength=len(keys))

    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(keys), size=(n_resamples, len(keys)))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(diff.mean()), float(lo), float(hi)


def verdict(point: float, lo: float, hi: float, min_gain: float) -> str:
    if lo > 0 and point >= min_gain:
        return "채택"
    if hi < 0:
        return "기각"
    return "보류"


def metadata_verdict(single: str, recall5: tuple[float, float, float], complete5_hi: float,
                     min_gain: float) -> dict:
    """메타데이터 가설의 판정(docs/SPEC.md "메타데이터 가설의 판정", D-18, S18).

    single-doc 판정이 채택·기각이면 그대로 두고, 보류이면 multi-doc Recall@5 차이
    (점 추정, 하한, 상한)로 판정하되 Complete@5 차이 구간 상한이 0보다 작으면 채택하지 않는다.
    +1.0%p 미만이고 하한 > 0인 보류를 예외로 올릴지는 사용자가 정한다(D-35). 여기서는 보류만 낸다.
    """
    if single != "보류":
        return {"verdict": single, "stage": "single-doc"}
    v = verdict(*recall5, min_gain)
    if v == "채택" and complete5_hi < 0:
        v = "보류"
    return {"verdict": v, "stage": "multi-doc"}
