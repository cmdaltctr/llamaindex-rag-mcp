"""Pre-run plan validator tests for Experiment 5b (OpenSpec task 1.4).

Tests-only artefact: ``validate_plan.py`` does not exist yet, so module
loading fails (red) until the implementation lands.  Loads the module via
importlib because the experiment directory is not a package (same pattern
as the Experiment 5 harness tests).  No network, no model downloads, no
torch imports -- pure stdlib json/pathlib against the committed plan.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
PLAN_PATH = EXP_DIR / "plan.json"

EXPECTED_GATE_IDS = [
    "G1a",
    "G1b",
    "G1c",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
    "G9",
]
ALL_CELL_IDS = {
    "onnx_cpu_in_process",
    "torch_mps_fresh",
    "torch_mps_persistent",
    "torch_cpu_persistent",
    "torch_cpu_fresh",
}
PERSISTENT_CELL_IDS = {"torch_mps_persistent", "torch_cpu_persistent"}


def _load_validator() -> types.ModuleType:
    """Load validate_plan.py from the experiment directory by file path."""
    spec = importlib.util.spec_from_file_location(
        "exp5b_validate_plan", EXP_DIR / "validate_plan.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["exp5b_validate_plan"] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _real_plan() -> dict:
    """Return a fresh parse of the committed plan (never the file on disk)."""
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _gate(plan: dict, gate_id: str) -> dict:
    """Return the gate dict with the given id from a plan payload."""
    return next(g for g in plan["gate_table"] if g["id"] == gate_id)


# ── Scenario 1: the real, committed plan is valid ─────────────────────


def test_real_plan_validates() -> None:
    """validate_plan on the untouched plan.json payload returns no errors."""
    assert validator.validate_plan(_real_plan()) == []


# ── Scenario 2: gate enumeration ──────────────────────────────────────


def test_enumeration_covers_all_gates_in_order() -> None:
    """enumerate_gates lists all 11 gates in plan order with resolved cells."""
    gates = validator.enumerate_gates(_real_plan())
    assert [g["id"] for g in gates] == EXPECTED_GATE_IDS

    g1a = gates[0]
    assert g1a["treatment_cells"] == ["torch_mps_persistent"]
    assert g1a["control_precisions"] == ["torch_fp32"]

    g1c = gates[2]
    assert len(g1c["treatment_cells"]) == 5
    assert set(g1c["treatment_cells"]) == ALL_CELL_IDS
    # pseudo-targets resolve to the pseudo string, never a fabricated backend
    assert g1c["control_backends"] == ["declared_plan"]

    g2 = gates[3]
    assert g2["thresholds"]["parent_observed_median_latency_ratio_max"] == 0.8

    g3 = gates[4]
    assert g3["control_backends"] == ["onnx"]

    g6 = gates[7]
    assert set(g6["treatment_cells"]) == PERSISTENT_CELL_IDS

    revision = _real_plan()["controlled_variables"]["model_revision"]
    for gate in gates:
        assert gate["model_revision"] == revision
        assert isinstance(gate["row_population"], str) and gate["row_population"]
        assert isinstance(gate["estimator"], str) and gate["estimator"]
        assert isinstance(gate["thresholds"], dict)


# ── Scenarios 3-7: rejection rules ────────────────────────────────────


def test_cross_backend_parity_gate_rejected() -> None:
    """A parity gate whose cells resolve to onnx vs torch backends is rejected."""
    plan = _real_plan()
    _gate(plan, "G1a")["control"] = "onnx_cpu_in_process"
    errors = validator.validate_plan(plan)
    assert errors, "ONNX-versus-Torch parity gate must be rejected"
    assert any("G1a" in e for e in errors)


def test_parity_fraction_below_one_rejected() -> None:
    """A parity gate with ranking_equality_fraction_min != 1.0 is rejected."""
    plan = _real_plan()
    _gate(plan, "G1a")["ranking_equality_fraction_min"] = 0.99
    errors = validator.validate_plan(plan)
    assert errors and any("G1a" in e for e in errors)


def test_missing_latency_threshold_rejected() -> None:
    """A latency-ratio gate missing its threshold field is rejected."""
    plan = _real_plan()
    del _gate(plan, "G2")["parent_observed_median_latency_ratio_max"]
    errors = validator.validate_plan(plan)
    assert errors and any("G2" in e for e in errors)


def test_unknown_treatment_cell_rejected() -> None:
    """A gate naming a cell id absent from the cells table is rejected."""
    plan = _real_plan()
    _gate(plan, "G1b")["treatment"] = "torch_mps_mystery"
    errors = validator.validate_plan(plan)
    assert errors and any("G1b" in e for e in errors)


def test_todo_local_marker_rejected_anywhere() -> None:
    """Any string containing TODO-LOCAL is rejected, wherever it sits."""
    plan = _real_plan()
    plan["controlled_variables"]["request_deadline_seconds"] = "TODO-LOCAL"
    assert validator.validate_plan(plan), "TODO-LOCAL must be rejected"

    plan = _real_plan()
    _gate(plan, "G9")["required_outcome"] = "resolve TODO-LOCAL before run"
    assert validator.validate_plan(plan), "TODO-LOCAL inside gates must be rejected"


def test_model_revision_must_be_pinned_40_hex() -> None:
    """model_revision must exist, hold no TODO marker, and be 40 hex chars."""
    for bad in ("unpinned", "TODO", "233902d"):
        plan = _real_plan()
        plan["controlled_variables"]["model_revision"] = bad
        assert validator.validate_plan(plan), f"model_revision={bad!r} must be rejected"

    plan = _real_plan()
    del plan["controlled_variables"]["model_revision"]
    assert validator.validate_plan(plan), "absent model_revision must be rejected"


# ── Scenario 8: CLI contract ──────────────────────────────────────────


def test_cli_accepts_real_plan() -> None:
    """main() returns 0 for the committed plan.json."""
    assert validator.main([str(PLAN_PATH)]) == 0


def test_cli_rejects_invalid_plan(tmp_path: Path) -> None:
    """main() returns 1 for a plan file that fails validation."""
    plan = _real_plan()
    _gate(plan, "G1a")["ranking_equality_fraction_min"] = 0.5
    bad_path = tmp_path / "plan.json"
    bad_path.write_text(json.dumps(plan), encoding="utf-8")
    assert validator.main([str(bad_path)]) == 1


def test_cli_missing_file_returns_one(tmp_path: Path) -> None:
    """main() returns 1 with an error for an unreadable path."""
    assert validator.main([str(tmp_path / "does_not_exist.json")]) == 1


# ── Scenario 9: over-rejection guard ──────────────────────────────────


def test_cross_backend_latency_gate_is_allowed() -> None:
    """A torch-vs-onnx latency-ratio gate (G3) is legal and never indicted.

    Guards against the parity rule over-reaching into ratio gates: G3 keeps
    different backends on purpose (deployment comparison, per its own
    interpretation field).
    """
    plan = _real_plan()
    gates = validator.enumerate_gates(plan)
    g3 = next(g for g in gates if g["id"] == "G3")
    assert g3["treatment_backends"] == ["torch"]
    assert g3["control_backends"] == ["onnx"]
    assert validator.validate_plan(plan) == []

    # even when the parity gate G1a is invalid, G3 must not be flagged
    _gate(plan, "G1a")["control"] = "onnx_cpu_in_process"
    errors = validator.validate_plan(plan)
    assert any("G1a" in e for e in errors)
    assert not any("G3" in e for e in errors)
