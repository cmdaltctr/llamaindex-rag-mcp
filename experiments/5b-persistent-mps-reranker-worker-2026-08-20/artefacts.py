"""Artefact row schemas for Experiment 5b (protocol.md section 17).

Single source of truth for the JSON-lines and checkpoint payloads the
runner writes and the summariser reads.  Building rows through this module
guarantees TDR-014 field presence: raw per-request rows carry the D16
required fields (``cell_id``, ``query_id``, ``phase``, ``latency_ms``,
``metrics``) plus the 5b route-admission evidence; memory samples separate
worker/parent/process-tree RSS and MPS allocator fields; probe rows carry
supervisor lifecycle evidence; checkpoint entries mark complete lifetimes
only.

Block pairing: every row carries its 1-based counterbalanced block number
(protocol section 15).  W3 lifetime *b* pairs with W2/W4/W1/W5 repetition
*b* — pairing never crosses blocks or PIDs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

TORCH_STACK_MODULES = ("torch", "transformers", "sentence_transformers")

RAW_ROW_REQUIRED = (
    "cell_id",
    "block",
    "lifetime",
    "request_index",
    "query_id",
    "phase",
    "source",
    "latency_ms",
    "metrics",
)

MEMORY_SAMPLE_REQUIRED = (
    "cell_id",
    "block",
    "lifetime",
    "request_index",
    "t_monotonic",
    "worker_rss_bytes",
    "parent_rss_bytes",
    "tree_rss_bytes",
)

PROBE_ROW_REQUIRED = (
    "probe",
    "worker_pid",
    "started_monotonic",
    "ended_monotonic",
    "outcome",
    "deadline_result",
    "detail",
)


def build_raw_row(
    *,
    cell_id: str,
    block: int,
    lifetime: int,
    request_index: int,
    query_id: str,
    phase: str,
    source: str,
    latency_ms: float,
    generation: int,
    worker_pid: int | None,
    metrics: dict[str, Any],
    parent_pid: int | None = None,
    warmup_pass: bool = False,
    stratum: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build one per-request raw row with route-admission evidence.

    ``metrics`` carries ``scores``, ``ranking`` and the boolean admission
    flags (``route_ok``, ``rerank_ok``, ``cardinality_ok``,
    ``generation_ok``); a row excluded from aggregates keeps ``admitted``
    false with the violation recorded in ``reason``.
    """
    if phase not in ("warmup", "measured"):
        raise ValueError(f"phase must be warmup|measured, got {phase!r}")
    if source not in ("primary", "longevity"):
        raise ValueError(f"source must be primary|longevity, got {source!r}")
    row = {
        "cell_id": cell_id,
        "block": block,
        "lifetime": lifetime,
        "request_index": request_index,
        "query_id": query_id,
        "phase": phase,
        "source": source,
        "latency_ms": float(latency_ms),
        "generation": generation,
        "worker_pid": worker_pid,
        "parent_pid": parent_pid if parent_pid is not None else os.getpid(),
        "warmup_pass": warmup_pass,
        "t_monotonic": time.monotonic(),
        "metrics": metrics,
    }
    if stratum is not None:
        row["stratum"] = stratum
    missing = [field for field in RAW_ROW_REQUIRED if field not in row]
    if missing:
        raise ValueError(f"raw row missing required field(s): {missing}")
    return row


def build_memory_sample(
    *,
    cell_id: str,
    block: int,
    lifetime: int,
    request_index: int,
    worker_rss_bytes: int,
    parent_rss_bytes: int,
    tree_rss_bytes: int,
    mps_current_allocated_bytes: int | None = None,
    mps_driver_allocated_bytes: int | None = None,
) -> dict[str, Any]:
    """Build one current-RSS sample with separate tree/MPS fields (D5)."""
    sample = {
        "cell_id": cell_id,
        "block": block,
        "lifetime": lifetime,
        "request_index": int(request_index),
        "t_monotonic": time.monotonic(),
        "worker_rss_bytes": int(worker_rss_bytes),
        "parent_rss_bytes": int(parent_rss_bytes),
        "tree_rss_bytes": int(tree_rss_bytes),
        "mps_current_allocated_bytes": mps_current_allocated_bytes,
        "mps_driver_allocated_bytes": mps_driver_allocated_bytes,
    }
    missing = [field for field in MEMORY_SAMPLE_REQUIRED if field not in sample]
    if missing:
        raise ValueError(f"memory sample missing required field(s): {missing}")
    return sample


def build_probe_row(
    *,
    probe: str,
    worker_pid: int | None,
    outcome: str,
    deadline_result: str,
    detail: str,
    parent_pid: int | None = None,
    descendant_pids: list[int] | None = None,
    generation: int | None = None,
    started_monotonic: float | None = None,
    ended_monotonic: float | None = None,
    fallback_route: str | None = None,
    exit_status: str | None = None,
    reaped: bool | None = None,
    orphans_remaining: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one lifecycle supervisor probe evidence row (section 12)."""
    now = time.monotonic()
    row: dict[str, Any] = {
        "probe": probe,
        "parent_pid": parent_pid if parent_pid is not None else os.getpid(),
        "worker_pid": worker_pid,
        "descendant_pids": descendant_pids or [],
        "generation": generation,
        "started_monotonic": started_monotonic if started_monotonic is not None else now,
        "ended_monotonic": ended_monotonic if ended_monotonic is not None else now,
        "outcome": outcome,
        "deadline_result": deadline_result,
        "fallback_route": fallback_route,
        "exit_status": exit_status,
        "reaped": reaped,
        "orphans_remaining": orphans_remaining,
        "detail": detail[:2000],
    }
    if extra:
        row.update(extra)
    missing = [field for field in PROBE_ROW_REQUIRED if field not in row]
    if missing:
        raise ValueError(f"probe row missing required field(s): {missing}")
    return row


def append_jsonl(path: str | Path, rows: list[dict[str, Any]] | dict[str, Any]) -> None:
    """Append rows to a JSON-lines artefact, fsyncing after the batch.

    Partial writes are bounded to one batch; checkpoint completeness is the
    authority for aggregate admission, never this file's tail.
    """
    payload = rows if isinstance(rows, list) else [rows]
    if not payload:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for row in payload:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically: serialise, ``.tmp``, fsync, rename (section 18)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    data = json.dumps(payload, sort_keys=True, indent=2)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(target)


def checkpoint_key(cell_id: str, block: int) -> str:
    """Canonical checkpoint key: one complete lifetime/replication unit."""
    return f"{cell_id}__block{block}"


def build_checkpoint(
    *,
    experiment_id: str,
    plan_sha256: str,
    completed: list[str],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the complete-lifetime checkpoint payload (section 18).

    ``completed`` lists keys whose whole lifetime finished; every other key
    in ``records`` restarts from request zero on ``--resume``.
    """
    for key, record in records.items():
        status = record.get("status")
        if status not in ("complete", "incomplete", "invalid"):
            raise ValueError(f"record {key!r} has invalid status {status!r}")
    return {
        "experiment_id": experiment_id,
        "plan_sha256": plan_sha256,
        "completed": sorted(completed),
        "records": records,
        "updated_monotonic": time.monotonic(),
    }


def imported_torch_stack_modules() -> list[str]:
    """Return Torch-stack modules imported in the current (parent) process.

    Task 2.4 purity proof: the parent must show none of ``torch``,
    ``transformers`` or ``sentence_transformers`` after worker/probe work.
    """
    return sorted(name for name in TORCH_STACK_MODULES if name in sys_modules())


def sys_modules() -> dict[str, Any]:
    """Indirection for tests that inject fake module entries."""
    import sys

    return sys.modules
