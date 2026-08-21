"""Fast tests for stats_extras (OpenSpec task 4.1) — RED until implemented.

Deterministic pure-stdlib statistics: Theil-Sen slope with the <2 distinct-x
guard, linear-interpolation percentiles, sustained-crossover detection
(including the cross-then-recross case), seeded block-bootstrap determinism
and a flat-series bound, plus the tolerance-comparison helpers used by the
correctness projection.  No model, no network.
"""

from __future__ import annotations

import math

from _lazy_module import LazyModule

se = LazyModule("stats_extras")  # RED (ModuleNotFoundError) until implemented


# ── theilsen_slope ────────────────────────────────────────────────────


def test_theilsen_exact_linear_slope() -> None:
    x = [1, 2, 3, 4, 5]
    y = [2 * xi + 1 for xi in x]
    assert se.theilsen_slope(x, y) == 2.0


def test_theilsen_robust_to_single_outlier() -> None:
    x = [1, 2, 3, 4, 5, 6, 7]
    y = [2.0 * xi + 1.0 for xi in x]
    y[3] = 1000.0  # one corrupt point; the median of slopes survives
    assert se.theilsen_slope(x, y) == 2.0


def test_theilsen_requires_two_distinct_x() -> None:
    try:
        se.theilsen_slope([1, 1, 1], [1.0, 2.0, 3.0])
        raise AssertionError("fewer than two distinct x values must raise")
    except ValueError:
        pass


# ── percentile ────────────────────────────────────────────────────────


def test_percentile_known_values_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert se.percentile(values, 0.0) == 1.0
    assert se.percentile(values, 0.25) == 1.75
    assert se.percentile(values, 0.5) == 2.5
    assert se.percentile(values, 0.75) == 3.25
    assert se.percentile(values, 1.0) == 4.0
    assert se.percentile([7.0], 0.5) == 7.0


# ── first_sustained_crossover ─────────────────────────────────────────


def test_crossover_immediate() -> None:
    assert se.first_sustained_crossover([10, 9, 8], [10, 10, 10]) == 1.0


def test_crossover_delayed() -> None:
    assert se.first_sustained_crossover([12, 11, 5, 5], [10, 10, 10, 10]) == 3.0


def test_crossover_never_is_infinite() -> None:
    assert se.first_sustained_crossover([11, 11], [10, 10]) == math.inf


def test_crossover_recross_returns_later_sustained_n() -> None:
    # Crosses at n=1, breaks at n=2 (7 > 6), then stays below: the answer
    # is the later sustained start, 3 — not the transient first crossing.
    persistent = [5, 7, 5, 5]
    baseline = [5, 6, 6, 6]
    assert se.first_sustained_crossover(persistent, baseline) == 3.0


def test_crossover_equality_counts_as_no_greater() -> None:
    # "no greater than" includes equality, so the equal start sustains.
    assert se.first_sustained_crossover([5, 5], [5, 5]) == 1.0


# ── seeded block bootstrap ────────────────────────────────────────────


def test_slope_bootstrap_deterministic_under_seed() -> None:
    x = list(range(60))
    y = [0.5 * xi + 2.0 for xi in x]

    first = se.block_bootstrap_slope_upper_bound(x, y, seed=20260821)
    second = se.block_bootstrap_slope_upper_bound(x, y, seed=20260821)
    assert first == second
    assert set(first) == {"slope", "upper_bound", "n_resamples", "confidence"}
    assert first["slope"] == 0.5
    assert first["n_resamples"] == 1000
    assert first["confidence"] == 0.95
    assert first["upper_bound"] >= first["slope"]

    # Perfectly linear data is seed-invariant by construction (every resample
    # has slope exactly 0.5), so seed sensitivity is asserted on stepped data
    # (blocks with different slopes) at a quantile where composition matters.
    # Theil-Sen's median robustness can collapse seed differences at the
    # median itself; 0.75 separates them on this fixed fixture.
    split = 40
    stepped = [0.5 * xi + 2.0 for xi in x[:split]] + [
        0.7 * xi + 2.0 - 0.2 * split for xi in x[split:]
    ]
    stepped_first = se.block_bootstrap_slope_upper_bound(x, stepped, seed=20260821, confidence=0.75)
    stepped_other = se.block_bootstrap_slope_upper_bound(x, stepped, seed=1, confidence=0.75)
    assert stepped_first == se.block_bootstrap_slope_upper_bound(
        x, stepped, seed=20260821, confidence=0.75
    )
    assert stepped_first["upper_bound"] != stepped_other["upper_bound"]


def test_slope_bootstrap_flat_series_bound_is_small() -> None:
    x = list(range(60))
    y = [100.0 + (0.01 if i % 2 else -0.01) for i in x]
    result = se.block_bootstrap_slope_upper_bound(x, y, seed=20260821)
    assert abs(result["slope"]) < 0.01
    assert result["upper_bound"] < 0.5  # near-flat growth stays near zero


def test_stat_bootstrap_shape_and_determinism() -> None:
    x = list(range(60))
    y = [float(i % 2) for i in x]

    def spread(xs: list[float], ys: list[float]) -> float:
        return max(ys) - min(ys)

    first = se.block_bootstrap_stat_upper_bound(spread, x, y, seed=20260821)
    second = se.block_bootstrap_stat_upper_bound(spread, x, y, seed=20260821)
    assert first == second
    assert first["upper_bound"] >= 1.0  # any resample keeps the 0/1 spread
    assert first["n_resamples"] == 1000
    assert first["confidence"] == 0.95


def test_stat_bootstrap_allows_infinite_stat() -> None:
    """A stat_fn returning math.inf must flow through without crashing."""
    x = list(range(20))
    y = [float(i) for i in x]

    def sometimes_inf(xs: list[float], ys: list[float]) -> float:
        return math.inf

    result = se.block_bootstrap_stat_upper_bound(sometimes_inf, x, y, seed=20260821)
    assert result["upper_bound"] == math.inf


# ── tolerance-comparison helpers (task 4.3 semantics) ─────────────────


def test_paired_max_abs_delta() -> None:
    a = {"d0": 0.5, "d1": 0.25}
    assert se.paired_max_abs_delta(a, {"d0": 0.5, "d1": 0.25}) == 0.0
    delta = se.paired_max_abs_delta(a, {"d0": 0.50005, "d1": 0.25})
    assert abs(delta - 5e-5) < 1e-12


def test_rankings_equal() -> None:
    assert se.rankings_equal(["a", "b", "c"], ["a", "b", "c"]) is True
    assert se.rankings_equal(["a", "b"], ["b", "a"]) is False
    assert se.rankings_equal(["a"], ["a", "b"]) is False


def test_tolerance_comparison_semantics() -> None:
    """Fresh-inference equality is tolerance-based, never byte equality."""
    tol = 1e-4
    baseline_scores = {"d0": 0.9, "d1": 0.8}
    drifted_scores = {"d0": 0.90005, "d1": 0.79996}
    assert se.paired_max_abs_delta(baseline_scores, drifted_scores) <= tol
    assert se.rankings_equal(["d0", "d1"], ["d0", "d1"])

    beyond = {"d0": 0.9002, "d1": 0.8}
    assert se.paired_max_abs_delta(baseline_scores, beyond) > tol
