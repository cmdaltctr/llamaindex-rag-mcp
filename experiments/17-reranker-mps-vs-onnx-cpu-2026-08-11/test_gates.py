#!/usr/bin/env python3
"""Focused tests for Experiment 17.

Tests the pure logic functions in run_eval.py: gate calculations (H1 to H5),
device assertions, repetition keys, ranking comparison, and checkpoint resume.

These tests do NOT require torch, onnxruntime, sentence-transformers, or any
model downloads. They exercise the coordinator's aggregation and gate logic
with synthetic data.

Run: uv run pytest experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/test_gates.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import (  # noqa: E402
    aggregate_repetitions,
    assert_device,
    evaluate_gates,
    get_completed_reps,
    rankings_match,
    repetition_key,
    save_repetition_result,
)

# ── Helpers ───────────────────────────────────────────────────────────


def _rep(
    cell_id: str,
    rep: int,
    *,
    p50: float = 100.0,
    p95: float = 200.0,
    cold_start: float = 1.0,
    peak_rss: float = 500.0,
    loaded: bool = True,
    selected_device: str = "cpu",
    rankings: list[list[int]] | None = None,
) -> dict:
    if rankings is None:
        rankings = [[0, 1, 2, 3, 4] for _ in range(5)]
    return {
        "cell_id": cell_id,
        "repetition": rep,
        "loaded": loaded,
        "selected_device": selected_device,
        "p50_query_ms": p50,
        "p95_query_ms": p95,
        "cold_start_s": cold_start,
        "peak_rss_mb": peak_rss,
        "rankings": rankings,
    }


_KEY_MAP = {
    "p50": "p50_query_ms",
    "p95": "p95_query_ms",
    "cold_start": "cold_start_s",
    "peak_rss": "peak_rss_mb",
}


def _agg(**overrides: object) -> dict:
    """Aggregated cell dict with sensible defaults."""
    base: dict[str, object] = {
        "p50_query_ms": 100.0,
        "p95_query_ms": 200.0,
        "cold_start_s": 1.0,
        "peak_rss_mb": 500.0,
        "loaded": True,
        "selected_device": "cpu",
        "rankings": [[0, 1, 2, 3, 4] for _ in range(5)],
    }
    for k, v in overrides.items():
        base[_KEY_MAP.get(k, k)] = v
    return base


# ── repetition_key ────────────────────────────────────────────────────


class TestRepetitionKey:
    def test_format(self):
        assert repetition_key("17A", 1) == "17A_rep1"

    def test_different_cells_differ(self):
        assert repetition_key("17A", 1) != repetition_key("17B", 1)

    def test_different_reps_differ(self):
        assert repetition_key("17A", 1) != repetition_key("17A", 2)


# ── evaluate_gates ────────────────────────────────────────────────────


class TestEvaluateGates:
    def test_all_pass(self):
        """H1 to H5 all pass when MPS is fast and rankings match."""
        gates = evaluate_gates(
            _agg(p50=100, p95=200, cold_start=1, peak_rss=500),
            _agg(p50=100),
            _agg(p50=50, p95=150, cold_start=2, peak_rss=800, selected_device="mps"),
        )
        assert gates["H1"]["pass"] is True
        assert gates["H2"]["pass"] is True
        assert gates["H3"]["pass"] is True
        assert gates["H4"]["pass"] is True
        assert gates["H5"]["pass"] is True
        assert gates["overall"]["pass"] is True

    def test_h1_fail_device_not_mps(self):
        gates = evaluate_gates(_agg(), _agg(), _agg(selected_device="cpu"))
        assert gates["H1"]["pass"] is False

    def test_h1_fail_not_loaded(self):
        gates = evaluate_gates(_agg(), _agg(), _agg(loaded=False, selected_device="mps"))
        assert gates["H1"]["pass"] is False

    def test_h2_fail_not_20pct_faster(self):
        """70 ms vs 80 ms torch CPU: 70 > 0.8*80 = 64."""
        gates = evaluate_gates(
            _agg(p50=100),
            _agg(p50=80),
            _agg(p50=70, selected_device="mps"),
        )
        assert gates["H1"]["pass"] is True
        assert gates["H2"]["pass"] is False

    def test_h2_boundary_exactly_20pct(self):
        """80 ms vs 100 ms: 80 == 0.8*100, passes."""
        gates = evaluate_gates(
            _agg(p50=100),
            _agg(p50=100),
            _agg(p50=80, selected_device="mps"),
        )
        assert gates["H2"]["pass"] is True

    def test_h3_fail_p95_exceeds(self):
        """P50 passes but P95 200 > 150."""
        gates = evaluate_gates(
            _agg(p50=100, p95=150),
            _agg(p50=100),
            _agg(p50=50, p95=200, selected_device="mps"),
        )
        assert gates["H3"]["pass"] is False

    def test_h4_fail_cold_start(self):
        """Cold start 4 > 3*1."""
        gates = evaluate_gates(
            _agg(cold_start=1, peak_rss=500),
            _agg(),
            _agg(cold_start=4, peak_rss=800, selected_device="mps"),
        )
        assert gates["H4"]["pass"] is False

    def test_h4_fail_rss(self):
        """RSS 1100 > 2*500."""
        gates = evaluate_gates(
            _agg(cold_start=1, peak_rss=500),
            _agg(),
            _agg(cold_start=2, peak_rss=1100, selected_device="mps"),
        )
        assert gates["H4"]["pass"] is False

    def test_h5_fail_ranking_mismatch_bc(self):
        """17B vs 17C differ on query 0."""
        r = [[0, 1, 2, 3, 4] for _ in range(5)]
        r_c = [row[:] for row in r]
        r_c[0] = [1, 0, 2, 3, 4]
        gates = evaluate_gates(
            _agg(rankings=r),
            _agg(rankings=r),
            _agg(rankings=r_c, selected_device="mps"),
        )
        assert gates["H5"]["pass"] is False

    def test_h5_fail_ranking_mismatch_ac(self):
        """17A vs 17C differ on query 0."""
        r = [[0, 1, 2, 3, 4] for _ in range(5)]
        r_c = [row[:] for row in r]
        r_c[0] = [1, 0, 2, 3, 4]
        gates = evaluate_gates(
            _agg(rankings=r),
            _agg(rankings=r_c),
            _agg(rankings=r_c, selected_device="mps"),
        )
        assert gates["H5"]["pass"] is False

    def test_overall_fail_when_any_gate_fails(self):
        gates = evaluate_gates(
            _agg(p50=100, p95=200, cold_start=1, peak_rss=500),
            _agg(p50=100),
            _agg(p50=50, p95=150, cold_start=2, peak_rss=800, selected_device="cpu"),
        )
        assert gates["overall"]["pass"] is False
        assert gates["overall"]["verdict"] != "PASS"


# ── aggregate_repetitions ─────────────────────────────────────────────


class TestAggregateRepetitions:
    def test_median_p50(self):
        """Median of [100, 120, 130] = 120, not mean 116.67."""
        reps = [_rep("17A", i, p50=v) for i, v in enumerate([100, 130, 120], 1)]
        assert aggregate_repetitions(reps)["p50_query_ms"] == 120

    def test_median_p95(self):
        reps = [_rep("17A", i, p95=v) for i, v in enumerate([200, 220, 210], 1)]
        assert aggregate_repetitions(reps)["p95_query_ms"] == 210

    def test_median_cold_start(self):
        reps = [_rep("17A", i, cold_start=v) for i, v in enumerate([1.0, 3.0, 2.0], 1)]
        assert aggregate_repetitions(reps)["cold_start_s"] == 2.0

    def test_median_peak_rss(self):
        reps = [_rep("17A", i, peak_rss=v) for i, v in enumerate([400, 600, 500], 1)]
        assert aggregate_repetitions(reps)["peak_rss_mb"] == 500

    def test_preserves_cell_id(self):
        reps = [_rep("17C", i) for i in range(1, 4)]
        assert aggregate_repetitions(reps)["cell_id"] == "17C"

    def test_rankings_from_first_successful_rep(self):
        rankings = [[i for i in range(20)] for _ in range(5)]
        reps = [_rep("17A", i, rankings=rankings) for i in range(1, 4)]
        assert aggregate_repetitions(reps)["rankings"] == rankings

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No repetitions"):
            aggregate_repetitions([])


# ── assert_device ─────────────────────────────────────────────────────


class TestAssertDevice:
    def test_correct_device_passes(self):
        assert_device({"selected_device": "mps"}, "mps")

    def test_wrong_device_raises(self):
        with pytest.raises(AssertionError, match="expected mps"):
            assert_device({"selected_device": "cpu"}, "mps")

    def test_missing_device_raises(self):
        with pytest.raises(KeyError, match="selected_device"):
            assert_device({}, "mps")


# ── rankings_match ────────────────────────────────────────────────────


class TestRankingsMatch:
    def test_identical(self):
        assert rankings_match([[0, 1], [2, 3]], [[0, 1], [2, 3]]) is True

    def test_different_order(self):
        assert rankings_match([[0, 1, 2]], [[1, 0, 2]]) is False

    def test_different_num_queries(self):
        assert rankings_match([[0, 1]], [[0, 1], [2, 3]]) is False

    def test_empty_matches_empty(self):
        assert rankings_match([], []) is True


# ── checkpoint resume ─────────────────────────────────────────────────


class TestCheckpointResume:
    def test_detects_completed(self, tmp_path):
        save_repetition_result(tmp_path, "17A_rep1", {"cell_id": "17A"})
        save_repetition_result(tmp_path, "17B_rep2", {"cell_id": "17B"})
        completed = get_completed_reps(tmp_path)
        assert completed == {"17A_rep1", "17B_rep2"}

    def test_empty_dir(self, tmp_path):
        assert get_completed_reps(tmp_path) == set()

    def test_resume_logic(self, tmp_path):
        """Simulates --resume: completed reps are skipped."""
        save_repetition_result(tmp_path, "17A_rep1", {"cell_id": "17A"})
        save_repetition_result(tmp_path, "17A_rep2", {"cell_id": "17A"})
        completed = get_completed_reps(tmp_path)
        all_keys = {repetition_key("17A", r) for r in range(1, 4)}
        assert all_keys - completed == {"17A_rep3"}

    def test_atomic_write_no_tmp_left(self, tmp_path):
        save_repetition_result(tmp_path, "17A_rep1", {"cell_id": "17A"})
        assert (tmp_path / "17A_rep1.json").exists()
        assert not (tmp_path / "17A_rep1.json.tmp").exists()

    def test_file_content_round_trips(self, tmp_path):
        payload = {"cell_id": "17C", "repetition": 3, "p50_query_ms": 42.0}
        save_repetition_result(tmp_path, "17C_rep3", payload)
        loaded = json.loads((tmp_path / "17C_rep3.json").read_text())
        assert loaded["p50_query_ms"] == 42.0
