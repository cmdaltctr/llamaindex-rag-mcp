"""Ingestion pipeline orchestrator.

Stage 3A processes one source file at a time, skips only complete matching
source/index versions, and preserves the last durable searchable version until
a replacement attempt has been written and verified.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..settings import resolve_effective_settings
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ._state import shutdown_requested
from .backends.orchestrator import resolve_declared_text_format
from .chunker import read_and_chunk_file_async
from .hashing import sha256_file
from .loader import gather_supported_files, make_file_detail
from .metrics import sample_peak_rss_bytes
from .replacement import IngestionStageError, replace_source_nodes_async
from .source_state import (
    IncompatibleSourceLineageError,
    assert_source_lineage_compatible,
    build_index_identity,
    build_source_id,
    build_source_version,
    canonical_source_path,
    is_complete_current_version,
)

logger = logging.getLogger(__name__)

_TIMING_KEYS = (
    "change_detection_seconds",
    "parse_chunk_seconds",
    "embedding_seconds",
    "store_write_seconds",
    "lock_wait_seconds",
    "cleanup_seconds",
)


def _new_timings() -> dict[str, float]:
    """Return a zeroed timing accumulator for one bounded source."""
    return {key: 0.0 for key in _TIMING_KEYS}


def _accumulate_timings(total: dict[str, float], unit: dict[str, float]) -> None:
    """Add one source's stage timings into the operation aggregate."""
    for key in _TIMING_KEYS:
        total[key] += unit.get(key, 0.0)


def _error_type(exc: Exception) -> str:
    """Map one per-source exception to the established public error classes."""
    if isinstance(exc, ConnectionError):
        return "connection"
    if isinstance(exc, IncompatibleSourceLineageError):
        return "store"
    if isinstance(exc, IngestionStageError):
        if exc.stage == "embedding":
            return "embedding"
        if exc.stage == "parse_chunk":
            return "file"
        return "store"
    return "file"


def _overall_error_type(types: list[str]) -> str:
    """Choose the most actionable error type when every source failed."""
    for candidate in ("connection", "embedding", "store", "file"):
        if candidate in types:
            return candidate
    return "file"


