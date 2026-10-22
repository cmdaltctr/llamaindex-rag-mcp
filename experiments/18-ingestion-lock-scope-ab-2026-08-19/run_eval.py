"""Runner for Experiment 18 — ingestion lock-scope baseline (Stage 3B gate).

Every measured cell executes in its own subprocess (``--single-cell``) so
``ru_maxrss`` peaks stay attributable to one cell and store state never
leaks between cells. The driver phase commands below orchestrate those
cells, checkpoint results atomically, and support ``--resume``.

Phases:
    boundedness   H1/H2/H5 — bounded node lifetime, RSS scaling, unchanged skip
    faults        H3/H4 — parse/embed/store-write failure safety and swap
    timing        lock-scope evidence — sequential vs 2-stream contended
    concurrency-ab  Phase B, reserved until a treatment variant exists

The pipeline is NOT re-instrumented: per-source timings and peak RSS are
read from the Stage 3A ingestion result contract.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

from harness import (
    OUTPUT_DIR,
    PROJECT_ROOT,
    atomic_json_write,
    build_fake_settings,
    build_runtime_manifest,
    child_environment,
    ensure_import_path,
    install_fake_runtime,
    install_real_runtime,
    ollama_available,
    ollama_model_present,
)

CELLS_DIR = OUTPUT_DIR / "cells"
# Phase-B repetitions write each arm/round into its own cells directory;
# ``--cells-dir`` sets this override for driver and single-cell workers alike.
CELLS_DIR_OVERRIDE: Path | None = None


def cells_dir() -> Path:
    """Return the active cells directory."""
    return CELLS_DIR_OVERRIDE if CELLS_DIR_OVERRIDE is not None else CELLS_DIR


SEED = 20260819
REAL_EMBED_MODEL = "nomic-embed-text"

# Cell matrix — MUST match plan.json (driver preflight asserts agreement).
CELLS: dict[str, dict] = {
    "bounded_25": {
        "corpus_size": 25,
        "failure_point": "none",
        "repeat_state": "first_plus_unchanged_second",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "bounded_100": {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "first_plus_unchanged_second",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "bounded_400": {
        "corpus_size": 400,
        "failure_point": "none",
        "repeat_state": "first_plus_unchanged_second",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "modified_25": {
        "corpus_size": 25,
        "failure_point": "none",
        "repeat_state": "one_file_modified",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "fault_none": {
        "corpus_size": 3,
        "failure_point": "none",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "fault_parse": {
        "corpus_size": 3,
        "failure_point": "parse",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "fault_embed": {
        "corpus_size": 3,
        "failure_point": "embed",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "fault_store_write": {
        "corpus_size": 3,
        "failure_point": "store_write",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "timing_fake_seq_100": {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    },
    "timing_fake_contended_100": {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "first",
        "ingest_topology": "concurrent_2_streams",
        "embedding_block": "fake_deterministic",
    },
    "timing_real_seq_100": {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "first",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "real_ollama",
    },
    "timing_real_contended_100": {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "first",
        "ingest_topology": "concurrent_2_streams",
        "embedding_block": "real_ollama",
    },
}

PHASE_CELLS: dict[str, list[str]] = {
    "boundedness": ["bounded_25", "bounded_100", "bounded_400", "modified_25"],
    "faults": ["fault_none", "fault_parse", "fault_embed", "fault_store_write"],
    "timing": [
        "timing_fake_seq_100",
        "timing_fake_contended_100",
        "timing_real_seq_100",
        "timing_real_contended_100",
    ],
}


def _generate_corpus(file_count: int, name: str) -> tuple[Path, str]:
    """Generate the deterministic corpus for one cell; return dir + identity."""
    from corpus import generate_corpus

    out = OUTPUT_DIR / name
    manifest = generate_corpus(out, file_count=file_count, seed=SEED)
    return out, manifest["corpus_identity"]


def _ingest(path: Path | str, settings, collection: str = "documents") -> dict:
    """Run one bounded ingestion and return the raw result contract."""
    from omrg.core.ingestion.pipeline import ingest_path_async

    return asyncio.run(
        ingest_path_async(
            str(path),
            collection_name=collection,
            effective_settings=settings,
        )
    )


def _peak_rss() -> int | None:
    ensure_import_path()
    from omrg.core.ingestion.metrics import sample_peak_rss_bytes

    return sample_peak_rss_bytes()


def _summarise_ingest(result: dict) -> dict:
    """Extract the timing/memory slice of one ingestion result."""
    details = result.get("file_details", [])
    return {
        "status": result.get("status"),
        "files_indexed": result.get("files_indexed", 0),
        "files_skipped_unchanged": result.get("files_skipped_unchanged", 0),
        "chunks_created": result.get("chunks_created", 0),
        "chunks_removed": result.get("chunks_removed", 0),
        "max_chunks_per_file": max((d.get("chunks", 0) for d in details), default=0),
        "timings": result.get("timings", {}),
        "peak_rss_bytes": result.get("peak_rss_bytes"),
    }


def run_bounded_cell(cell_id: str, size: int, modified: bool) -> dict:
    """Execute one boundedness cell: first ingest, unchanged repeat, optional edit."""
    corpus_dir, identity = _generate_corpus(size, f"corpus_{size}")
    store_dir = OUTPUT_DIR / f"chroma_{cells_dir().name}_{cell_id}"
    runtime = install_fake_runtime(store_dir)
    settings = build_fake_settings("documents", store_dir)
    manifest = build_runtime_manifest(
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_identity=identity,
    )
    started = time.perf_counter()
    first = _ingest(corpus_dir, settings)
    first_summary = _summarise_ingest(first)
    unchanged = _ingest(corpus_dir, settings)
    unchanged_summary = _summarise_ingest(unchanged)
    modified_summary = None
    if modified:
        target = sorted(corpus_dir.glob("source_*.txt"))[0]
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\nAmended tail.", encoding="utf-8"
        )
        modified_result = _ingest(corpus_dir, settings)
        modified_summary = _summarise_ingest(modified_result)
    return {
        "cell_id": cell_id,
        "factors": CELLS[cell_id],
        "manifest": manifest,
        "status": "completed",
        "wall_seconds": time.perf_counter() - started,
        "first": first_summary,
        "unchanged_second": unchanged_summary,
        "one_file_modified": modified_summary,
        "process_peak_rss_bytes": _peak_rss(),
    }


def run_fault_cell(cell_id: str, stage: str) -> dict:
    """Execute one fault-injection cell on a three-file corpus."""
    corpus_dir, identity = _generate_corpus(3, f"corpus_fault_{cell_id}")
    store_dir = OUTPUT_DIR / f"chroma_{cells_dir().name}_{cell_id}"
    runtime = install_fake_runtime(store_dir)
    store = runtime["store"]
    settings = build_fake_settings("documents", store_dir)
    manifest = build_runtime_manifest(
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_identity=identity,
    )

    ensure_import_path()
    from omrg.core.ingestion import pipeline as pipeline_module
    from omrg.core.ingestion import replacement as replacement_module

    initial = _ingest(corpus_dir, settings)
    target = sorted(corpus_dir.glob("source_*.txt"))[0]
    # Pipeline file order (os.walk) need not match sorted glob order; match
    # the detail row for the target file explicitly.
    target_detail = next(d for d in initial["file_details"] if d.get("file") == target.name)
    version_a = target_detail.get("source_version")
    rows_after_first = store.count_where("documents", {"file_path": str(target)})

    target.write_text(
        target.read_text(encoding="utf-8") + "\n\nReplacement content B.", encoding="utf-8"
    )

    injected_error: str | None = None
    failed_status: str | None = None
    if stage == "parse":
        original = pipeline_module.read_and_chunk_file_async

        async def _raise_parse(*args, **kwargs):
            raise RuntimeError("injected parse failure")

        pipeline_module.read_and_chunk_file_async = _raise_parse
        try:
            failed = _ingest(target, settings)
        finally:
            pipeline_module.read_and_chunk_file_async = original
    elif stage == "embed":
        original = replacement_module._embed_missing_nodes
        replacement_module._embed_missing_nodes = lambda nodes: (_ for _ in ()).throw(
            RuntimeError("injected embed failure")
        )
        try:
            failed = _ingest(target, settings)
        finally:
            replacement_module._embed_missing_nodes = original
    elif stage == "store_write":
        original = store.write_nodes
        store.write_nodes = lambda nodes, coll: (_ for _ in ()).throw(
            RuntimeError("injected store_write failure")
        )
        try:
            failed = _ingest(target, settings)
        finally:
            del store.__dict__["write_nodes"]
            _ = original
    else:
        failed = _ingest(target, settings)

    if stage != "none":
        failed_status = failed.get("status")
        details = failed.get("file_details", [])
        injected_error = details[0].get("failure_stage") if details else None
    old_rows = store.count_where("documents", {"file_path": str(target)})
    old_version_rows = sum(
        1
        for _, _, metadata in store.iter_documents("documents")
        if metadata.get("file_path") == str(target) and metadata.get("source_version") == version_a
    )

    # The recovery ingest completes the B replacement. For F0 the first
    # modified ingest already succeeded (that call IS the swap), so the
    # chunk/version evidence comes from it; the recovery call then merely
    # confirms idempotence (unchanged skip). For injected faults the
    # recovery ingest performs the deferred swap after disarm.
    recovery = _ingest(target, settings)
    recovery_detail = next(
        (d for d in recovery.get("file_details", []) if d.get("file") == target.name),
        {},
    )
    swap_detail = (
        next((d for d in failed.get("file_details", []) if d.get("file") == target.name), {})
        if stage == "none"
        else recovery_detail
    )
    version_b = swap_detail.get("source_version")
    rows_after_recovery = store.count_where("documents", {"file_path": str(target)})
    final_version_rows = sum(
        1
        for _, _, metadata in store.iter_documents("documents")
        if metadata.get("file_path") == str(target) and metadata.get("source_version") == version_b
    )
    return {
        "cell_id": cell_id,
        "factors": CELLS[cell_id],
        "manifest": manifest,
        "status": "completed",
        "failure_point": stage,
        "failed_ingest_status": failed_status if stage != "none" else None,
        "observed_failure_stage": injected_error,
        "rows_for_target_after_first": rows_after_first,
        "rows_for_target_after_failure": old_rows,
        "old_version_rows_after_failure": old_version_rows,
        "old_version_survived": old_version_rows == rows_after_first,
        "recovery_status": recovery.get("status"),
        "rows_for_target_after_recovery": rows_after_recovery,
        "swap_chunks": swap_detail.get("chunks", 0),
        "swap_completed": (
            swap_detail.get("status") in ("indexed", "skipped_unchanged")
            and rows_after_recovery == swap_detail.get("chunks", -1)
            and final_version_rows == swap_detail.get("chunks", -1)
        ),
    }


def _split_halves(corpus_dir: Path) -> tuple[Path, Path]:
    """Copy a corpus into two disjoint halves for the contended topology."""
    files = sorted(corpus_dir.glob("source_*.txt"))
    half1_dir = corpus_dir.parent / f"{corpus_dir.name}_h1"
    half2_dir = corpus_dir.parent / f"{corpus_dir.name}_h2"
    for dest, subset in (
        (half1_dir, files[: len(files) // 2]),
        (half2_dir, files[len(files) // 2 :]),
    ):
        dest.mkdir(parents=True, exist_ok=True)
        for existing in dest.glob("source_*.txt"):
            existing.unlink()
        for source in subset:
            shutil.copy2(source, dest / source.name)
    return half1_dir, half2_dir


def _ingest_both(half1: Path, half2: Path, settings) -> tuple[dict, dict]:
    """Run two ingest streams concurrently on one event loop."""

    async def _gather():
        from omrg.core.ingestion.pipeline import ingest_path_async

        return await asyncio.gather(
            ingest_path_async(str(half1), collection_name="documents", effective_settings=settings),
            ingest_path_async(str(half2), collection_name="documents", effective_settings=settings),
        )

    return asyncio.run(_gather())


def run_timing_cell(cell_id: str, block: str, topology: str) -> dict:
    """Execute one timing cell (sequential or 2-stream contended)."""
    if block == "real_ollama":
        if not ollama_available() or not ollama_model_present(REAL_EMBED_MODEL):
            return {
                "cell_id": cell_id,
                "factors": CELLS[cell_id],
                "status": "skipped",
                "skip_reason": "ollama or model unavailable",
            }
        corpus_dir, identity = _generate_corpus(100, "corpus_100")
        store_dir = OUTPUT_DIR / f"chroma_{cells_dir().name}_{cell_id}"
        runtime = install_real_runtime(store_dir)
        settings = build_fake_settings("documents", store_dir)
        warmup_dir = OUTPUT_DIR / "corpus_warmup"
        from corpus import generate_corpus

        generate_corpus(warmup_dir, file_count=2, seed=SEED + 1)
        warm_started = time.perf_counter()
        _ingest(warmup_dir, settings, collection="warmup")
        warmup_seconds = time.perf_counter() - warm_started
    else:
        corpus_dir, identity = _generate_corpus(100, "corpus_100")
        store_dir = OUTPUT_DIR / f"chroma_{cells_dir().name}_{cell_id}"
        runtime = install_fake_runtime(store_dir)
        settings = build_fake_settings("documents", store_dir)
        warmup_seconds = None
    manifest = build_runtime_manifest(
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_identity=identity,
    )

    if topology == "sequential_1_stream":
        started = time.perf_counter()
        result = _ingest(corpus_dir, settings)
        wall = time.perf_counter() - started
        streams = [_summarise_ingest(result)]
        combined = None
    else:
        half1, half2 = _split_halves(corpus_dir)
        started = time.perf_counter()
        results = _ingest_both(half1, half2, settings)
        wall = time.perf_counter() - started
        streams = [_summarise_ingest(r) for r in results]
        combined = {
            "files_total": sum(s["files_indexed"] for s in streams),
            "chunks_total": sum(s["chunks_created"] for s in streams),
            "lock_wait_seconds_total": sum(
                s["timings"].get("lock_wait_seconds", 0.0) for s in streams
            ),
        }
    return {
        "cell_id": cell_id,
        "factors": CELLS[cell_id],
        "manifest": manifest,
        "status": "completed",
        "warmup_seconds": warmup_seconds,
        "wall_seconds": wall,
        "streams": streams,
        "combined": combined,
        "process_peak_rss_bytes": _peak_rss(),
    }


def execute_single_cell(cell_id: str) -> None:
    """Dispatch and run one cell, writing its result atomically."""
    if cell_id.startswith("bounded_"):
        size = CELLS[cell_id]["corpus_size"]
        result = run_bounded_cell(cell_id, size, modified=False)
    elif cell_id == "modified_25":
        result = run_bounded_cell(cell_id, 25, modified=True)
    elif cell_id.startswith("fault_"):
        result = run_fault_cell(cell_id, CELLS[cell_id]["failure_point"])
    elif cell_id.startswith("timing_"):
        factors = CELLS[cell_id]
        result = run_timing_cell(cell_id, factors["embedding_block"], factors["ingest_topology"])
    else:
        raise SystemExit(f"unknown cell {cell_id}")
    atomic_json_write(cells_dir() / f"{cell_id}.json", result)
    print(f"CELL_DONE {cell_id} status={result.get('status')}", flush=True)


def preflight_plan() -> None:
    """Assert the runner cell matrix matches plan.json exactly."""
    ensure_import_path()
    from experiments._lib.plan import ExperimentPlan

    plan = ExperimentPlan.from_json(Path(__file__).parent / "plan.json")
    runner_cells = [{"id": cid, "factors": CELLS[cid]} for cid in CELLS]
    plan.assert_runner_cells(runner_cells)
    print(f"preflight: {len(CELLS)} cells agree with plan.json", flush=True)


def run_phase(phase: str, resume: bool) -> None:
    """Drive all cells of one phase in isolated subprocesses."""
    if phase == "concurrency-ab":
        print("Phase B reserved: no treatment variant exists yet", flush=True)
        raise SystemExit(3)
    preflight_plan()
    for cell_id in PHASE_CELLS[phase]:
        target = cells_dir() / f"{cell_id}.json"
        if resume and target.exists():
            print(f"resume: skip {cell_id}", flush=True)
            continue
        print(f"running cell {cell_id} ...", flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--single-cell", cell_id]
        if CELLS_DIR_OVERRIDE is not None:
            command.extend(["--cells-dir", str(CELLS_DIR_OVERRIDE)])
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=child_environment(OUTPUT_DIR),
            check=False,
        )
        if completed.returncode != 0:
            print(f"cell {cell_id} FAILED rc={completed.returncode}", flush=True)
    print(f"phase {phase} complete; results in {cells_dir()}", flush=True)


def run_smoke() -> None:
    """Prove the harness end-to-end with a five-file fake block, then clean."""
    global CELLS
    CELLS = dict(CELLS)
    CELLS["smoke_5"] = {
        "corpus_size": 5,
        "failure_point": "none",
        "repeat_state": "first_plus_unchanged_second",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
    }
    result = run_bounded_cell("smoke_5", 5, modified=False)
    first, second = result["first"], result["unchanged_second"]
    if first["status"] != "ok" or first["files_indexed"] != 5:
        raise SystemExit(f"smoke FAILED: first ingest unexpected: {first}")
    if first["chunks_created"] <= 0:
        raise SystemExit(f"smoke FAILED: no chunks created: {first}")
    if second["files_skipped_unchanged"] != 5 or second["chunks_created"] != 0:
        raise SystemExit(f"smoke FAILED: unchanged skip broken: {second}")
    print(
        f"smoke OK: 5 files, {first['chunks_created']} chunks, "
        f"second pass skipped {second['files_skipped_unchanged']}",
        flush=True,
    )
    shutil.rmtree(OUTPUT_DIR / "chroma_cells_smoke_5", ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR / "corpus_5", ignore_errors=True)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=[*PHASE_CELLS, "concurrency-ab", "ALL"])
    parser.add_argument("--single-cell", dest="single_cell")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--cells-dir",
        type=Path,
        help="override the cells output directory (Phase B arm/round isolation)",
    )
    args = parser.parse_args()
    global CELLS_DIR_OVERRIDE
    if args.cells_dir is not None:
        CELLS_DIR_OVERRIDE = args.cells_dir
        args.cells_dir.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        run_smoke()
    elif args.single_cell:
        execute_single_cell(args.single_cell)
    elif args.phase == "ALL":
        for phase in PHASE_CELLS:
            run_phase(phase, args.resume)
    elif args.phase:
        run_phase(args.phase, args.resume)
    else:
        parser.error("choose --phase, --single-cell, or --smoke")


if __name__ == "__main__":
    main()
