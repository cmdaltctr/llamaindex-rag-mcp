"""Summarise Experiment 18 cell results into gates and a decision record.

Loads ``output/cells/*.json``, evaluates hypotheses H1-H5 (Phase A
correctness gates) plus the lock-scope timing evidence, and writes
``output/results.summary.json``. Phase B gates H6/H7 stay reserved until
a treatment variant exists.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELLS_DIR = HERE / "output" / "cells"

TIMING_KEYS = (
    "change_detection_seconds",
    "parse_chunk_seconds",
    "embedding_seconds",
    "store_write_seconds",
    "lock_wait_seconds",
    "cleanup_seconds",
    "total_seconds",
)


def _load(cell_id: str) -> dict | None:
    path = CELLS_DIR / f"{cell_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _timing_row(label: str, cell: dict) -> dict:
    """Build one timing table row from a timing cell."""
    streams = cell.get("streams", [])
    timings = {}
    for stream in streams:
        for key, value in stream.get("timings", {}).items():
            timings[key] = timings.get(key, 0.0) + value
    wall = cell.get("wall_seconds") or 0.0
    files = sum(s.get("files_indexed", 0) for s in streams)
    chunks = sum(s.get("chunks_created", 0) for s in streams)
    residual = max(
        0.0,
        sum(s.get("timings", {}).get("total_seconds", 0.0) for s in streams)
        - sum(
            sum(v for k, v in s.get("timings", {}).items() if k != "total_seconds") for s in streams
        ),
    )
    return {
        "cell": label,
        "status": cell.get("status"),
        "wall_seconds": round(wall, 3),
        "files": files,
        "chunks": chunks,
        "docs_per_second": round(files / wall, 2) if wall else None,
        "lock_wait_seconds": round(timings.get("lock_wait_seconds", 0.0), 4),
        "lock_wait_fraction_of_wall": (
            round(timings.get("lock_wait_seconds", 0.0) / wall, 4) if wall else None
        ),
        "stage_seconds": {
            key: round(timings.get(key, 0.0), 3) for key in TIMING_KEYS if key != "total_seconds"
        },
        "untimed_residual_seconds": round(residual, 3),
        "peak_rss_bytes": cell.get("process_peak_rss_bytes"),
    }


def _boundedness() -> dict:
    rows = {}
    for size in (25, 100, 400):
        cell = _load(f"bounded_{size}")
        if cell is None:
            continue
        first = cell["first"]
        second = cell["unchanged_second"]
        rows[size] = {
            "files_indexed": first["files_indexed"],
            "chunks": first["chunks_created"],
            "max_chunks_per_file": first["max_chunks_per_file"],
            "unchanged_skipped": second["files_skipped_unchanged"],
            "unchanged_chunks_created": second["chunks_created"],
            "unchanged_embedding_seconds": second["timings"].get("embedding_seconds"),
            "peak_rss_bytes": cell.get("process_peak_rss_bytes"),
        }
    return rows


def _gates(bounded: dict) -> dict:
    h1 = bool(bounded) and all(row["max_chunks_per_file"] > 0 for row in bounded.values())
    h2 = None
    if 25 in bounded and 100 in bounded:
        base = bounded[25]["peak_rss_bytes"]
        grown = bounded[100]["peak_rss_bytes"]
        h2 = bool(base and grown and grown / base <= 2.0)
    h5 = bool(bounded) and all(
        row["unchanged_skipped"] == size and row["unchanged_chunks_created"] == 0
        for size, row in bounded.items()
    )
    faults = {}
    for stage in ("none", "parse", "embed", "store_write"):
        cell = _load(f"fault_{stage}")
        if cell is None:
            faults[stage] = {"missing": True}
            continue
        faults[stage] = {
            "old_version_survived": cell["old_version_survived"],
            "swap_completed": cell["swap_completed"],
        }
    fault_stages = [s for s in faults if s != "none"]
    swap_stages = list(faults)
    h3 = bool(fault_stages) and all(faults[s].get("old_version_survived") for s in fault_stages)
    h4 = bool(swap_stages) and all(faults[s].get("swap_completed") for s in swap_stages)
    return {
        "H1_bounded_units": h1,
        "H2_rss_scaling": h2,
        "H3_failure_safety": h3,
        "H4_swap": h4,
        "H5_unchanged_skip": h5,
        "fault_cells": faults,
    }


def _decision(timing_rows: dict) -> dict:
    """Compute the lock-scope decision inputs (single-stream and contended)."""
    fake_seq = timing_rows.get("timing_fake_seq_100", {})
    fake_con = timing_rows.get("timing_fake_contended_100", {})
    real_seq = timing_rows.get("timing_real_seq_100", {})
    real_con = timing_rows.get("timing_real_contended_100", {})

    def speedup(seq, con):
        if seq.get("wall_seconds") and con.get("wall_seconds"):
            return round(seq["wall_seconds"] / con["wall_seconds"], 3)
        return None

    return {
        "single_stream_lock_wait_fraction": {
            block: timing_rows.get(f"timing_{block}_seq_100", {}).get("lock_wait_fraction_of_wall")
            for block in ("fake", "real")
        },
        "contended_lock_wait_fraction": {
            block: timing_rows.get(f"timing_{block}_contended_100", {}).get(
                "lock_wait_fraction_of_wall"
            )
            for block in ("fake", "real")
        },
        "contended_speedup_vs_sequential": {
            "fake": speedup(fake_seq, fake_con),
            "real": speedup(real_seq, real_con),
        },
        "interpretation_rules": [
            "lock scope is a demonstrated constraint only if the contended lock-wait fraction is material AND embedding dominates the lock-held critical section",
            "single-stream sequential ingestion cannot contend by construction; a zero single-stream lock wait is expected, not evidence for widening",
            "if contended speedup already approaches the parallel bound, the lock is not the limiting factor",
        ],
    }


def main() -> None:
    """Load cells, evaluate gates, write summary."""
    timing_rows = {
        cell_id: _timing_row(cell_id, cell)
        for cell_id in (
            "timing_fake_seq_100",
            "timing_fake_contended_100",
            "timing_real_seq_100",
            "timing_real_contended_100",
        )
        if (cell := _load(cell_id)) is not None
    }
    bounded = _boundedness()
    modified = _load("modified_25")
    gates = _gates(bounded)
    summary = {
        "experiment_id": "18-ingestion-lock-scope-ab",
        "boundedness": bounded,
        "modified_25": (
            {
                "files_indexed": modified["one_file_modified"]["files_indexed"],
                "files_skipped": modified["one_file_modified"]["files_skipped_unchanged"],
            }
            if modified and modified.get("one_file_modified")
            else None
        ),
        "gates": gates,
        "timing": timing_rows,
        "decision_inputs": _decision(timing_rows),
        "phase_b": "reserved — H6/H7 evaluated only if a Stage 3B treatment variant is implemented",
    }
    out = HERE / "output" / "results.summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["gates"], indent=2))
    for name, row in timing_rows.items():
        print(
            f"{name}: wall={row['wall_seconds']}s lock_wait={row['lock_wait_seconds']}s "
            f"({row['lock_wait_fraction_of_wall']}) docs/s={row['docs_per_second']}",
            flush=True,
        )
    print(f"summary written to {out}", flush=True)


if __name__ == "__main__":
    main()
