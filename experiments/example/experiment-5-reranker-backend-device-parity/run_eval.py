"""Run Experiment 5 (reranker backend/device parity) — parent orchestrator.

Implements the TDR-014 campaign contract around
``child_run.py``:

* D15: loads ``plan.json`` via ``ExperimentPlan.from_json`` and proves
  the runner's four-cell matrix agrees with the plan before any work;
* protocol section 10: counterbalanced (rotated) cell order across
  repetitions, fresh child process per ``(cell, repetition)``;
* protocol section 11: 3 repetitions, 1 untimed warm-up pass and >= 5
  measured passes per repetition (defaults overridable);
* TDR-014 rule 7: checkpoint after every child via ``.tmp`` → rename,
  ``--resume`` skips completed children;
* TDR-014 rule 8: per-child and per-cell records use
  ``stats.cell_record`` statuses (``complete`` / ``incomplete`` /
  ``invalid``); a cell is ``complete`` only when all its repetitions
  completed, and rows are validated with
  ``stats.validate_per_query_rows`` before being accepted.

``--dry-run`` executes the untimed preflight path only (one
repetition, no warm-up, no measured passes) — never a measured cell.

Example (quiet measured campaign)::

    uv run --no-sync python run_eval.py --output-dir output
"""

from __future__ import annotations

import argparse
import subprocess  # noqa: S404 — spawning the committed child script
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import harness  # noqa: E402 — needs SCRIPT_DIR on sys.path first


def load_plan() -> Any:
    """Load and validate plan.json (D15)."""
    from experiments._lib.plan import ExperimentPlan

    return ExperimentPlan.from_json(harness.PLAN_PATH)


def assert_plan_agreement(plan: Any) -> None:
    """Abort the whole run when runner cells differ from the plan."""
    plan.assert_runner_cells(harness.build_cell_matrix())


