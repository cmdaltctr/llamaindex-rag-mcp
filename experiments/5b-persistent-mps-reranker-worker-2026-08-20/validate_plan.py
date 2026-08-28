"""Pre-run plan validator for Experiment 5b (OpenSpec task 1.4).

Enumerates every gate's exact cells, backend, precision, model revision, row
population, estimator and threshold from ``plan.json`` before any harness
code or measured work runs.  Rejects plans whose gates violate the registered
families, including the hard rule that a ranking-parity gate may never
compare an ONNX cell against a Torch cell: their divergence is registered
descriptive evidence (Experiment 5), not a correctness gate.

Pure stdlib; no model, no network.  Exit code 0 = plan is runnable,
1 = plan is invalid.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments._lib.plan import ExperimentPlan  # noqa: E402 — needs repo root first

SCRIPT_DIR = Path(__file__).resolve().parent
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

# Targets that legitimately name a rule or a probe set instead of a cell id.
PSEUDO_TARGETS = {
    "all",
    "all_cited_cells",
    "persistent_cells",
    "worker_death_worker_hang_pipe_pressure",
    "shutdown_eof_idle_expiry_parent_death",
    "registered_deadlines",
    "registered_lifecycle_bounds",
    "declared_plan",
    "declared_opt_in_budget",
    "zero_growth_direction",
    "TDR-014",
}

# Gate families: (family, signature fields, required fields, numeric fields,
# row population, estimator).  The first family whose signature field is
# present classifies the gate.  Numeric fields are threshold/estimator values;
# the rest are descriptive strings whose presence is still required.
GATE_FAMILIES: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str], ...
] = (
    (
        "parity",
        ("ranking_equality_fraction_min", "max_abs_score_delta_max"),
        ("ranking_equality_fraction_min", "max_abs_score_delta_max"),
        ("ranking_equality_fraction_min", "max_abs_score_delta_max"),
        "paired admitted measured rerank rows from the two named cells",
        "ranking-equality fraction and maximum absolute score delta",
    ),
    (
        "route-truth",
        ("route_or_rerank_violations_max",),
        ("route_or_rerank_violations_max",),
        ("route_or_rerank_violations_max",),
        "every admitted response row across all cells",
        "count of route/rerank-truth violations",
    ),
    (
        "latency-ratio",
        ("parent_observed_median_latency_ratio_max",),
        ("parent_observed_median_latency_ratio_max",),
        ("parent_observed_median_latency_ratio_max",),
        "paired parent-observed measured latency rows",
        "median parent-observed latency ratio (treatment over control)",
    ),
    (
        "break-even",
        ("one_sided_upper_bound_requests_max",),
        ("one_sided_upper_bound_requests_max", "confidence_level"),
        ("one_sided_upper_bound_requests_max", "confidence_level"),
        "cumulative parent-observed latency rows including startup and warm-up",
        "seeded block-bootstrap one-sided upper bound on the break-even request count",
    ),
    (
        "memory-budget",
        ("worker_plateau_rss_mib_max",),
        (
            "worker_plateau_rss_mib_max",
            "fallback_ready_process_tree_plateau_rss_mib_max",
            "fallback_ready_process_tree_peak_rss_mib_max",
            "aggregation_rule",
        ),
        (
            "worker_plateau_rss_mib_max",
            "fallback_ready_process_tree_plateau_rss_mib_max",
            "fallback_ready_process_tree_peak_rss_mib_max",
        ),
        "per-lifetime current-RSS samples (plateau window 801-1000) plus peak samples",
        "95th-percentile current-RSS plateau and peak per worker lifetime",
    ),
    (
        "memory-growth",
        ("one_sided_upper_bound_mib_per_1000_requests_strictly_below",),
        (
            "one_sided_upper_bound_mib_per_1000_requests_strictly_below",
            "confidence_level",
            "aggregation_rule",
        ),
        (
            "one_sided_upper_bound_mib_per_1000_requests_strictly_below",
            "confidence_level",
        ),
        "ordered current-RSS samples over requests 201-1000 per lifetime",
        "Theil-Sen slope with seeded block-bootstrap one-sided upper bound",
    ),
    (
        "deadline-fallback",
        ("request_deadline_seconds",),
        ("request_deadline_seconds", "required_outcome"),
        ("request_deadline_seconds",),
        "lifecycle probe rows (worker death, hang, pipe pressure)",
        "deadline compliance per probe with no late response admitted",
    ),
    (
        "reaping",
        ("remaining_worker_or_descendant_processes_max",),
        (
            "remaining_worker_or_descendant_processes_max",
            "drain_term_kill_idle_orphan_bounds",
        ),
        ("remaining_worker_or_descendant_processes_max",),
        "lifecycle supervisor process rows and orphan-observation evidence",
        "count of remaining worker/descendant processes after bounded shutdown",
    ),
    (
        "admissibility",
        ("required_outcome",),
        ("required_outcome",),
        (),
        "all TDR-014 artefacts (plan, manifests, preflight, rows, checkpoints)",
        "TDR-014 checklist pass/fail over every cited cell",
    ),
)


def _is_number(value: Any) -> bool:
    """Return True for real numeric thresholds (bool excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _find_todo_markers(node: Any, path: str = "$") -> list[str]:
    """Return error strings for every string value containing TODO-LOCAL."""
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            found.extend(_find_todo_markers(value, f"{path}.{key}"))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for index, item in enumerate(node):
            found.extend(_find_todo_markers(item, f"{path}[{index}]"))
    elif isinstance(node, str) and "TODO-LOCAL" in node:
        found.append(f"{path}: unresolved TODO-LOCAL marker")
    return found


def _classify_gate(
    gate: Mapping[str, Any],
) -> tuple[str, tuple[str, ...], tuple[str, ...], str, str] | None:
    """Return (family, required_fields, numeric_fields, row_population, estimator)."""
    for family, signatures, required, numeric, population, estimator in GATE_FAMILIES:
        if any(field in gate for field in signatures):
            return family, required, numeric, population, estimator
    return None


def _resolve_target(
    name: Any, cells_by_id: Mapping[str, Mapping[str, Any]], persistent_ids: tuple[str, ...]
) -> list[str] | None:
    """Resolve a gate target to cell ids; None means unresolvable."""
    if not isinstance(name, str):
        return None
    if name in cells_by_id:
        return [name]
    if name in ("all", "all_cited_cells"):
        return list(cells_by_id)
    if name == "persistent_cells":
        return list(persistent_ids)
    if name in PSEUDO_TARGETS:
        return [name]
    return None


def _factor_view(
    cell_ids: Sequence[str], cells_by_id: Mapping[str, Mapping[str, Any]], factor: str
) -> list[str]:
    """Backends/precisions for resolved cells; pseudo names pass through."""
    return [
        cells_by_id[cell_id].get("factors", {}).get(factor, cell_id)
        if cell_id in cells_by_id
        else cell_id
        for cell_id in cell_ids
    ]


def enumerate_gates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Enumerate every gate with resolved cells, routes, population and thresholds.

    Returns one dict per gate in plan order with keys ``id``, ``name``,
    ``treatment_cells``, ``control_cells``, ``treatment_backends``,
    ``treatment_precisions``, ``control_backends``, ``control_precisions``,
    ``model_revision``, ``row_population``, ``estimator`` and ``thresholds``.
    Unknown targets are passed through verbatim so callers can report them.
    """
    cells_by_id = {cell["id"]: cell for cell in payload.get("cells", [])}
    persistent_ids = tuple(
        cell_id
        for cell_id, cell in cells_by_id.items()
        if cell.get("factors", {}).get("process_shape") == "persistent_worker"
    )
    revision = payload.get("controlled_variables", {}).get("model_revision", "")

    enumerated: list[dict[str, Any]] = []
    for gate in payload.get("gate_table", []):
        classified = _classify_gate(gate) or ("unclassified", (), "", "")
        _, _, _, population, estimator = classified
        treatment = _resolve_target(gate.get("treatment"), cells_by_id, persistent_ids)
        control = _resolve_target(gate.get("control"), cells_by_id, persistent_ids)
        enumerated.append(
            {
                "id": gate.get("id", "?"),
                "name": gate.get("name", ""),
                "treatment_cells": treatment or [gate.get("treatment")],
                "control_cells": control or [gate.get("control")],
                "treatment_backends": _factor_view(treatment or [], cells_by_id, "backend"),
                "treatment_precisions": _factor_view(treatment or [], cells_by_id, "precision"),
                "control_backends": _factor_view(control or [], cells_by_id, "backend"),
                "control_precisions": _factor_view(control or [], cells_by_id, "precision"),
                "model_revision": revision,
                "row_population": population,
                "estimator": estimator,
                "thresholds": {key: value for key, value in gate.items() if _is_number(value)},
            }
        )
    return enumerated


def validate_plan(payload: Mapping[str, Any]) -> list[str]:
    """Validate a parsed plan payload; return a list of errors (empty = valid)."""
    errors: list[str] = []

    try:
        ExperimentPlan.from_dict(payload)
    except (ValueError, TypeError) as exc:
        errors.append(f"plan structure rejected by ExperimentPlan: {exc}")

    errors.extend(_find_todo_markers(payload))

    revision = payload.get("controlled_variables", {}).get("model_revision")
    if not isinstance(revision, str) or not _HEX40.fullmatch(revision):
        errors.append(
            "controlled_variables.model_revision must be a pinned 40-character "
            f"hex revision (got {revision!r})"
        )

    cells_by_id = {cell["id"]: cell for cell in payload.get("cells", [])}
    persistent_ids = tuple(
        cell_id
        for cell_id, cell in cells_by_id.items()
        if cell.get("factors", {}).get("process_shape") == "persistent_worker"
    )

    for gate in payload.get("gate_table", []):
        gate_id = gate.get("id", "?")
        classified = _classify_gate(gate)
        if classified is None:
            errors.append(f"{gate_id}: no recognised gate family (signature field missing)")
            continue
        family, required, numeric_fields, _, _ = classified

        for field in required:
            if field not in gate:
                errors.append(f"{gate_id}: {family} gate is missing field '{field}'")
        for field in numeric_fields:
            if field in gate and not _is_number(gate[field]):
                errors.append(f"{gate_id}: field '{field}' must be numeric")

        if (
            "ranking_equality_fraction_min" in required
            and gate.get("ranking_equality_fraction_min") != 1.0
        ):
            errors.append(
                f"{gate_id}: parity gates must demand 100% ranking equality "
                f"(got {gate.get('ranking_equality_fraction_min')!r})"
            )

        treatment = _resolve_target(gate.get("treatment"), cells_by_id, persistent_ids)
        control = _resolve_target(gate.get("control"), cells_by_id, persistent_ids)
        for role, resolved in (("treatment", treatment), ("control", control)):
            if resolved is None:
                errors.append(
                    f"{gate_id}: unknown {role} target {gate.get(role)!r} "
                    "(neither a declared cell id nor a registered pseudo-target)"
                )

        if family == "parity" and treatment and control:
            treatment_backends = _factor_view(treatment, cells_by_id, "backend")
            control_backends = _factor_view(control, cells_by_id, "backend")
            if set(treatment_backends) != set(control_backends):
                errors.append(
                    f"{gate_id}: parity gate mixes backends "
                    f"({'+vs+'.join(sorted(set(treatment_backends) | set(control_backends)))}); "
                    "ONNX-versus-Torch equality is forbidden — divergence between them is "
                    "registered descriptive evidence, never a correctness gate"
                )

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: print the gate enumeration, then any validation errors."""
    plan_path = Path(argv[0]) if argv else SCRIPT_DIR / "plan.json"
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read plan {plan_path}: {exc}")
        return 1

    for gate in enumerate_gates(payload):
        print(
            f"{gate['id']}: {gate['name']} | treatment={gate['treatment_cells']} "
            f"({'+'.join(gate['treatment_backends'])}/"
            f"{'+'.join(gate['treatment_precisions'])}) vs control={gate['control_cells']} "
            f"({'+'.join(gate['control_backends'])}/"
            f"{'+'.join(gate['control_precisions'])}) | revision={gate['model_revision'][:12]} "
            f"| rows: {gate['row_population']} | estimator: {gate['estimator']} "
            f"| thresholds: {gate['thresholds']}"
        )

    errors = validate_plan(payload)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"plan {plan_path} is INVALID ({len(errors)} error(s))")
        return 1
    print(f"plan {plan_path} is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
