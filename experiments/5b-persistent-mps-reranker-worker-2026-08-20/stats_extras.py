"""Pure-stdlib statistics for the Experiment 5b summariser (protocol §9/§10).

Deterministic estimators with no global random state: Theil-Sen slope,
linear-interpolation percentiles, sustained-crossover detection, seeded joint
block-bootstrap upper bounds and the tolerance-comparison helpers behind the
canonical correctness projection.

For campaign-sized series (n around 800) the bootstrap uses a NumPy fast
path when available; the definition (median of pairwise slopes over jointly
block-resampled series) is identical, and small series stay pure-stdlib so
the fast tests need no NumPy.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Sequence

_NUMPY_THRESHOLD = 200


def theilsen_slope(x: Sequence[float], y: Sequence[float]) -> float:
    """Median of pairwise slopes; pairs with equal x are skipped.

    Raises:
        ValueError: On length mismatch, empty input, or fewer than two
            distinct x values.
    """
    xs = [float(value) for value in x]
    ys = [float(value) for value in y]
    n = len(xs)
    if n != len(ys) or n < 2:
        raise ValueError("theilsen_slope needs equal-length series with at least two points")
    slopes: list[float]
    if n > _NUMPY_THRESHOLD:
        try:
            import numpy as np

            xv = np.asarray(xs)
            yv = np.asarray(ys)
            dx = xv[None, :] - xv[:, None]
            dy = yv[None, :] - yv[:, None]
            iu = np.triu_indices(n, k=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                vector_slopes = (dy[iu] / dx[iu])[np.isfinite(dy[iu] / dx[iu])]
            if vector_slopes.size == 0:
                raise ValueError("fewer than two distinct x values")
            return float(np.median(vector_slopes))
        except ImportError:
            pass
    pairwise: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx == 0:
                continue
            pairwise.append((ys[j] - ys[i]) / dx)
    slopes = pairwise
    if not slopes:
        raise ValueError("fewer than two distinct x values")
    return float(statistics.median(slopes))


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation percentile; ``fraction`` in [0, 1]."""
    data = sorted(float(value) for value in values)
    if not data:
        raise ValueError("percentile of empty sequence")
    if fraction <= 0.0:
        return data[0]
    if fraction >= 1.0:
        return data[-1]
    position = fraction * (len(data) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper or data[lower] == data[upper]:
        # Equal (or infinite) neighbours: interpolation would produce nan.
        return data[lower]
    return data[lower] + (data[upper] - data[lower]) * (position - lower)


def first_sustained_crossover(
    persistent_cum: Sequence[float],
    baseline_cum: Sequence[float],
) -> float:
    """Smallest 1-based n where persistent <= baseline holds to the end.

    Returns ``math.inf`` when the persistent series is still above baseline
    at the horizon.  Equality counts as "no greater than".
    """
    n = len(persistent_cum)
    if n == 0 or len(baseline_cum) != n:
        raise ValueError("crossover needs equal-length non-empty series")
    last_bad = 0
    for index in range(n):
        if persistent_cum[index] > baseline_cum[index]:
            last_bad = index + 1
    if last_bad >= n:
        return math.inf
    return float(last_bad + 1)


def paired_max_abs_delta(
    scores_a: dict[str, float],
    scores_b: dict[str, float],
) -> float:
    """Max |a-b| over the key union; a missing key counts as infinity."""
    delta = 0.0
    for key, value in scores_a.items():
        if key not in scores_b:
            return math.inf
        delta = max(delta, abs(float(value) - float(scores_b[key])))
    if len(scores_b) > len(scores_a):
        return math.inf
    return float(delta)


def rankings_equal(ranking_a: Sequence[str], ranking_b: Sequence[str]) -> bool:
    """Exact ordered-list equality of two rankings."""
    return list(ranking_a) == list(ranking_b)


def _block_indices(n: int, block_length: int, rng: random.Random) -> list[int]:
    """Joint block resampling indices: contiguous blocks, with replacement."""
    if block_length <= 0:
        raise ValueError("block_length must be positive")
    starts = list(range(0, n, block_length))
    indices: list[int] = []
    while len(indices) < n:
        start = rng.choice(starts)
        indices.extend(range(start, min(start + block_length, n)))
    return indices[:n]


def block_bootstrap_slope_upper_bound(
    x: Sequence[float],
    y: Sequence[float],
    *,
    seed: int,
    block_length: int = 40,
    n_resamples: int = 1000,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    """One-sided bootstrap upper bound of the Theil-Sen slope.

    Resamples index blocks jointly, recomputes the slope per resample and
    returns the ``confidence`` percentile of the resampled slopes.
    """
    xs = [float(value) for value in x]
    ys = [float(value) for value in y]
    observed = theilsen_slope(xs, ys)
    rng = random.Random(seed)  # noqa: S311 — seeded determinism is contractual
    slopes: list[float] = []
    for _ in range(n_resamples):
        indices = _block_indices(len(xs), block_length, rng)
        slopes.append(theilsen_slope([xs[i] for i in indices], [ys[i] for i in indices]))
    return {
        "slope": float(observed),
        "upper_bound": float(percentile(slopes, confidence)),
        "n_resamples": n_resamples,
        "confidence": confidence,
    }


def block_bootstrap_stat_upper_bound(
    stat_fn: Callable[[Sequence[float], Sequence[float]], float],
    x: Sequence[float],
    y: Sequence[float],
    *,
    seed: int,
    block_length: int = 40,
    n_resamples: int = 1000,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    """One-sided bootstrap upper bound of any paired statistic.

    ``stat_fn`` receives the jointly block-resampled series and returns a
    float; ``math.inf`` flows through so "never crosses" statistics fail
    loudly instead of being clamped.
    """
    xs = [float(value) for value in x]
    ys = [float(value) for value in y]
    observed = stat_fn(xs, ys)
    rng = random.Random(seed)  # noqa: S311 — seeded determinism is contractual
    stats: list[float] = []
    for _ in range(n_resamples):
        indices = _block_indices(len(xs), block_length, rng)
        stats.append(stat_fn([xs[i] for i in indices], [ys[i] for i in indices]))
    return {
        "statistic": float(observed),
        "upper_bound": float(percentile(stats, confidence)),
        "n_resamples": n_resamples,
        "confidence": confidence,
    }