async def ingest_path_async(
    path: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
    effective_settings: Any = None,
    store: VectorStore | None = None,
    embed_model: Any = None,
) -> dict:
    """Index a file or directory using bounded, failure-safe source units.

    The event loop yields during hashing, parsing/chunking, embedding, and
    vector-store work. At most one source file's node set is retained by this
    orchestrator at a time.

    Args:
        path: Absolute or relative path to a file or directory.
        chunk_size: Optional chunk-size override for this ingestion.
        chunk_overlap: Optional chunk-overlap override.
        progress_callback: Optional callable ``(phase, current, total)``.
        collection_name: Target vector-store collection.
        effective_settings: Optional resolved :class:`EffectiveSettings`.

    Returns:
        Backward-compatible ingestion result with additive change-detection
        and timing diagnostics.
    """
    shutdown_requested.clear()
    operation_started = time.perf_counter()

    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        return {
            "status": "error",
            "error_type": "file",
            "message": f"Path not found: {path}",
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
            "metadata_degraded": 0,
        }

    # Resolve settings BEFORE the extension gate: the ingestible set is
    # profile-scoped (design D4), so a codebase-profile ingest admits
    # source extensions a documents-profile ingest rejects.
    resolved_settings = resolve_effective_settings(effective_settings)
    resolved_extensions = set(resolved_settings.ingestion.ingest_extensions)

    if path_obj.is_file() and path_obj.suffix.lower() not in resolved_extensions:
        return {
            "status": "error",
            "error_type": "file",
            "message": (
                f"Unsupported file extension: {path_obj.suffix}. "
                f"Supported: {', '.join(sorted(resolved_extensions))}"
            ),
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
            "metadata_degraded": 0,
        }

    effective_chunk_size = (
        chunk_size if chunk_size is not None else resolved_settings.chunking.chunk_size
    )
    effective_chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else resolved_settings.chunking.chunk_overlap
    )

    files_to_index, skipped_details = gather_supported_files(
        path_obj, extensions=resolved_extensions
    )
    if not files_to_index:
        return {
            "status": "ok",
            "files_indexed": 0,
            "files_skipped_unchanged": 0,
            "chunks_created": 0,
            "chunks_removed": 0,
            "file_details": skipped_details,
            "collection": collection_name,
            "metadata_degraded": 0,
            "timings": {
                **_new_timings(),
                "total_seconds": time.perf_counter() - operation_started,
            },
            "peak_rss_bytes": sample_peak_rss_bytes(),
        }

    # Type-aware ingestion: detect file types via Magika. Failure degrades to
    # extension-based routing exactly as before.
    from ..codebase.codebase_map import detect_file_types

    content_type_map: dict[str, str] = {}
    try:
        inventory = detect_file_types(str(path_obj))
        for entry in inventory.entries:
            content_type_map[entry.path] = f"{entry.group}/{entry.label}"
    except Exception as exc:
        logger.warning(
            "Magika detection failed, using extension-based routing: %s",
            exc,
        )

    resolved_store = store if store is not None else get_default_store()
    files_indexed = 0
    files_skipped_unchanged = 0
    chunks_created_total = 0
    chunks_removed_total = 0
    metadata_degraded_count = 0
    errors: list[str] = []
    failure_types: list[str] = []
    file_details: list[dict] = []
    aggregate_timings = _new_timings()

    for index, file_path in enumerate(files_to_index):
        if shutdown_requested.is_set():
            break

        try:
            rel_path = str(file_path.relative_to(path_obj))
        except ValueError:
            rel_path = str(file_path)
        content_type = content_type_map.get(rel_path)

        if content_type and content_type.startswith("binary"):
            file_details.append(
                make_file_detail(
                    file_name=file_path.name,
                    status="skipped",
                    chunks=0,
                )
            )
            logger.info("SKIP %s - binary file skipped", file_path.name)
            if progress_callback:
                progress_callback("read", index + 1, len(files_to_index))
            continue

        unit_started = time.perf_counter()
        unit_timings = _new_timings()
        nodes = None
        source_version = None

        try:
            detection_started = time.perf_counter()
            canonical_file_path = canonical_source_path(file_path)
            source_id = build_source_id(canonical_file_path)
            content_hash = await asyncio.to_thread(sha256_file, file_path)
            # Resolve the declared parser text format BEFORE the unchanged
            # check (design D3): the declaration decides Markdown routing,
            # so it belongs in the identity. The later BackendRead carries
            # the same resolution and verifies agreement inside the read.
            parser_text_format = resolve_declared_text_format(file_path, settings=resolved_settings)
            index_identity = build_index_identity(
                resolved_settings,
                content_type=content_type,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                text_format=parser_text_format,
                embed_model=embed_model,
            )
            source_version = build_source_version(content_hash, index_identity)
            # Reject pre-lineage rows for this path before any parse,
            # embedding, or store mutation so schemas never mix silently.
            await asyncio.to_thread(
                assert_source_lineage_compatible,
                resolved_store,
                collection_name,
                file_path=canonical_file_path,
                source_id=source_id,
            )
            unchanged, existing_chunks = await asyncio.to_thread(
                is_complete_current_version,
                resolved_store,
                collection_name,
                source_id=source_id,
                content_hash=content_hash,
                index_identity=index_identity,
                source_version=source_version,
            )
            unit_timings["change_detection_seconds"] = time.perf_counter() - detection_started

            if unchanged:
                files_skipped_unchanged += 1
                detail = make_file_detail(
                    file_name=file_path.name,
                    status="skipped_unchanged",
                    chunks=0,
                )
                detail["existing_chunks"] = existing_chunks
                detail["source_version"] = source_version
                unit_timings["total_seconds"] = time.perf_counter() - unit_started
                detail["timings"] = unit_timings
                detail["peak_rss_bytes"] = sample_peak_rss_bytes()
                file_details.append(detail)
                logger.info("SKIP %s - unchanged source/index version", file_path.name)
                continue

            parse_started = time.perf_counter()
            nodes = await read_and_chunk_file_async(
                file_path,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                content_type=content_type,
                fallback_strategy=resolved_settings.chunking.strategy_fallback,
                taxonomy_mode=resolved_settings.metadata.taxonomy_mode,
                settings=resolved_settings,
            )
            unit_timings["parse_chunk_seconds"] = time.perf_counter() - parse_started
            if not nodes:
                raise IngestionStageError(
                    "parse_chunk",
                    f"No chunks were produced for '{file_path}'.",
                )

            file_metadata_degraded = getattr(nodes, "metadata_degraded", False)
            # Count degradation on observation, not on replacement success:
            # an embedding/store failure after degraded extraction must not
            # hide that degradation from the caller.
            if file_metadata_degraded:
                metadata_degraded_count += 1
            outcome = await replace_source_nodes_async(
                nodes,
                file_path=canonical_file_path,
                source_id=source_id,
                content_hash=content_hash,
                index_identity=index_identity,
                source_version=source_version,
                progress_callback=progress_callback,
                collection_name=collection_name,
                store=resolved_store,
                embed_model=embed_model,
                embed_concurrency=resolved_settings.ingestion.embed_concurrency,
                norm_guard_enabled=resolved_settings.embedding.norm_guard_enabled,
                norm_tolerance=resolved_settings.embedding.norm_tolerance,
            )
            unit_timings.update(outcome.timings.as_dict())
            chunks_created_total += outcome.chunks_written
            chunks_removed_total += outcome.chunks_removed
            files_indexed += 1

            detail = make_file_detail(
                file_name=file_path.name,
                status="indexed",
                chunks=outcome.chunks_written,
                metadata_degraded=file_metadata_degraded,
            )
            detail["source_version"] = source_version
            # Effective chunking strategy, when the result carries one
            # (CodeChunkResult): makes the AST-aware code path observable
            # per file (spec type-aware-ingestion: "files with a
            # tree-sitter mapping SHALL be chunked by the AST-aware code
            # strategy") instead of only through stored metadata.
            effective_strategy = getattr(nodes, "chunk_strategy_effective", None)
            if effective_strategy is not None:
                detail["effective_strategy"] = effective_strategy
            if outcome.norm_band is not None:
                # Observed embedding-vector norm band for this source —
                # the guard's evidence trail in the ingest report (spec:
                # "records the observed norm band"). Absent when the guard
                # is disabled: report what ran, not what did not.
                detail["embedding_norm_band"] = {
                    "min": outcome.norm_band[0],
                    "max": outcome.norm_band[1],
                }
            unit_timings["total_seconds"] = time.perf_counter() - unit_started
            detail["timings"] = unit_timings
            detail["peak_rss_bytes"] = sample_peak_rss_bytes()
            file_details.append(detail)
            logger.info(
                "OK %s - %d verified chunk(s)",
                file_path.name,
                outcome.chunks_written,
            )
        except Exception as exc:
            failure_type = _error_type(exc)
            failure_types.append(failure_type)
            errors.append(f"{file_path.name}: {exc}")
            unit_timings["total_seconds"] = time.perf_counter() - unit_started
            detail = make_file_detail(
                file_name=file_path.name,
                status="failed",
                chunks=0,
                error=str(exc),
            )
            if source_version is not None:
                detail["source_version"] = source_version
            detail["failure_stage"] = (
                exc.stage if isinstance(exc, IngestionStageError) else failure_type
            )
            if nodes is not None and getattr(nodes, "metadata_degraded", False):
                detail["metadata_degraded"] = True
            detail["timings"] = unit_timings
            detail["peak_rss_bytes"] = sample_peak_rss_bytes()
            file_details.append(detail)
            logger.warning("FAIL %s - %s", file_path.name, exc)
        finally:
            # Explicitly drop the bounded node set before the next source's
            # parser starts. This matters because Python evaluates the RHS of
            # the next assignment before replacing the previous local value.
            if nodes is not None:
                del nodes
            _accumulate_timings(aggregate_timings, unit_timings)
            if progress_callback:
                progress_callback("read", index + 1, len(files_to_index))

    all_details = file_details + skipped_details
    aggregate_timings["total_seconds"] = time.perf_counter() - operation_started
    common = {
        "files_indexed": files_indexed,
        "files_skipped_unchanged": files_skipped_unchanged,
        "chunks_created": chunks_created_total,
        "chunks_removed": chunks_removed_total,
        "collection": collection_name,
        "file_details": all_details,
        "metadata_degraded": metadata_degraded_count,
        "timings": aggregate_timings,
        "peak_rss_bytes": sample_peak_rss_bytes(),
    }

    if files_indexed > 0 or files_skipped_unchanged > 0:
        result: dict = {"status": "ok", **common}
    else:
        result = {
            "status": "error",
            "error_type": _overall_error_type(failure_types),
            "message": (
                f"All {len(files_to_index)} file(s) failed to index. "
                "See file_details for per-file errors."
            ),
            **common,
        }
    if errors:
        result["warnings"] = errors
    return result
