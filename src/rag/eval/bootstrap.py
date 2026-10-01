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
