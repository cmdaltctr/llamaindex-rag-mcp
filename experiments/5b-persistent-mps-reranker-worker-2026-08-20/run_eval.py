"""Experiment 5b campaign runner (protocol sections 13, 18 and 21).

Measured campaign: three counterbalanced blocks over the five-cell matrix
(W1 in-process ONNX, W2/W5 fresh children, W3/W4 persistent worker
lifetimes).  Every unit checkpoints atomically on completion; ``--resume``
reuses complete lifetimes only and restarts incomplete ones from request
zero.  ``--dry-run`` executes the untimed preflight path (plan agreement,
frozen identities, five route handshakes, parent purity, stub-worker probe
battery, one untimed real-model request per route) and never writes a
measured row.

The parent stays Torch-free: worker cells run in children; W1 loads the
ONNX reranker in-process as the declared fallback-ready parent state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import artefacts as art
import harness
import ipc_client
import materialise

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_MEASURED_REQUESTS = 1000
DEFAULT_BLOCKS = 3
WARMUP_REQUESTS = 24  # one untimed pass over the workload
SAMPLING_EVERY = 10
GROWTH_WINDOW_START = 201
GROWTH_WINDOW_END = 1000
PROBE_FLAGS = (
    "worker_death",
    "worker_hang",
    "parent_death_idle",
    "parent_death_inflight",
    "stdout_backpressure",
    "stderr_flooding",
    "malformed_frame",
    "request_deadline",
    "idle_expiry_restart",
    "orderly_shutdown",
    "eof_stdin",
    "orphan_reaping",
)

_onnx_parent_state: dict[str, Any] = {}


class CellAbort(RuntimeError):
    """A route-admission violation aborted the cell (protocol section 14)."""


# ── W1 in-process ONNX baseline ───────────────────────────────────────


def ensure_onnx_parent() -> Any:
    """Load and warm the production ONNX reranker once (fallback-ready W1).

    The declared W1 parent state (plan.json ``w1_parent_state``): loaded and
    warmed before paired measured rows and retained for W3 fallback
    measurement across the whole campaign.
    """
    if "reranker" not in _onnx_parent_state:
        from omrg.core.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(model_id=harness.MODEL_ID)
        probe = [{"text": "probe passage", "score": 0.0, "doc_id": "probe"}]
        reranker.rerank("probe query", probe, top_k=1)
        if probe[0].get("_reranked") is not True:
            raise CellAbort("ONNX parent warm-up degraded; aborting campaign")
        _onnx_parent_state["reranker"] = reranker
    return _onnx_parent_state["reranker"]


def run_w1_unit(
    *,
    block: int,
    measured_requests: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Serve the ordered primary workload in-process through ONNX CPU."""
    reranker = ensure_onnx_parent()
    rows_path = output_dir / "raw_rows" / f"onnx_cpu_in_process__block{block}.jsonl"
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    sampler = ipc_client.MemorySampler(
        __import__("os").getpid(), interval_s=1.0, parent_pid=__import__("os").getpid()
    )
    sampler.start()
    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    warmup_started = time.perf_counter()
    for n in range(WARMUP_REQUESTS):
        request = harness.ordered_primary_request(n)
        candidates = [
            {"text": c["text"], "score": 0.0, "doc_id": c["doc_id"]} for c in request["candidates"]
        ]
        reranker.rerank(request["query"], candidates, top_k=harness.TOP_K)
    warmup_s = time.perf_counter() - warmup_started
    try:
        for n in range(measured_requests):
            request = harness.ordered_primary_request(n)
            candidates = [
                {"text": c["text"], "score": 0.0, "doc_id": c["doc_id"]}
                for c in request["candidates"]
            ]
            started = time.perf_counter()
            ranked = reranker.rerank(request["query"], candidates, top_k=harness.TOP_K)
            latency_ms = (time.perf_counter() - started) * 1000.0
            reranked = all(row.get("_reranked") is True for row in ranked) and len(ranked) == len(
                candidates
            )
            metrics = {
                "scores": {row["doc_id"]: float(row["score"]) for row in ranked},
                "ranking": [row["doc_id"] for row in ranked],
                "route_ok": True,
                "rerank_ok": reranked,
                "cardinality_ok": len(ranked) == len(candidates),
                "generation_ok": True,
                "admitted": reranked,
                "reason": "" if reranked else "unreranked onnx response",
                "backend": "onnx",
                "device": "cpu",
            }
            rows.append(
                art.build_raw_row(
                    cell_id="onnx_cpu_in_process",
                    block=block,
                    lifetime=1,
                    request_index=n + 1,
                    query_id=request["query_id"],
                    phase="measured",
                    source="primary",
                    latency_ms=latency_ms,
                    generation=0,
                    worker_pid=None,
                    metrics=metrics,
                )
            )
            if (n + 1) % SAMPLING_EVERY == 0:
                sample = sampler.sample_now(
                    cell_id="onnx_cpu_in_process",
                    block=block,
                    lifetime=1,
                    request_index=n + 1,
                )
                if sample is not None:
                    samples.append(sample)
            if not reranked:
                art.append_jsonl(rows_path, rows)
                raise CellAbort(f"W1 block {block} request {n + 1}: unreranked response")
    finally:
        sampler.stop()
    art.append_jsonl(rows_path, rows)
    art.append_jsonl(
        output_dir / "memory_samples" / f"onnx_cpu_in_process__block{block}.jsonl",
        samples,
    )
    return {
        "status": "complete",
        "startup_s": 0.0,
        "warmup_s": warmup_s,
        "worker_pid": None,
        "generation": 0,
        "unit": f"onnx_cpu_in_process__block{block}",
    }


