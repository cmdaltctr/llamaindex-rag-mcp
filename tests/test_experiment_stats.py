"""Fast tests for the Stage 4 statistical output contract (task 4.4)."""

from __future__ import annotations

import pytest
from experiments._lib.stats import (
    VALID_CELL_STATUSES,
    cell_record,
    finalise_cells,
    paired_bootstrap_ci,
    split_warmup,
    validate_per_query_rows,
)


def _row(
    *,
    cell_id: str = "dense_off",
    query_id: str = "q1",
    phase: str = "measured",
    latency_ms: float = 12.5,
    metrics: dict | None = None,
) -> dict:
    return {
        "cell_id": cell_id,
        "query_id": query_id,
        "phase": phase,
        "latency_ms": latency_ms,
        "metrics": metrics if metrics is not None else {"coverage_at_20": 0.5},
    }


def test_validate_per_query_rows_accepts_good_rows() -> None:
    validate_per_query_rows([_row(phase="warmup"), _row(phase="measured", query_id="q2")])


def test_validate_per_query_rows_names_offending_row_and_field() -> None:
    rows = [_row(), _row()]
    del rows[1]["query_id"]

    with pytest.raises(ValueError, match=r"row 1.*query_id"):
        validate_per_query_rows(rows)

    rows = [_row(), _row(phase="hot")]
    with pytest.raises(ValueError, match=r"row 1.*phase"):
        validate_per_query_rows(rows)

    rows = [_row(), _row(latency_ms="fast")]
    with pytest.raises(ValueError, match=r"row 1.*latency_ms"):
        validate_per_query_rows(rows)

    rows = [_row(), _row(metrics=[0.5])]
    with pytest.raises(ValueError, match=r"row 1.*metrics"):
        validate_per_query_rows(rows)


def test_split_warmup_partitions_and_preserves_order() -> None:
    rows = [
        _row(query_id="q1", phase="warmup"),
        _row(query_id="q1", phase="measured"),
        _row(query_id="q2", phase="warmup"),
        _row(query_id="q2", phase="measured"),
    ]

    warmup, measured = split_warmup(rows)

    assert [row["query_id"] for row in warmup] == ["q1", "q2"]
    assert all(row["phase"] == "warmup" for row in warmup)
    assert [row["query_id"] for row in measured] == ["q1", "q2"]
    assert all(row["phase"] == "measured" for row in measured)


def test_paired_bootstrap_ci_identical_sequences_straddle_zero() -> None:
    values = [float(i) for i in range(20)]

    result = paired_bootstrap_ci(values, values, n_resamples=2000, seed=42)

    assert result["delta"] == 0.0
    assert result["ci_low"] <= 0.0 <= result["ci_high"]


def test_paired_bootstrap_ci_is_deterministic_for_a_seed() -> None:
    a = [float(i % 7) for i in range(25)]
    b = [float((i * 3) % 5) for i in range(25)]

    first = paired_bootstrap_ci(a, b, n_resamples=2000, seed=7)
    second = paired_bootstrap_ci(a, b, n_resamples=2000, seed=7)

    assert first == second


def test_paired_bootstrap_ci_constant_shift_excludes_zero() -> None:
    b = [float(i) * 1.5 + 2.0 for i in range(30)]
    a = [value + 1.0 for value in b]

    result = paired_bootstrap_ci(a, b, n_resamples=2000, seed=42)

    assert result["delta"] == pytest.approx(1.0)
    assert result["ci_low"] > 0.9
    assert result["ci_high"] < 1.1


def test_paired_bootstrap_ci_rejects_mismatched_and_empty_inputs() -> None:
    with pytest.raises(ValueError, match="equal-length"):
        paired_bootstrap_ci([1.0, 2.0], [1.0], n_resamples=100, seed=1)

    with pytest.raises(ValueError, match="at least one pair"):
        paired_bootstrap_ci([], [], n_resamples=100, seed=1)


def test_paired_bootstrap_ci_reports_sample_size() -> None:
    result = paired_bootstrap_ci([1.0, 2.0, 3.0], [3.0, 2.0, 1.0], n_resamples=100, seed=3)

    assert result["n"] == 3
    assert result["confidence"] == 0.95


def test_cell_record_complete_without_reason() -> None:
    record = cell_record(status="complete", coverage_at_20=0.62)

    assert record == {"status": "complete", "reason": None, "coverage_at_20": 0.62}


def test_cell_record_requires_reason_for_invalid_status() -> None:
    with pytest.raises(ValueError, match="reason"):
        cell_record(status="invalid")

    assert cell_record(status="invalid", reason="store write failed")["reason"] == (
        "store write failed"
    )
    with pytest.raises(ValueError, match="reason"):
        cell_record(status="incomplete", reason="   ")


def test_cell_record_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unknown cell status.*aborted"):
        cell_record(status="aborted", reason="hung")

    assert "aborted" not in VALID_CELL_STATUSES


def test_cell_record_preserves_extra_fields() -> None:
    record = cell_record(
        status="complete",
        coverage_at_20=0.61,
        latency_ms_p95=184.2,
        artefacts=["per_query.jsonl"],
    )

    assert record["coverage_at_20"] == 0.61
    assert record["latency_ms_p95"] == 184.2
    assert record["artefacts"] == ["per_query.jsonl"]


def test_finalise_cells_marks_missing_status_incomplete() -> None:
    cells = [{"cell_id": "dense_off", "coverage_at_20": 0.5}]

    finalised = finalise_cells(cells)

    assert finalised == [
        {
            "cell_id": "dense_off",
            "coverage_at_20": 0.5,
            "status": "incomplete",
            "reason": "missing status",
        }
    ]
    assert "status" not in cells[0]


def test_finalise_cells_preserves_existing_statuses() -> None:
    cells = [
        {"cell_id": "a", "status": "complete", "reason": None},
        {"cell_id": "b", "status": "invalid", "reason": "runner killed mid-cell"},
    ]

    finalised = finalise_cells(cells)

    assert [record["status"] for record in finalised] == ["complete", "invalid"]
    assert finalised[1]["reason"] == "runner killed mid-cell"


def test_finalise_cells_rejects_unknown_status_and_missing_reason() -> None:
    with pytest.raises(ValueError, match="unknown cell status"):
        finalise_cells([{"cell_id": "a", "status": "aborted"}])

    with pytest.raises(ValueError, match="reason"):
        finalise_cells([{"cell_id": "a", "status": "incomplete"}])


def test_finalise_cells_does_not_mutate_inputs() -> None:
    cells = [{"cell_id": "a"}, {"cell_id": "b", "status": "complete", "reason": None}]
    snapshots = [dict(cell) for cell in cells]

    finalise_cells(cells)

    assert cells == snapshots
