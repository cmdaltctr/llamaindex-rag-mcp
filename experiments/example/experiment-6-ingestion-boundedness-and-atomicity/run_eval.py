"""Runner for the Experiment 6 template — ingestion boundedness and atomicity.

Stage 5 task 5.6 execution against CURRENT code (Stage 3B narrow lock
retained at HEAD).  Phase A (boundedness H1/H2, unchanged-skip H5, fault
safety H3, swap H4) is the mandatory battery.  Phase B (``--phase
concurrency-ab``) is CONFIRMING EVIDENCE ONLY: it measures current-code
contended throughput and compares it descriptively against experiment 18's
recorded Stage 3B arm; the Stage 3A baseline no longer exists at HEAD.

Every measured cell runs in its own subprocess (``--single-cell``) so
``ru_maxrss`` peaks stay attributable to one cell.  The driver prepares and
identity-checks generated corpora, asserts plan/runner agreement, spawns
cells, merges raw rows atomically, and supports ``--resume``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from harness import (  # noqa: I001 — harness lives beside this runner
    CORPUS_MANIFESTS_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    REAL_EMBED_MODEL,
    atomic_json_write,
    build_fake_settings,
    child_environment,
    ensure_import_path,
    install_embed_counter,
    install_fake_runtime,
    install_real_runtime,
    install_replacement_probe,
    install_store_write_counter,
    manifest_for_cell,
    ollama_available,
    ollama_model_present,
    peak_rss_bytes,
)

SEED = 20260806
TARGET_CHARS = 6000
CORPUS_SIZES = (0, 3, 25, 100, 400)
WARMUP_SEED = SEED + 1

# Cell matrix — MUST match plan.json (driver preflight asserts agreement).
CELLS: dict[str, dict[str, Any]] = {}


def _register_cells() -> None:
    """Populate CELLS in deterministic order (ids must match plan.json)."""
    for rep in (1, 2, 3):
        CELLS[f"rss_baseline_rep{rep}"] = {
            "corpus_size": 0,
            "failure_point": "none",
            "repeat_state": "noop_empty_dir",
            "ingest_topology": "sequential_1_stream",
            "embedding_block": "fake_deterministic",
            "run_phase": "boundedness",
        }
    for size in (25, 100, 400):
        for rep in (1, 2, 3):
            CELLS[f"boundedness_{size}_rep{rep}"] = {
                "corpus_size": size,
                "failure_point": "none",
                "repeat_state": "first_plus_unchanged_second",
                "ingest_topology": "sequential_1_stream",
                "embedding_block": "fake_deterministic",
                "run_phase": "boundedness",
            }
    CELLS["modified_100_rep1"] = {
        "corpus_size": 100,
        "failure_point": "none",
        "repeat_state": "one_file_modified",
        "ingest_topology": "sequential_1_stream",
        "embedding_block": "fake_deterministic",
        "run_phase": "boundedness",
    }
    for stage in ("none", "parse", "embed", "store_write"):
        CELLS[f"fault_{stage}"] = {
            "corpus_size": 3,
            "failure_point": stage,
            "repeat_state": "first",
            "ingest_topology": "sequential_1_stream",
            "embedding_block": "fake_deterministic",
            "run_phase": "faults",
        }
    for rep in (1, 2, 3):
        CELLS[f"confirm_fake_contended_100_rep{rep}"] = {
            "corpus_size": 100,
            "failure_point": "none",
            "repeat_state": "first",
            "ingest_topology": "concurrent_2_streams",
            "embedding_block": "fake_deterministic",
            "run_phase": "concurrency_ab",
        }
    for rep in (1, 2, 3):
        CELLS[f"confirm_real_contended_100_rep{rep}"] = {
            "corpus_size": 100,
            "failure_point": "none",
            "repeat_state": "first",
            "ingest_topology": "concurrent_2_streams",
            "embedding_block": "real_ollama",
            "run_phase": "concurrency_ab",
        }


_register_cells()

PHASE_CELLS: dict[str, list[str]] = {
    "boundedness": [cid for cid in CELLS if CELLS[cid]["run_phase"] == "boundedness"],
    "faults": [cid for cid in CELLS if CELLS[cid]["run_phase"] == "faults"],
    "concurrency-ab": [cid for cid in CELLS if CELLS[cid]["run_phase"] == "concurrency_ab"],
}

CELLS_DIR = OUTPUT_DIR / "cells"
RERUN_PROOF_DIR = OUTPUT_DIR / "rerun_proof"
RAW_ROWS_PATH = OUTPUT_DIR / "results.raw.json"
CELL_RECORDS_PATH = OUTPUT_DIR / "cell_records.json"


# ── Corpus preparation ────────────────────────────────────────────────────


def corpus_dir_for(size: int) -> Path:
    """Return the transient generated-corpus directory for one size."""
    return OUTPUT_DIR / f"gencorpus_{size}"


def corpus_manifest_path_for(size: int) -> Path:
    """Return the committed corpus-manifest copy for one size."""
    return CORPUS_MANIFESTS_DIR / f"corpus_{size}.json"


def prepare_corpora(sizes: tuple[int, ...] = CORPUS_SIZES) -> dict[int, str]:
    """Generate or verify corpora; write committed manifest copies.

    Returns size → corpus_identity.  When the committed copy exists, the
    regenerated corpus must reproduce its identity byte-for-byte — the
    generator determinism gate (protocol §12 corpus checksums).
    """
    from corpus import generate_corpus

    CORPUS_MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    identities: dict[int, str] = {}
    for size in sizes:
        target = corpus_manifest_path_for(size)
        manifest = generate_corpus(
            corpus_dir_for(size),
            file_count=size,
            seed=SEED,
            target_chars=TARGET_CHARS,
        )
        identity = manifest["corpus_identity"]
        if target.exists():
            committed = target.read_text(encoding="utf-8")
            if committed != (corpus_dir_for(size) / "manifest.json").read_text(encoding="utf-8"):
                raise SystemExit(
                    f"corpus determinism gate failed for size {size}: regenerated "
                    f"manifest differs from committed copy {target}"
                )
        else:
            shutil.copy2(corpus_dir_for(size) / "manifest.json", target)
        identities[size] = identity
        print(f"corpus size {size}: identity {identity[:12]}", flush=True)
    return identities


# ── Ingestion helpers ─────────────────────────────────────────────────────


def _ingest(path: Path | str, settings: Any, collection: str = "documents") -> dict[str, Any]:
    """Run one bounded ingestion and return the raw result contract."""
    from rag_mcp.core.ingestion.pipeline import ingest_path_async

    return asyncio.run(
        ingest_path_async(
            str(path),
            collection_name=collection,
            effective_settings=settings,
        )
    )


def _summarise_ingest(result: dict[str, Any]) -> dict[str, Any]:
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


def _reset_counts(counts: dict[str, int]) -> None:
    """Zero a counter dict in place (keys stay present for the wrappers)."""
    counts.update({key: 0 for key in counts})


def _probe_snapshot(probe: dict[str, int]) -> dict[str, int]:
    """Copy the boundedness probe state."""
    return dict(probe)


def _preflight_cell(manifest: dict[str, Any], plan_assertions: list[dict[str, Any]]) -> None:
    """Run plan assertions plus the fallback abort against one manifest."""
    from experiments._lib.preflight import assert_manifest, assert_no_fallback

    assert_manifest(manifest, plan_assertions)
    assert_no_fallback(manifest)


def _load_plan() -> Any:
    ensure_import_path()
    from experiments._lib.plan import ExperimentPlan

    return ExperimentPlan.from_json(Path(__file__).resolve().parent / "plan.json")


# ── Boundedness cells ─────────────────────────────────────────────────────


def run_boundedness_cell(cell_id: str, factors: dict[str, Any], out_dir: Path) -> None:
    """Execute one boundedness cell in this subprocess.

    Sizes 25/100/400: clean first ingest + unchanged repeat (H2/H5), with
    embedding/store-write call counters and the replacement-batch probe
    (H1).  ``modified_100`` adds a one-file modification ingest.  Size 0
    measures the no-op RSS baseline used by the frozen H2 guard.
    """
    size = factors["corpus_size"]
    repeat = factors["repeat_state"]
    corpus_dir = corpus_dir_for(size)
    corpus_manifest_path = corpus_manifest_path_for(size)
    store_dir = OUTPUT_DIR / f"store_{out_dir.name}_{cell_id}"
    runtime = install_fake_runtime(store_dir)
    settings = build_fake_settings("documents", store_dir)
    embed_counts = install_embed_counter()
    write_counts = install_store_write_counter(runtime["store"])
    probe = install_replacement_probe()
    manifest = manifest_for_cell(
        cell_id=cell_id,
        run_phase="boundedness",
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_manifest_path=corpus_manifest_path,
        settings=settings,
    )
    plan = _load_plan()
    _preflight_cell(manifest, list(plan.required_manifest_assertions))
    if manifest["embedding"]["model"] != "mock-deterministic-v1":
        raise SystemExit("preflight: fake block model mismatch")
    sampler = peak_rss_bytes()
    if sampler is None:
        raise SystemExit("preflight: RSS sampler not functioning on this platform")
    files_present = len(list(corpus_dir.glob("source_*.txt")))
    if files_present != size:
        raise SystemExit(f"preflight: corpus file count {files_present} != {size}")

    rows: list[dict[str, Any]] = []

    def _row(query_id: str, wall: float, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "cell_id": cell_id,
            "query_id": query_id,
            "phase": "measured",
            "latency_ms": round(wall * 1000.0, 3),
            "metrics": {
                **summary,
                "embed_seam_calls": embed_counts["embed_seam_calls"],
                "nodes_embedded": embed_counts["nodes_embedded"],
                "store_write_calls": write_counts["write_calls"],
                "nodes_written": write_counts["nodes_written"],
                "probe": _probe_snapshot(probe),
                "docs_per_second": (
                    round(summary["files_indexed"] / wall, 4)
                    if wall and summary["files_indexed"]
                    else None
                ),
            },
        }

    started = time.perf_counter()
    if size == 0:
        result = _ingest(corpus_dir, settings)
        wall = time.perf_counter() - started
        rows.append(_row(f"{cell_id}#noop", wall, _summarise_ingest(result)))
        summaries: dict[str, Any] = {"noop": _summarise_ingest(result)}
    else:
        t0 = time.perf_counter()
        first = _ingest(corpus_dir, settings)
        wall_first = time.perf_counter() - t0
        first_summary = _summarise_ingest(first)
        rows.append(_row(f"{cell_id}#first", wall_first, first_summary))
        _reset_counts(embed_counts)
        _reset_counts(write_counts)

        t1 = time.perf_counter()
        second = _ingest(corpus_dir, settings)
        wall_second = time.perf_counter() - t1
        second_summary = _summarise_ingest(second)
        second_row = _row(f"{cell_id}#unchanged_second", wall_second, second_summary)
        second_row["metrics"]["embed_seam_calls"] = embed_counts["embed_seam_calls"]
        second_row["metrics"]["nodes_embedded"] = embed_counts["nodes_embedded"]
        second_row["metrics"]["store_write_calls"] = write_counts["write_calls"]
        second_row["metrics"]["nodes_written"] = write_counts["nodes_written"]
        rows.append(second_row)
        _reset_counts(embed_counts)
        _reset_counts(write_counts)

        summaries = {"first": first_summary, "unchanged_second": second_summary}
        if repeat == "one_file_modified":
            target = sorted(corpus_dir.glob("source_*.txt"))[0]
            target.write_text(
                target.read_text(encoding="utf-8") + "\n\nAmended tail for exp 6.",
                encoding="utf-8",
            )
            t2 = time.perf_counter()
            modified = _ingest(corpus_dir, settings)
            wall_modified = time.perf_counter() - t2
            modified_summary = _summarise_ingest(modified)
            modified_row = _row(f"{cell_id}#modified", wall_modified, modified_summary)
            modified_row["metrics"]["embed_seam_calls"] = embed_counts["embed_seam_calls"]
            modified_row["metrics"]["nodes_embedded"] = embed_counts["nodes_embedded"]
            modified_row["metrics"]["store_write_calls"] = write_counts["write_calls"]
            modified_row["metrics"]["nodes_written"] = write_counts["nodes_written"]
            rows.append(modified_row)
            summaries["one_file_modified"] = modified_summary

    record = {
        "status": "complete",
        "cell_id": cell_id,
        "factors": factors,
        "manifest": manifest,
        "rows": rows,
        "summaries": summaries,
        "process_peak_rss_bytes": peak_rss_bytes(),
        "wall_seconds": time.perf_counter() - started,
    }
    atomic_json_write(out_dir / f"{cell_id}.json", record)
    print(f"CELL_DONE {cell_id} status=complete", flush=True)


# ── Fault-injection cells ─────────────────────────────────────────────────

INJECTION_MARKERS = {
    "parse": "injected parse failure",
    "embed": "injected embed failure",
    "store_write": "injected store_write failure",
}
EXPECTED_FAILURE_STAGE = {
    "parse": "file",
    "embed": "embedding",
    "store_write": "store_write",
}


def run_fault_cell(cell_id: str, factors: dict[str, Any], out_dir: Path) -> None:
    """Execute one fault-injection cell (F0-F3) on a three-file corpus.

    Sequence: ingest version A (gate: A searchable), modify target to B,
    arm the injector at the declared stage, ingest B (must fail at that
    stage), verify A rows survive untouched, disarm, recovery-ingest B,
    verify the swap completed with zero stale rows.
    """
    ensure_import_path()
    from rag_mcp.core.ingestion import pipeline as pipeline_module
    from rag_mcp.core.ingestion import replacement as replacement_module

    stage = factors["failure_point"]
    corpus_dir = corpus_dir_for(3)
    corpus_manifest_path = corpus_manifest_path_for(3)
    store_dir = OUTPUT_DIR / f"store_{out_dir.name}_{cell_id}"
    runtime = install_fake_runtime(store_dir)
    store = runtime["store"]
    settings = build_fake_settings("documents", store_dir)
    manifest = manifest_for_cell(
        cell_id=cell_id,
        run_phase="faults",
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_manifest_path=corpus_manifest_path,
        settings=settings,
    )
    plan = _load_plan()
    _preflight_cell(manifest, list(plan.required_manifest_assertions))
    if peak_rss_bytes() is None:
        raise SystemExit("preflight: RSS sampler not functioning on this platform")

    initial = _ingest(corpus_dir, settings)
    if initial.get("status") != "ok" or initial.get("files_indexed") != 3:
        raise SystemExit(f"preflight: initial ingest unexpected: {initial.get('status')}")
    target = sorted(corpus_dir.glob("source_*.txt"))[0]
    target_detail = next((d for d in initial["file_details"] if d.get("file") == target.name), None)
    if target_detail is None:
        raise SystemExit("preflight: target file missing from initial ingest details")
    version_a = target_detail.get("source_version")
    rows_after_first = store.count_where("documents", {"file_path": str(target)})
    if rows_after_first != target_detail.get("chunks") or rows_after_first == 0:
        raise SystemExit(
            f"preflight: version A not searchable before fault injection "
            f"(rows={rows_after_first}, chunks={target_detail.get('chunks')})"
        )

    target.write_text(
        target.read_text(encoding="utf-8") + "\n\nReplacement content B for exp 6.",
        encoding="utf-8",
    )

    def _raise(marker: str):
        def _raiser(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(marker)

        return _raiser

    original_parse = pipeline_module.read_and_chunk_file_async
    original_embed = replacement_module._embed_missing_nodes
    marker = INJECTION_MARKERS.get(stage)
    try:
        if stage == "parse":
            pipeline_module.read_and_chunk_file_async = _raise(marker)
        elif stage == "embed":
            replacement_module._embed_missing_nodes = _raise(marker)
        elif stage == "store_write":
            store.write_nodes = _raise(marker)
        failed = _ingest(target, settings)
    finally:
        pipeline_module.read_and_chunk_file_async = original_parse
        replacement_module._embed_missing_nodes = original_embed
        if stage == "store_write" and "write_nodes" in store.__dict__:
            del store.__dict__["write_nodes"]

    failure_detail = next(
        (d for d in failed.get("file_details", []) if d.get("file") == target.name), {}
    )
    error_text = str(failure_detail.get("error", ""))
    injection_marker_seen = bool(marker) and marker in error_text
    if stage != "none" and not injection_marker_seen:
        raise SystemExit(
            f"preflight: injector did not fire at stage {stage!r}; error observed: {error_text!r}"
        )
    observed_failure_stage = failure_detail.get("failure_stage")

    rows_after_failure = store.count_where("documents", {"file_path": str(target)})
    old_version_rows = sum(
        1
        for _, _, metadata in store.iter_documents("documents")
        if metadata.get("file_path") == str(target) and metadata.get("source_version") == version_a
    )
    old_version_survived = rows_after_failure == rows_after_first and (
        old_version_rows == rows_after_first
    )

    recovery = _ingest(target, settings)
    recovery_detail = next(
        (d for d in recovery.get("file_details", []) if d.get("file") == target.name), {}
    )
    swap_detail = failure_detail if stage == "none" else recovery_detail
    version_b = swap_detail.get("source_version")
    final_rows = store.count_where("documents", {"file_path": str(target)})
    version_b_rows = sum(
        1
        for _, _, metadata in store.iter_documents("documents")
        if metadata.get("file_path") == str(target) and metadata.get("source_version") == version_b
    )
    stale_rows = final_rows - version_b_rows
    swap_completed = (
        swap_detail.get("status") in ("indexed", "skipped_unchanged")
        and version_b is not None
        and final_rows == swap_detail.get("chunks", -1)
        and version_b_rows == swap_detail.get("chunks", -1)
        and stale_rows == 0
    )

    evidence = {
        "cell_id": cell_id,
        "factors": factors,
        "manifest": manifest,
        "status": "complete",
        "failure_point": stage,
        "failed_ingest_status": failed.get("status") if stage != "none" else None,
        "observed_failure_stage": observed_failure_stage,
        "expected_failure_stage": EXPECTED_FAILURE_STAGE.get(stage),
        "injection_marker": marker,
        "injection_marker_seen": injection_marker_seen,
        "rows_for_target_after_first": rows_after_first,
        "rows_for_target_after_failure": rows_after_failure,
        "old_version_rows_after_failure": old_version_rows,
        "old_version_survived": old_version_survived,
        "recovery_status": recovery.get("status"),
        "recovery_files_indexed": recovery.get("files_indexed"),
        "recovery_files_skipped_unchanged": recovery.get("files_skipped_unchanged"),
        "rows_for_target_after_recovery": final_rows,
        "final_version": version_b,
        "final_version_rows": version_b_rows,
        "stale_rows_after_recovery": stale_rows,
        "swap_chunks": swap_detail.get("chunks", 0),
        "swap_completed": swap_completed,
        "process_peak_rss_bytes": peak_rss_bytes(),
    }
    atomic_json_write(out_dir / f"{cell_id}.json", evidence)
    print(
        f"CELL_DONE {cell_id} status=complete "
        f"old_survived={old_version_survived} swap={swap_completed}",
        flush=True,
    )


DETERMINISTIC_FAULT_FIELDS = (
    "failure_point",
    "observed_failure_stage",
    "expected_failure_stage",
    "injection_marker",
    "injection_marker_seen",
    "rows_for_target_after_first",
    "rows_for_target_after_failure",
    "old_version_rows_after_failure",
    "old_version_survived",
    "recovery_status",
    "recovery_files_indexed",
    "recovery_files_skipped_unchanged",
    "rows_for_target_after_recovery",
    "final_version_rows",
    "stale_rows_after_recovery",
    "swap_chunks",
    "swap_completed",
)


# ── Phase B confirming cells ──────────────────────────────────────────────


def _split_halves(cell_id: str) -> tuple[Path, Path]:
    """Copy the size-100 corpus into two disjoint halves (fresh per cell)."""
    corpus_dir = corpus_dir_for(100)
    files = sorted(corpus_dir.glob("source_*.txt"))
    half1 = OUTPUT_DIR / f"split_{cell_id}_h1"
    half2 = OUTPUT_DIR / f"split_{cell_id}_h2"
    for dest, subset in (
        (half1, files[: len(files) // 2]),
        (half2, files[len(files) // 2 :]),
    ):
        dest.mkdir(parents=True, exist_ok=True)
        for existing in dest.glob("source_*.txt"):
            existing.unlink()
        for source in subset:
            shutil.copy2(source, dest / source.name)
    return half1, half2


def _ingest_both(half1: Path, half2: Path, settings: Any) -> list[dict[str, Any]]:
    """Run two ingest streams concurrently on one event loop."""

    async def _gather() -> list[dict[str, Any]]:
        from rag_mcp.core.ingestion.pipeline import ingest_path_async

        results = await asyncio.gather(
            ingest_path_async(str(half1), collection_name="documents", effective_settings=settings),
            ingest_path_async(str(half2), collection_name="documents", effective_settings=settings),
        )
        return list(results)

    return asyncio.run(_gather())


def run_confirming_cell(cell_id: str, factors: dict[str, Any], out_dir: Path) -> None:
    """Execute one Phase B confirming cell (current code, 2-stream contended).

    Confirming-only framing: single variant (HEAD), fresh store, compared
    descriptively against experiment 18's Stage 3B arm in the summariser.
    """
    block = factors["embedding_block"]
    corpus_manifest_path = corpus_manifest_path_for(100)
    store_dir = OUTPUT_DIR / f"store_{out_dir.name}_{cell_id}"
    warmup_rows: list[dict[str, Any]] = []

    if block == "real_ollama":
        if not ollama_available() or not ollama_model_present(REAL_EMBED_MODEL):
            record = {
                "status": "invalid",
                "reason": (
                    "BLOCKED real-runtime arm: Ollama daemon or "
                    f"{REAL_EMBED_MODEL} unavailable; not silently substituted"
                ),
                "cell_id": cell_id,
                "factors": factors,
            }
            atomic_json_write(out_dir / f"{cell_id}.json", record)
            print(f"CELL_DONE {cell_id} status=invalid (BLOCKED real arm)", flush=True)
            return
        runtime = install_real_runtime(store_dir)
        expected_model = REAL_EMBED_MODEL
    else:
        runtime = install_fake_runtime(store_dir)
        expected_model = "mock-deterministic-v1"

    settings = build_fake_settings("documents", store_dir)
    embed_counts = install_embed_counter()
    write_counts = install_store_write_counter(runtime["store"])
    probe = install_replacement_probe()
    manifest = manifest_for_cell(
        cell_id=cell_id,
        run_phase="concurrency_ab",
        embedding=runtime["embedding"],
        vector_store=runtime["vector_store"],
        corpus_manifest_path=corpus_manifest_path,
        settings=settings,
        extra={
            "phase_b_mode": "confirming_only",
            "reference": "experiments/18-ingestion-lock-scope-ab-2026-08-19 stage3b arm",
        },
    )
    plan = _load_plan()
    _preflight_cell(manifest, list(plan.required_manifest_assertions))
    if manifest["embedding"]["model"] != expected_model:
        raise SystemExit(
            f"preflight: {block} block model mismatch: "
            f"{manifest['embedding']['model']!r} != {expected_model!r}"
        )
    if peak_rss_bytes() is None:
        raise SystemExit("preflight: RSS sampler not functioning on this platform")

    if block == "real_ollama":
        from corpus import generate_corpus

        warmup_dir = OUTPUT_DIR / "gencorpus_warmup"
        generate_corpus(warmup_dir, file_count=2, seed=WARMUP_SEED, target_chars=TARGET_CHARS)
        t_warm = time.perf_counter()
        warmup_result = _ingest(warmup_dir, settings, collection="warmup")
        warmup_wall = time.perf_counter() - t_warm
        warmup_summary = _summarise_ingest(warmup_result)
        _reset_counts(embed_counts)
        _reset_counts(write_counts)
        warmup_rows = [
            {
                "cell_id": cell_id,
                "query_id": f"{cell_id}#warmup",
                "phase": "warmup",
                "latency_ms": round(warmup_wall * 1000.0, 3),
                "metrics": warmup_summary,
            }
        ]

    half1, half2 = _split_halves(cell_id)
    started = time.perf_counter()
    results = _ingest_both(half1, half2, settings)
    wall = time.perf_counter() - started

    rows: list[dict[str, Any]] = list(warmup_rows)
    streams = []
    for index, result in enumerate(results):
        summary = _summarise_ingest(result)
        streams.append(summary)
        rows.append(
            {
                "cell_id": cell_id,
                "query_id": f"{cell_id}#stream{index + 1}",
                "phase": "measured",
                "latency_ms": round(wall * 1000.0, 3),
                "metrics": summary,
            }
        )
    files_total = sum(s["files_indexed"] for s in streams)
    lock_wait_total = sum(s["timings"].get("lock_wait_seconds", 0.0) for s in streams)
    combined = {
        "files_total": files_total,
        "chunks_total": sum(s["chunks_created"] for s in streams),
        "wall_seconds": round(wall, 3),
        "docs_per_second": round(files_total / wall, 4) if wall else None,
        "lock_wait_seconds_total": round(lock_wait_total, 4),
        "lock_wait_fraction_of_wall": round(lock_wait_total / wall, 4) if wall else None,
        "stage_seconds_total": {
            key: round(sum(s["timings"].get(key, 0.0) for s in streams), 4)
            for key in (
                "change_detection_seconds",
                "parse_chunk_seconds",
                "embedding_seconds",
                "store_write_seconds",
                "lock_wait_seconds",
                "cleanup_seconds",
            )
        },
        "embed_seam_calls": embed_counts["embed_seam_calls"],
        "store_write_calls": write_counts["write_calls"],
        "probe": _probe_snapshot(probe),
    }
    record = {
        "status": "complete",
        "cell_id": cell_id,
        "factors": factors,
        "manifest": manifest,
        "rows": rows,
        "streams": streams,
        "combined": combined,
        "process_peak_rss_bytes": peak_rss_bytes(),
        "phase_b_mode": "confirming_only",
    }
    atomic_json_write(out_dir / f"{cell_id}.json", record)
    print(
        f"CELL_DONE {cell_id} status=complete docs/s={combined['docs_per_second']} "
        f"lock_wait_frac={combined['lock_wait_fraction_of_wall']}",
        flush=True,
    )


# ── Driver ────────────────────────────────────────────────────────────────


def execute_single_cell(cell_id: str, out_dir: Path) -> None:
    """Dispatch and run one cell, writing its result atomically."""
    factors = CELLS[cell_id]
    phase = factors["run_phase"]
    if phase == "boundedness":
        run_boundedness_cell(cell_id, factors, out_dir)
    elif phase == "faults":
        run_fault_cell(cell_id, factors, out_dir)
    else:
        run_confirming_cell(cell_id, factors, out_dir)


def preflight_plan() -> None:
    """Assert the runner cell matrix matches plan.json exactly."""
    plan = _load_plan()
    runner_cells = [{"id": cid, "factors": CELLS[cid]} for cid in CELLS]
    plan.assert_runner_cells(runner_cells)
    print(f"preflight: {len(CELLS)} cells agree with plan.json", flush=True)


def _merge_cell(cell_path: Path, rows_out: Path, records_out: Path) -> str | None:
    """Merge one finished cell file into the raw-rows and records artefacts."""
    from experiments._lib.stats import finalise_cells, validate_per_query_rows

    cell = json.loads(cell_path.read_text(encoding="utf-8"))
    rows = json.loads(rows_out.read_text(encoding="utf-8")) if rows_out.exists() else []
    records = json.loads(records_out.read_text(encoding="utf-8")) if records_out.exists() else []
    cell_rows = cell.get("rows", [])
    validate_per_query_rows(cell_rows)
    rows.extend(cell_rows)
    record = {k: v for k, v in cell.items() if k != "rows"}
    records.append(record)
    finalise_cells(records)
    atomic_json_write(rows_out, rows)
    atomic_json_write(records_out, records)
    return cell.get("status")


def run_phase(
    phase: str,
    resume: bool,
    out_dir: Path = CELLS_DIR,
    merge: bool = True,
) -> None:
    """Drive all cells of one phase in isolated subprocesses.

    ``merge=False`` keeps a secondary run (the rerun proof) out of the
    primary raw-rows/records artefacts.
    """
    preflight_plan()
    prepare_corpora()
    out_dir.mkdir(parents=True, exist_ok=True)
    for cell_id in PHASE_CELLS[phase]:
        target = out_dir / f"{cell_id}.json"
        if resume and target.exists():
            status = json.loads(target.read_text(encoding="utf-8")).get("status")
            if status == "complete":
                print(f"resume: skip {cell_id}", flush=True)
                continue
        print(f"running cell {cell_id} ...", flush=True)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--single-cell",
            cell_id,
            "--out-dir",
            str(out_dir),
        ]
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=child_environment(),
            check=False,
        )
        if completed.returncode != 0 or not target.exists():
            print(f"cell {cell_id} FAILED rc={completed.returncode}", flush=True)
            record = {
                "status": "incomplete",
                "reason": f"cell process failed rc={completed.returncode}",
                "cell_id": cell_id,
                "factors": CELLS[cell_id],
            }
            atomic_json_write(target, record)
        if merge:
            status = _merge_cell(target, RAW_ROWS_PATH, CELL_RECORDS_PATH)
            print(f"merged {cell_id} status={status}", flush=True)
    print(f"phase {phase} complete; results in {out_dir}", flush=True)


def remerge_all() -> None:
    """Rebuild raw-rows and cell-records artefacts from ``output/cells``.

    Recovery path: after a secondary run (rerun proof) or an interrupted
    merge, rebuild the primary aggregates from the canonical cell files.
    """
    ensure_import_path()
    for path in (RAW_ROWS_PATH, CELL_RECORDS_PATH):
        if path.exists():
            path.unlink()
    for cell_path in sorted(CELLS_DIR.glob("*.json")):
        status = _merge_cell(cell_path, RAW_ROWS_PATH, CELL_RECORDS_PATH)
        print(f"remerged {cell_path.stem} status={status}", flush=True)


def run_rerun_proof() -> None:
    """Re-run every fault cell exactly and diff the deterministic slice."""
    run_phase("faults", resume=False, out_dir=RERUN_PROOF_DIR, merge=False)
    verdict: dict[str, Any] = {"comparisons": {}, "all_identical": True}
    for cell_id in PHASE_CELLS["faults"]:
        primary = json.loads((CELLS_DIR / f"{cell_id}.json").read_text(encoding="utf-8"))
        rerun = json.loads((RERUN_PROOF_DIR / f"{cell_id}.json").read_text(encoding="utf-8"))
        slice_primary = {k: primary.get(k) for k in DETERMINISTIC_FAULT_FIELDS}
        slice_rerun = {k: rerun.get(k) for k in DETERMINISTIC_FAULT_FIELDS}
        identical = slice_primary == slice_rerun
        verdict["comparisons"][cell_id] = {
            "identical": identical,
            "primary": slice_primary,
            "rerun": slice_rerun,
        }
        verdict["all_identical"] = verdict["all_identical"] and identical
        print(f"rerun proof {cell_id}: identical={identical}", flush=True)
    atomic_json_write(OUTPUT_DIR / "rerun_proof_verdict.json", verdict)
    if not verdict["all_identical"]:
        raise SystemExit("rerun proof FAILED: deterministic slice differs")
    print("rerun proof: all deterministic fault evidence identical", flush=True)


def run_smoke() -> None:
    """Prove the harness end-to-end with a five-file fake block, then clean."""
    from corpus import generate_corpus

    smoke_dir = OUTPUT_DIR / "gencorpus_smoke"
    generate_corpus(smoke_dir, file_count=5, seed=SEED, target_chars=TARGET_CHARS)
    store_dir = OUTPUT_DIR / "store_smoke"
    runtime = install_fake_runtime(store_dir)
    settings = build_fake_settings("documents", store_dir)
    first = _ingest(smoke_dir, settings)
    second = _ingest(smoke_dir, settings)
    if first.get("status") != "ok" or first.get("files_indexed") != 5:
        raise SystemExit(f"smoke FAILED: first ingest unexpected: {first.get('status')}")
    if first.get("chunks_created", 0) <= 0:
        raise SystemExit("smoke FAILED: no chunks created")
    if second.get("files_skipped_unchanged") != 5 or second.get("chunks_created") != 0:
        raise SystemExit("smoke FAILED: unchanged skip broken")
    _ = runtime["store"].count("documents")
    shutil.rmtree(store_dir, ignore_errors=True)
    shutil.rmtree(smoke_dir, ignore_errors=True)
    print(
        f"smoke OK: 5 files, {first['chunks_created']} chunks, "
        f"second pass skipped {second['files_skipped_unchanged']}",
        flush=True,
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=[*PHASE_CELLS, "ALL"])
    parser.add_argument("--single-cell", dest="single_cell")
    parser.add_argument("--out-dir", type=Path, default=CELLS_DIR)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun-proof", action="store_true")
    parser.add_argument("--remerge", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        run_smoke()
    elif args.remerge:
        remerge_all()
    elif args.rerun_proof:
        run_rerun_proof()
    elif args.single_cell:
        execute_single_cell(args.single_cell, args.out_dir)
    elif args.phase == "ALL":
        for phase in PHASE_CELLS:
            run_phase(phase, args.resume)
    elif args.phase:
        run_phase(args.phase, args.resume)
    else:
        parser.error("choose --phase, --single-cell, --rerun-proof, --remerge, or --smoke")


if __name__ == "__main__":
    main()