def spawn_child(
    *,
    cell_id: str,
    repetition: int,
    output_dir: Path,
    measured_passes: int,
    warmup_passes: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Run one fresh child and return its parsed result JSON."""
    argv = [
        sys.executable,
        *harness.child_argv(
            cell_id=cell_id,
            repetition=repetition,
            output_dir=output_dir,
            measured_passes=measured_passes,
            warmup_passes=warmup_passes,
            dry_run=dry_run,
        ),
    ]
    completed = subprocess.run(  # noqa: S603 — argv is fully constructed
        argv,
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    result_path = harness.child_result_path(output_dir, cell_id, repetition)
    if not result_path.exists():
        return {
            "cell_id": cell_id,
            "repetition": repetition,
            "status": "incomplete",
            "reason": (
                f"child exited {completed.returncode} without writing a result; "
                f"stderr tail: {completed.stderr[-400:]}"
            ),
        }
    import json

    return json.loads(result_path.read_text(encoding="utf-8"))


def evaluate_child_result(child: dict[str, Any]) -> dict[str, Any]:
    """Turn a child result into a validated cell_record (TDR-014 rule 8)."""
    from experiments._lib import stats as stats_lib

    status = child.get("status")
    if status == "complete":
        try:
            stats_lib.validate_per_query_rows(child.get("rows", []))
        except ValueError as exc:
            return stats_lib.cell_record(
                status="invalid",
                reason=f"child rows failed D16 validation: {exc}",
                cell_id=child["cell_id"],
                repetition=child["repetition"],
            )
        warmup, measured = stats_lib.split_warmup(child["rows"])
        return stats_lib.cell_record(
            status="complete",
            reason=None,
            cell_id=child["cell_id"],
            repetition=child["repetition"],
            manifest=child.get("manifest"),
            rows=child["rows"],
            n_warmup_rows=len(warmup),
            n_measured_rows=len(measured),
        )
    if status == "preflight_ok":
        return stats_lib.cell_record(
            status="incomplete",
            reason="dry-run preflight only; no measured passes executed",
            cell_id=child["cell_id"],
            repetition=child["repetition"],
        )
    return stats_lib.cell_record(
        status=str(status or "incomplete"),
        reason=str(child.get("reason") or "child result carried no status"),
        cell_id=child.get("cell_id", "?"),
        repetition=child.get("repetition", -1),
    )


def load_checkpoint(path: Path) -> dict[str, Any]:
    """Load the resume checkpoint (empty structure when absent)."""
    import json

    if not path.exists():
        return {"completed": [], "records": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cells",
        nargs="*",
        default=None,
        help="subset of cell ids (default: all four, plan-agreement checked)",
    )
    parser.add_argument("--repetitions", type=int, default=harness.REPETITIONS)
    parser.add_argument("--measured-passes", type=int, default=harness.MEASURED_PASSES)
    parser.add_argument("--warmup-passes", type=int, default=harness.WARMUP_PASSES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR / "output")
    args = parser.parse_args()

    if args.measured_passes < 5 and not args.dry_run:
        parser.error("protocol section 11 requires >= 5 measured passes")

    plan = load_plan()
    assert_plan_agreement(plan)
    print("plan agreement: runner cells match plan.json", flush=True)

    all_cells = harness.build_cell_matrix()
    selected = (
        [cell for cell in all_cells if cell["id"] in set(args.cells)] if args.cells else all_cells
    )
    if not selected:
        parser.error("no cells selected")

    repetitions = 1 if args.dry_run else args.repetitions
    warmup_passes = 0 if args.dry_run else args.warmup_passes
    measured_passes = 0 if args.dry_run else args.measured_passes

    output_dir: Path = args.output_dir
    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    checkpoint = (
        load_checkpoint(checkpoint_path) if args.resume else {"completed": [], "records": []}
    )
    done_keys = {tuple(entry) for entry in checkpoint.get("completed", [])}

    records: list[dict[str, Any]] = list(checkpoint.get("records", []))
    for repetition in range(repetitions):
        order = harness.counterbalanced_order(selected, repetition)
        for cell in order:
            key = (cell["id"], repetition)
            if key in done_keys:
                print(f"skip (resume): {cell['id']} rep {repetition}", flush=True)
                continue
            print(
                f"run: {cell['id']} rep {repetition} "
                f"(order position {order.index(cell) + 1}/{len(order)})",
                flush=True,
            )
            child = spawn_child(
                cell_id=cell["id"],
                repetition=repetition,
                output_dir=output_dir,
                measured_passes=measured_passes,
                warmup_passes=warmup_passes,
                dry_run=args.dry_run,
            )
            record = evaluate_child_result(child)
            records = [
                r
                for r in records
                if not (r.get("cell_id") == cell["id"] and r.get("repetition") == repetition)
            ]
            records.append(record)
            checkpoint["completed"] = [list(k) for k in sorted(done_keys | {key})]
            checkpoint["records"] = records
            harness.write_json_atomic(checkpoint_path, checkpoint)
            done_keys.add(key)
            print(
                f"child status: {child.get('status')} -> record {record['status']}",
                flush=True,
            )

    from experiments._lib import stats as stats_lib

    cell_records = rollup_cells(records, expected_repetitions=repetitions)
    finalised = stats_lib.finalise_cells(cell_records)
    result = {
        "experiment_id": "5-reranker-backend-device-parity",
        "protocol_version": "1.0",
        "dry_run": args.dry_run,
        "workload_identity": harness.workload_identity(),
        "repetitions": repetitions,
        "measured_passes": measured_passes,
        "cells": finalised,
        "repetition_records": records,
    }
    harness.write_json_atomic(output_dir / "eval_results.json", result)
    write_raw_rows(output_dir, records)
    for entry in finalised:
        print(f"cell {entry.get('cell_id')}: {entry['status']}", flush=True)
    return 0


def rollup_cells(
    records: list[dict[str, Any]], *, expected_repetitions: int
) -> list[dict[str, Any]]:
    """Collapse repetition records into per-cell records.

    A cell is ``complete`` only when exactly ``expected_repetitions``
    records exist and every one completed; any invalid repetition makes
    the cell ``invalid``; otherwise ``incomplete``.  Reasons propagate
    verbatim.
    """
    from experiments._lib import stats as stats_lib

    by_cell: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_cell.setdefault(str(record.get("cell_id")), []).append(record)
    rolled: list[dict[str, Any]] = []
    for cell_id, reps in sorted(by_cell.items()):
        statuses = {rep["status"] for rep in reps}
        if statuses == {"complete"} and len(reps) == expected_repetitions:
            rolled.append(stats_lib.cell_record(status="complete", cell_id=cell_id))
        elif "invalid" in statuses:
            invalid_reasons = [
                f"rep {rep.get('repetition')}: {rep.get('reason')}"
                for rep in reps
                if rep["status"] == "invalid"
            ]
            rolled.append(
                stats_lib.cell_record(
                    status="invalid",
                    reason="; ".join(invalid_reasons),
                    cell_id=cell_id,
                )
            )
        else:
            rolled.append(
                stats_lib.cell_record(
                    status="incomplete",
                    reason="not all repetitions completed",
                    cell_id=cell_id,
                )
            )
    return rolled


def write_raw_rows(output_dir: Path, records: list[dict[str, Any]]) -> None:
    """Persist every per-query row to ``raw_rows.jsonl`` (never regenerated)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "raw_rows.jsonl").open("w", encoding="utf-8") as handle:
        import json

        for record in records:
            for row in record.get("rows") or []:
                handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