# ── worker cells (W2/W3/W4/W5) ────────────────────────────────────────


def _metrics_from_outcome(outcome: ipc_client.RequestOutcome, generation: int) -> dict[str, Any]:
    frame = outcome.frame or {}
    rerank_ok = frame.get("reranked") is True
    cardinality_ok = frame.get("cardinality") == frame.get("expected_cardinality")
    admitted = outcome.admitted and rerank_ok and cardinality_ok
    metrics = {
        "scores": frame.get("scores", {}),
        "ranking": frame.get("ranking", []),
        "route_ok": outcome.ok,
        "rerank_ok": rerank_ok,
        "cardinality_ok": cardinality_ok,
        "generation_ok": frame.get("generation") == generation,
        "admitted": admitted,
        "reason": outcome.error_code or outcome.detail or "",
        "backend": frame.get("backend"),
        "device": frame.get("device"),
        "model_id": frame.get("model_id"),
        "inference_ms": frame.get("inference_ms"),
    }
    return metrics


def _validate_ready_evidence(cell_id: str, evidence: dict[str, Any]) -> None:
    """Protocol section 13 route assertions against handshake evidence."""
    factors = {cell["id"]: cell["factors"] for cell in harness.build_cell_matrix()}[cell_id]
    expected_device = factors["device"]
    if not str(evidence.get("effective_device", "")).startswith(expected_device):
        raise CellAbort(
            f"{cell_id}: requested device {expected_device!r} but effective "
            f"{evidence.get('effective_device')!r}"
        )
    if factors["backend"] == "torch":
        if evidence.get("model_revision") != harness.MODEL_REVISION:
            raise CellAbort(
                f"{cell_id}: model revision {evidence.get('model_revision')!r} != "
                f"registered {harness.MODEL_REVISION!r}"
            )
        for name, digest in harness.MODEL_FILE_SHA256.items():
            observed = (evidence.get("model_file_sha256") or {}).get(name)
            if observed != digest:
                raise CellAbort(f"{cell_id}: file digest mismatch for {name}")
    if evidence.get("pytorch_enable_mps_fallback") != "0":
        raise CellAbort(f"{cell_id}: PYTORCH_ENABLE_MPS_FALLBACK was not '0' before import")


