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


def test_measured_run_preserves_dry_run_preflight_green(tmp_path) -> None:
    """Regression: the measured run must not clobber dry-run all_green evidence.

    The 2026-08-22 campaign launched after a green ``--dry-run`` in the same
    output directory, but the measured path rewrote ``preflight/_summary.json``
    without ``probes_green``/``all_green`` and G9 reported "preflight not
    green" despite every probe passing before the first measured row.
    """
    import json

    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "_summary.json").write_text(
        json.dumps({"all_green": True, "probes_green": True}), encoding="utf-8"
    )
    summary = {
        "plan_agreement": True,
        "routes_green": True,
        "parent_torch_free": True,
    }
    merged = run_eval.merge_prior_preflight_green(summary, tmp_path)
    assert merged["probes_green"] is True
    assert merged["all_green"] is True

    # A prior summary that was not green, or absent, must not invent flags.
    (preflight_dir / "_summary.json").write_text(json.dumps({"all_green": False}), encoding="utf-8")
    fresh = {
        "plan_agreement": True,
        "routes_green": True,
        "parent_torch_free": True,
    }
    assert "all_green" not in run_eval.merge_prior_preflight_green(fresh, tmp_path)
    empty_dir = tmp_path / "elsewhere"
    empty_dir.mkdir()
    assert "all_green" not in run_eval.merge_prior_preflight_green(dict(fresh), empty_dir)


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
