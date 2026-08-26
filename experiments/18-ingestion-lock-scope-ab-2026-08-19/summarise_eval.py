"""Summarise Experiment 18 cell results into gates and a decision record.

Loads ``output/cells/*.json``, evaluates hypotheses H1-H5 (Phase A
correctness gates) plus the lock-scope timing evidence, and writes
``output/results.summary.json``. With ``--ab`` it additionally compares the
Stage 3A baseline repetitions against the Stage 3B treatment repetitions
(``output/cells_stage3a_rep*/`` vs ``output/cells_stage3b_rep*/``) and
evaluates the Phase B gates H6/H7.
"""

from __future__ import annotations

import argparse
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


def _ab_comparison() -> dict:
    """Compare baseline vs treatment timing repetitions (Phase B)."""
    arms = {}
    for arm in ("stage3a", "stage3b"):
        rep_dirs = sorted((HERE / "output").glob(f"cells_{arm}_rep*"))
        cells = {}
        for rep_dir in rep_dirs:
            for cell_id in ("timing_fake_contended_100", "timing_real_contended_100"):
                path = rep_dir / f"{cell_id}.json"
                if not path.exists():
                    continue
                cell = json.loads(path.read_text(encoding="utf-8"))
                if cell.get("status") != "completed":
                    continue
                streams = cell.get("streams", [])
                files = sum(s.get("files_indexed", 0) for s in streams)
                wall = cell.get("wall_seconds") or 0.0
                lock_wait = sum(s.get("timings", {}).get("lock_wait_seconds", 0.0) for s in streams)
                cells.setdefault(cell_id, []).append(
                    {
                        "rep": rep_dir.name,
                        "wall_seconds": round(wall, 3),
                        "docs_per_second": round(files / wall, 2) if wall else None,
                        "lock_wait_fraction": round(lock_wait / wall, 4) if wall else None,
                        "peak_rss_bytes": cell.get("process_peak_rss_bytes"),
                        "repo_commit": cell.get("manifest", {}).get("repo_commit"),
                        "git_dirty": cell.get("manifest", {}).get("git_dirty"),
                    }
                )
        arms[arm] = cells
    verdict = {}
    for cell_id in ("timing_fake_contended_100", "timing_real_contended_100"):
        base = arms["stage3a"].get(cell_id, [])
        treat = arms["stage3b"].get(cell_id, [])
        if not base or not treat:
            verdict[cell_id] = {"status": "missing repetitions"}
            continue
        base_rate = sum(r["docs_per_second"] for r in base) / len(base)
        treat_rate = sum(r["docs_per_second"] for r in treat) / len(treat)
        base_rss = max(r["peak_rss_bytes"] or 0 for r in base)
        treat_rss = max(r["peak_rss_bytes"] or 0 for r in treat)
        verdict[cell_id] = {
            "baseline_docs_per_second_mean": round(base_rate, 2),
            "treatment_docs_per_second_mean": round(treat_rate, 2),
            "throughput_improvement_fraction": round((treat_rate - base_rate) / base_rate, 4)
            if base_rate
            else None,
            "baseline_lock_wait_fraction_mean": round(
                sum(r["lock_wait_fraction"] for r in base) / len(base), 4
            ),
            "treatment_lock_wait_fraction_mean": round(
                sum(r["lock_wait_fraction"] for r in treat) / len(treat), 4
            ),
            "peak_rss_ratio_treatment_over_baseline": round(treat_rss / base_rss, 4)
            if base_rss and treat_rss
            else None,
            "repetitions": {"stage3a": len(base), "stage3b": len(treat)},
        }
    real = verdict.get("timing_real_contended_100", {})
    improvement = real.get("throughput_improvement_fraction")
    rss_ratio = real.get("peak_rss_ratio_treatment_over_baseline")
    correctness_dir = HERE / "output" / "cells_stage3b_correctness"
    correctness_ok = None
    if correctness_dir.exists():
        correctness_cells = {
            p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in correctness_dir.glob("*.json")
        }
        bounded = {
            size: correctness_cells.get(f"bounded_{size}")
            for size in (25, 100, 400)
            if correctness_cells.get(f"bounded_{size}")
        }
        faults_ok = all(
            correctness_cells.get(f"fault_{stage}", {}).get("old_version_survived")
            for stage in ("parse", "embed", "store_write")
            if correctness_cells.get(f"fault_{stage}")
        )
        correctness_ok = bool(bounded) and faults_ok
    h6 = bool(improvement is not None and improvement >= 0.20)
    h7 = bool(rss_ratio is not None and rss_ratio <= 1.25 and correctness_ok is True)
    return {
        "cells": arms,
        "verdict": verdict,
        "gates": {
            "H6_throughput_ge_20pct_real_contended": h6,
            "H7_rss_le_1_25x_and_correctness_green": h7,
            "treatment_correctness_dir_found": correctness_ok,
        },
    }


def main() -> None:
    """Load cells, evaluate gates, write summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ab",
        action="store_true",
        help="also evaluate the Phase B baseline-vs-treatment repetitions",
    )
    args = parser.parse_args()
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
    print(json.dumps(summary["gates"], indent=2))
    for name, row in timing_rows.items():
        print(
            f"{name}: wall={row['wall_seconds']}s lock_wait={row['lock_wait_seconds']}s "
            f"({row['lock_wait_fraction_of_wall']}) docs/s={row['docs_per_second']}",
            flush=True,
        )
    if args.ab:
        ab = _ab_comparison()
        summary["phase_b_ab"] = ab
        out_ab = HERE / "output" / "results.ab.json"
        out_ab.write_text(json.dumps(ab, indent=2), encoding="utf-8")
        print(json.dumps(ab["gates"], indent=2))
        for cell_id, verdict in ab["verdict"].items():
            print(f"{cell_id}: {verdict}", flush=True)
        print(f"A/B summary written to {out_ab}", flush=True)
    out = HERE / "output" / "results.summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary written to {out}", flush=True)


if __name__ == "__main__":
    main()
