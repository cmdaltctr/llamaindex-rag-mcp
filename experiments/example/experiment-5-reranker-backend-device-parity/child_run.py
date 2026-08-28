"""Fresh child process for one Experiment 5 (cell, repetition).

Spawned by ``run_eval.py`` via ``sys.executable`` so each route runs in
a clean process: the production reranker caches are process-wide, so a
fresh child guarantees ``last_loaded_variant`` provenance and zero
cross-route state leakage (protocol section 5).

Sequence (TDR-014):

1. set route environment (``RERANK_ONNX_PROVIDER``, offline Hub) and
   apply the torch device policy — all before production import;
2. construct the production reranker and trigger its lazy load with an
   untimed cold-start probe;
3. build the D13 manifest and run the full D14 preflight — any failure
   writes an ``invalid`` result with the exact reason and stops before
   timing;
4. one untimed warm-up pass (``phase="warmup"`` rows);
5. ``--measured-passes`` measured passes (``phase="measured"`` rows),
   with production-fallback detection after every rerank call;
6. record peak RSS (and MPS memory for the MPS route) and write the
   result JSON atomically.

With ``--dry-run`` the child stops after step 3 — an untimed preflight
dry run that proves each route loads and passes preflight without
executing measured cells.
"""

from __future__ import annotations

import argparse
import os
import resource
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import harness  # noqa: E402 — needs SCRIPT_DIR on sys.path first


def _mps_memory_bytes() -> int | None:
    """MPS current allocated memory, when this process used MPS."""
    try:
        import torch

        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return int(torch.mps.current_allocated_memory())
    except Exception:  # pragma: no cover — depends on torch build
        return None
    return None


def _route_facts(reranker: object, cell: dict) -> dict:
    """Manifest extras observed from the loaded production object."""
    facts: dict[str, object] = {
        "cold_start_probe_call": "rerank('probe query', 1 pair, top_k=1)",
    }
    if cell["factors"]["backend"] == "torch":
        facts["torch_predict_default_batch_size"] = harness.torch_predict_default_batch_size(
            reranker
        )
    return facts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--repetition", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--measured-passes", type=int, default=harness.MEASURED_PASSES)
    parser.add_argument("--warmup-passes", type=int, default=harness.WARMUP_PASSES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cells = {cell["id"]: cell for cell in harness.build_cell_matrix()}
    if args.cell not in cells:
        print(f"unknown cell {args.cell!r}", file=sys.stderr)
        return 2
    cell = cells[args.cell]
    result_path = harness.child_result_path(Path(args.output_dir), args.cell, args.repetition)

    # 1. Route environment — before any production import.
    os.environ.update(harness.route_env_overrides(cell))
    harness.apply_device_policy(cell)

    # 2. Load the production reranker; untimed cold-start probe.
    reranker = harness.construct_reranker(cell)
    try:
        cold_start_s, probe_fallback = harness.cold_start_probe(reranker)
    except Exception as exc:  # noqa: BLE001 — recorded as invalid evidence
        harness.write_json_atomic(
            result_path,
            {
                "cell_id": args.cell,
                "repetition": args.repetition,
                "status": "invalid",
                "reason": f"cold-start probe raised: {exc}",
            },
        )
        return 0
    if probe_fallback:
        harness.write_json_atomic(
            result_path,
            {
                "cell_id": args.cell,
                "repetition": args.repetition,
                "status": "invalid",
                "reason": f"cold-start probe degraded: {probe_fallback}",
            },
        )
        return 0

    # 3. Manifest + D14 preflight (untimed).
    manifest = harness.build_cell_manifest(
        cell=cell,
        reranker=reranker,
        experiment_id="5-reranker-backend-device-parity",
        protocol_version="1.0",
        route_facts=_route_facts(reranker, cell),
        extra={"cold_start_s": cold_start_s},
    )
    try:
        harness.preflight_cell(cell=cell, reranker=reranker, manifest=manifest)
    except Exception as exc:  # noqa: BLE001 — invalid-cell evidence
        manifest["preflight_error"] = str(exc)
        harness.write_json_atomic(
            result_path,
            {
                "cell_id": args.cell,
                "repetition": args.repetition,
                "status": "invalid",
                "reason": f"preflight failed: {exc}",
                "manifest": manifest,
            },
        )
        return 0

    if args.dry_run:
        harness.write_json_atomic(
            result_path,
            {
                "cell_id": args.cell,
                "repetition": args.repetition,
                "status": "preflight_ok",
                "manifest": manifest,
            },
        )
        return 0

    # 4. Untimed warm-up pass, then 5. measured passes.
    workload = harness.load_workload()
    rows: list[dict] = []
    for pass_index in range(args.warmup_passes):
        warm_rows, _ = harness.run_workload_pass(
            reranker=reranker,
            workload=workload,
            cell_id=args.cell,
            repetition=args.repetition,
            pass_index=pass_index,
            phase="warmup",
        )
        rows.extend(warm_rows)
    for pass_index in range(args.measured_passes):
        measured_rows, _ = harness.run_workload_pass(
            reranker=reranker,
            workload=workload,
            cell_id=args.cell,
            repetition=args.repetition,
            pass_index=pass_index,
            phase="measured",
        )
        rows.extend(measured_rows)

    # 6. Resource observations and atomic result write.
    peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports ru_maxrss in bytes; Linux in kilobytes.  Normalise.
    if sys.platform == "linux" and peak_rss_bytes > 0:
        peak_rss_bytes *= 1024
    manifest["peak_rss_bytes"] = int(peak_rss_bytes)
    manifest["mps_allocated_bytes"] = _mps_memory_bytes()

    harness.write_json_atomic(
        result_path,
        {
            "cell_id": args.cell,
            "repetition": args.repetition,
            "status": "complete",
            "manifest": manifest,
            "rows": rows,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