def _mps_fields(frame: dict[str, Any] | None) -> dict[str, Any]:
    mps = (frame or {}).get("mps") or {}
    return {
        "mps_current_allocated_bytes": mps.get("current_allocated_bytes"),
        "mps_driver_allocated_bytes": mps.get("driver_allocated_bytes"),
    }


def run_worker_unit(
    *,
    cell_id: str,
    block: int,
    lifetime: int,
    measured_requests: int,
    output_dir: Path,
    include_longevity: bool,
) -> dict[str, Any]:
    """One complete worker lifetime: warm-up, measured primary, longevity."""
    factors = {cell["id"]: cell["factors"] for cell in harness.build_cell_matrix()}[cell_id]
    rows_path = output_dir / "raw_rows" / f"{cell_id}__block{block}.jsonl"
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    supervisor = ipc_client.WorkerSupervisor(device=factors["device"])
    spawn_started = time.perf_counter()
    try:
        supervisor.start()
    except Exception:
        supervisor.shutdown()
        raise
    startup_s = time.perf_counter() - spawn_started
    try:
        _validate_ready_evidence(cell_id, supervisor.ready_evidence)
        sampler = ipc_client.MemorySampler(
            supervisor.worker_pid, interval_s=1.0, parent_pid=__import__("os").getpid()
        )
        sampler.start()

        warmup_started = time.perf_counter()
        for n in range(WARMUP_REQUESTS):
            request = harness.ordered_primary_request(n)
            outcome = supervisor.request(
                request["query"], request["candidates"], top_k=harness.TOP_K
            )
            if not outcome.admitted:
                rows.append(
                    art.build_raw_row(
                        cell_id=cell_id,
                        block=block,
                        lifetime=lifetime,
                        request_index=n + 1,
                        query_id=request["query_id"],
                        phase="warmup",
                        source="primary",
                        latency_ms=outcome.latency_ms or 0.0,
                        generation=supervisor.generation,
                        worker_pid=supervisor.worker_pid,
                        metrics=_metrics_from_outcome(outcome, supervisor.generation),
                        warmup_pass=True,
                    )
                )
                art.append_jsonl(rows_path, rows)
                raise CellAbort(f"{cell_id} block {block}: warm-up request {n + 1} not admitted")
        warmup_s = time.perf_counter() - warmup_started

        for n in range(measured_requests):
            request = harness.ordered_primary_request(n)
            outcome = supervisor.request(
                request["query"], request["candidates"], top_k=harness.TOP_K
            )
            rows.append(
                art.build_raw_row(
                    cell_id=cell_id,
                    block=block,
                    lifetime=lifetime,
                    request_index=n + 1,
                    query_id=request["query_id"],
                    phase="measured",
                    source="primary",
                    latency_ms=outcome.latency_ms if outcome.latency_ms is not None else 0.0,
                    generation=supervisor.generation,
                    worker_pid=supervisor.worker_pid,
                    metrics=_metrics_from_outcome(outcome, supervisor.generation),
                )
            )
            if not rows[-1]["metrics"]["admitted"]:
                art.append_jsonl(rows_path, rows)
                raise CellAbort(
                    f"{cell_id} block {block} request {n + 1}: {rows[-1]['metrics']['reason']}"
                )
            sample_now = (n + 1) % SAMPLING_EVERY == 0 or (
                GROWTH_WINDOW_START <= n + 1 <= GROWTH_WINDOW_END
            )
            if sample_now:
                sample = sampler.sample_now(
                    cell_id=cell_id,
                    block=block,
                    lifetime=lifetime,
                    request_index=n + 1,
                    **_mps_fields(outcome.frame),
                )
                if sample is not None:
                    samples.append(sample)

        if include_longevity and factors["process_shape"] == "persistent_worker":
            schedule = harness.load_longevity_schedule()
            for index, entry in enumerate(schedule["requests"]):
                request = materialise.materialise_request(entry)
                outcome = supervisor.request(
                    request["query"], request["candidates"], top_k=len(request["candidates"])
                )
                rows.append(
                    art.build_raw_row(
                        cell_id=cell_id,
                        block=block,
                        lifetime=lifetime,
                        request_index=measured_requests + index + 1,
                        query_id=f"long_r{entry['request_index']}",
                        phase="measured",
                        source="longevity",
                        latency_ms=outcome.latency_ms if outcome.latency_ms is not None else 0.0,
                        generation=supervisor.generation,
                        worker_pid=supervisor.worker_pid,
                        metrics=_metrics_from_outcome(outcome, supervisor.generation),
                        stratum={
                            "candidate_count": entry["stratum_candidate_count"],
                            "approx_tokens_per_candidate": entry[
                                "stratum_approx_tokens_per_candidate"
                            ],
                        },
                    )
                )
                if not rows[-1]["metrics"]["admitted"]:
                    art.append_jsonl(rows_path, rows)
                    raise CellAbort(
                        f"{cell_id} block {block} longevity request "
                        f"{entry['request_index']}: {rows[-1]['metrics']['reason']}"
                    )
                if (index + 1) % SAMPLING_EVERY == 0:
                    sample = sampler.sample_now(
                        cell_id=cell_id,
                        block=block,
                        lifetime=lifetime,
                        request_index=measured_requests + index + 1,
                        **_mps_fields(outcome.frame),
                    )
                    if sample is not None:
                        samples.append(sample)
        sampler.stop()
    finally:
        exit_evidence = supervisor.shutdown()

    art.append_jsonl(rows_path, rows)
    art.append_jsonl(output_dir / "memory_samples" / f"{cell_id}__block{block}.jsonl", samples)
    return {
        "status": "complete",
        "startup_s": startup_s,
        "warmup_s": warmup_s,
        "worker_pid": supervisor.worker_pid,
        "generation": supervisor.generation,
        "exit_evidence": exit_evidence,
        "unit": f"{cell_id}__block{block}",
    }


