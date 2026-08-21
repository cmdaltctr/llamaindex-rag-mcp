"""Fast tests for run_eval's complete-lifetime resume semantics (task 4.1).

Resume reuses complete lifetimes only: a unit recorded in the checkpoint's
``completed`` list is skipped, while an interrupted unit (present in
``records`` but not ``completed``) restarts from request zero.  The
``lifetime``/attempt separation keeps any statistic from crossing PIDs.
No model, no network.
"""

from __future__ import annotations

import artefacts as art
import run_eval

TABLE = {
    1: ("torch_cpu_fresh", "torch_mps_persistent"),
    2: ("torch_mps_persistent", "torch_cpu_fresh"),
}


def test_all_units_pending_on_empty_checkpoint() -> None:
    pending = run_eval.pending_units(2, TABLE, [])
    assert pending == [
        ("torch_cpu_fresh", 1),
        ("torch_mps_persistent", 1),
        ("torch_mps_persistent", 2),
        ("torch_cpu_fresh", 2),
    ]


def test_complete_units_are_skipped_in_counterbalanced_order() -> None:
    completed = [
        art.checkpoint_key("torch_cpu_fresh", 1),
        art.checkpoint_key("torch_mps_persistent", 2),
    ]
    pending = run_eval.pending_units(2, TABLE, completed)
    assert pending == [
        ("torch_mps_persistent", 1),
        ("torch_cpu_fresh", 2),
    ]


def test_incomplete_unit_restarts_because_never_completed() -> None:
    """A record with status incomplete is evidence, not a resume token."""
    checkpoint = art.build_checkpoint(
        experiment_id="5b-persistent-mps-reranker-worker",
        plan_sha256="00" * 32,
        completed=[],  # the interrupted unit never completed
        records={
            art.checkpoint_key("torch_mps_persistent", 1): {
                "status": "incomplete",
                "reason": "parent interrupted mid-lifetime",
            }
        },
    )
    pending = run_eval.pending_units(2, TABLE, checkpoint["completed"])
    assert ("torch_mps_persistent", 1) in pending  # restarts from request zero


def test_checkpoint_statuses_validate_for_resume_records() -> None:
    """TDR-014 rule 8: interrupted units are status strings, never numeric."""
    try:
        art.build_checkpoint(
            experiment_id="x",
            plan_sha256="00" * 32,
            completed=[],
            records={"unit": {"status": "half-done"}},
        )
        raise AssertionError("invalid status must raise")
    except ValueError:
        pass