# ── checkpoint plumbing ───────────────────────────────────────────────


def campaign_context(
    block: int,
    *,
    phase: str,
    operator_declaration: str,
) -> dict[str, Any]:
    """Per-block power/thermal/interference evidence (protocol section 15).

    ``pmset`` readings are macOS-specific and degrade to explicit None when
    unavailable; the foreground-interference declaration comes verbatim
    from the operator at campaign start.
    """
    import platform

    def _pmset(flag: str) -> str | None:
        try:
            result = subprocess.run(
                ["pmset", "-g", flag],  # noqa: S603 — fixed argv
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.stdout.strip()[:500] if result.returncode == 0 else None
        except Exception:  # noqa: BLE001 — diagnostic evidence only
            return None

    memory_percent = None
    try:
        import psutil

        memory_percent = psutil.virtual_memory().percent
    except Exception:  # noqa: BLE001 — diagnostic evidence only
        pass
    return {
        "block": block,
        "phase": phase,  # "start" or "end"
        "t_monotonic": time.monotonic(),
        "power_source": _pmset("ps"),
        "thermal_state": _pmset("therm"),
        "memory_pressure_percent": memory_percent,
        "operator_interference_declaration": operator_declaration,
        "cell_order": list(harness.COUNTERBALANCE_TABLE.get(block, ())),
        "macos_version": platform.mac_ver()[0] or None,
    }


def pending_units(
    blocks: int,
    table: dict[int, tuple[str, ...]],
    completed: list[str],
) -> list[tuple[str, int]]:
    """Units still to run: complete lifetimes are skipped, others restart.

    Resume reuses complete lifetimes only (protocol section 18); an
    incomplete or invalid unit is absent from *completed* and therefore
    restarts from request zero under a new attempt.
    """
    done = set(completed)
    return [
        (cell_id, block)
        for block in range(1, blocks + 1)
        for cell_id in table[block]
        if art.checkpoint_key(cell_id, block) not in done
    ]


def load_checkpoint(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return art.build_checkpoint(
        experiment_id=harness.EXPERIMENT_ID,
        plan_sha256=harness.plan_sha256(),
        completed=[],
        records={},
    )


def write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    art.write_json_atomic(path, checkpoint)


# ── preflight (dry run) ───────────────────────────────────────────────


def identity_block() -> dict[str, Any]:
    """Task 5.1 identity evidence: commit, lock, host, OS and Python."""
    import platform

    from experiments._lib.manifest import git_commit, git_dirty, lock_hash

    macos = platform.mac_ver()[0]
    return {
        "repo_commit": git_commit(REPO_ROOT),
        "dependency_lock_hash": lock_hash(REPO_ROOT),
        "git_dirty": git_dirty(REPO_ROOT),
        "host_machine": platform.machine(),
        "host_processor": platform.processor(),
        "macos_version": macos or None,
        "python_version": platform.python_version(),
        "workload_identity": harness.WORKLOAD_IDENTITY,
        "longevity_identity": harness.LONGEVITY_IDENTITY,
        "model_id": harness.MODEL_ID,
        "model_revision": harness.MODEL_REVISION,
    }


def preflight(output_dir: Path) -> dict[str, Any]:
    """Untimed preflight: identities, five route handshakes, purity, probes."""
    plan = harness.load_plan()
    harness.assert_plan_agreement(plan)
    harness.assert_frozen_identities()
    routes_green = True
    route_results: dict[str, Any] = {}
    for cell in harness.build_cell_matrix():
        cell_id = cell["id"]
        if cell_id == "onnx_cpu_in_process":
            reranker = ensure_onnx_parent()
            evidence = {
                "requested_backend": "onnx",
                "effective_backend": "onnx",
                "onnx_effective_providers": __import__(
                    "experiments._lib.manifest", fromlist=["observe_onnx_providers"]
                ).observe_onnx_providers(reranker),
                "model_id": harness.MODEL_ID,
                "pytorch_enable_mps_fallback": __import__("os").environ.get(
                    "PYTORCH_ENABLE_MPS_FALLBACK", ""
                ),
            }
            ok = bool(evidence["onnx_effective_providers"]) and (
                evidence["onnx_effective_providers"][0] == "CPUExecutionProvider"
            )
            route_results[cell_id] = {"ok": ok, "evidence": evidence}
            routes_green = routes_green and ok
        else:
            supervisor = ipc_client.WorkerSupervisor(device=cell["factors"]["device"])
            try:
                supervisor.start()
                _validate_ready_evidence(cell_id, supervisor.ready_evidence)
                request = harness.ordered_primary_request(0)
                outcome = supervisor.request(
                    request["query"], request["candidates"], top_k=harness.TOP_K
                )
                ok = outcome.admitted
                route_results[cell_id] = {
                    "ok": ok,
                    "evidence": supervisor.ready_evidence,
                    "untimed_request_admitted": ok,
                }
            finally:
                supervisor.shutdown()
            routes_green = routes_green and ok
    purity = harness.assert_parent_torch_free()
    parent_torch_free = purity == []
    summary = {
        "plan_agreement": True,
        "frozen_identities": True,
        "identity": identity_block(),
        "routes_green": routes_green,
        "route_results": route_results,
        "parent_torch_free": parent_torch_free,
        "parent_torch_stack_modules": purity,
    }
    preflight_dir = output_dir / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    for cell_id, result in route_results.items():
        art.write_json_atomic(preflight_dir / f"{cell_id}__block0.json", result)
    return summary


def merge_prior_preflight_green(summary: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Preserve dry-run preflight-green evidence across the measured run.

    The intended workflow (protocol section 21) runs ``--dry-run`` and the
    measured campaign against the same ``--output-dir``.  The measured run
    re-runs the route preflight and rewrites ``preflight/_summary.json``
    without the probe battery, which previously destroyed the dry-run's
    ``probes_green``/``all_green`` flags and made G9 report "preflight not
    green" even though every probe passed before the first measured row.
    Restore those flags from the prior summary when it was green.
    """
    prior_path = output_dir / "preflight" / "_summary.json"
    if not prior_path.exists():
        return summary
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — malformed prior summary is not fatal
        return summary
    if prior.get("all_green"):
        summary["probes_green"] = True
        summary["all_green"] = bool(
            summary.get("plan_agreement")
            and summary.get("routes_green")
            and summary.get("parent_torch_free")
        )
    return summary


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--measured-requests", type=int, default=DEFAULT_MEASURED_REQUESTS)
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    parser.add_argument("--no-longevity", action="store_true")
    parser.add_argument(
        "--operator-declaration",
        default="",
        help="verbatim foreground-interference declaration recorded per block",
    )
    for probe in PROBE_FLAGS:
        parser.add_argument(f"--probe-{probe.replace('_', '-')}", action="store_true")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_probes = [probe for probe in PROBE_FLAGS if getattr(args, f"probe_{probe}")]
    if selected_probes:
        import probes

        for probe in selected_probes:
            probes.run_probe(probe, output_dir)
        return 0

    summary = preflight(output_dir)
    if not args.dry_run:
        summary = merge_prior_preflight_green(summary, output_dir)
    if args.dry_run:
        import probes

        probes_green = probes.run_battery(output_dir, fast=False)
        summary["probes_green"] = probes_green
        summary["all_green"] = bool(
            summary["plan_agreement"]
            and summary["routes_green"]
            and summary["parent_torch_free"]
            and probes_green
        )
        art.write_json_atomic(output_dir / "preflight" / "_summary.json", summary)
        print(
            f"preflight complete: routes_green={summary['routes_green']} "
            f"probes_green={probes_green} parent_torch_free={summary['parent_torch_free']}"
        )
        return 0 if summary["all_green"] else 1

    art.write_json_atomic(output_dir / "preflight" / "_summary.json", summary)
    if not (summary["routes_green"] and summary["parent_torch_free"]):
        print("preflight failed; refusing measured campaign", file=sys.stderr)
        return 1

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    else:
        checkpoint = art.build_checkpoint(
            experiment_id=harness.EXPERIMENT_ID,
            plan_sha256=harness.plan_sha256(),
            completed=[],
            records={},
        )

    for block in range(1, args.blocks + 1):
        art.append_jsonl(
            output_dir / "campaign_context.jsonl",
            campaign_context(block, phase="start", operator_declaration=args.operator_declaration),
        )
        for cell_id in harness.COUNTERBALANCE_TABLE[block]:
            key = art.checkpoint_key(cell_id, block)
            if key in checkpoint["completed"]:
                print(f"skip complete unit {key}")
                continue
            attempt = 1
            while True:
                try:
                    if cell_id == "onnx_cpu_in_process":
                        record = run_w1_unit(
                            block=block,
                            measured_requests=args.measured_requests,
                            output_dir=output_dir,
                        )
                    else:
                        record = run_worker_unit(
                            cell_id=cell_id,
                            block=block,
                            lifetime=attempt,
                            measured_requests=args.measured_requests,
                            output_dir=output_dir,
                            include_longevity=not args.no_longevity,
                        )
                    checkpoint["records"][key] = record
                    checkpoint["completed"] = sorted(set(checkpoint["completed"]) | {key})
                    break
                except CellAbort as exc:
                    checkpoint["records"][key] = {
                        "status": "invalid",
                        "reason": str(exc),
                        "attempt": attempt,
                    }
                    art.write_json_atomic(checkpoint_path, checkpoint)
                    print(f"unit {key} aborted: {exc}", file=sys.stderr)
                    return 1
                attempt += 1
            art.write_json_atomic(checkpoint_path, checkpoint)
            print(f"unit {key} complete")
        art.append_jsonl(
            output_dir / "campaign_context.jsonl",
            campaign_context(block, phase="end", operator_declaration=args.operator_declaration),
        )
    print("campaign complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
