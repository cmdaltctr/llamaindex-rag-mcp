"""Ingestion pipeline orchestrator.

The main ``ingest_path_async`` entry point that ties together file
gathering, content-type detection, chunking, metadata extraction, and
ChromaDB writing.  Extracted from the original ``ingestion.py`` monolith
as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from .loader import SUPPORTED_EXTENSIONS
from ..settings import resolve_effective_settings
from ._state import shutdown_requested
from .chunker import read_and_chunk_file_async
from .loader import gather_supported_files, make_file_detail
from .writer import embed_and_write_async, remove_document

logger = logging.getLogger(__name__)


async def ingest_path_async(
    path: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
    effective_settings: Any = None,
) -> dict:
    """Async ingestion entry point — indexes files into ChromaDB.

    Yields the event loop during file I/O, metadata extraction, and
    ChromaDB writes so the MCP server remains responsive.

    Args:
        path: Absolute or relative path to a file or directory.
        chunk_size: Override CHUNK_SIZE for this ingestion.
        chunk_overlap: Override CHUNK_OVERLAP for this ingestion.
        progress_callback: Optional callable ``(phase, current, total)``.
        collection_name: Name of the ChromaDB collection to write to.
        effective_settings: Optional :class:`EffectiveSettings` resolved
            by :class:`ProfileResolver` for this collection (Phase 4).
            When provided, its ``chunk_strategy_fallback`` and
            ``metadata_taxonomy_mode`` supply the defaults for ambiguous
            file types and metadata classification.

    Returns:
        Same dict shape as the former sync ``ingest_path()``.
    """
    shutdown_requested.clear()

    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        return {
            "status": "error",
            "error_type": "file",
            "message": f"Path not found: {path}",
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
        }

    if path_obj.is_file() and path_obj.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "error_type": "file",
            "message": (
                f"Unsupported file extension: {path_obj.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
        }

    # Resolve settings ONCE at the entry-point boundary; everything below
    # receives the resolved instance.
    resolved_settings = resolve_effective_settings(effective_settings)
    _chunk_size = (
        chunk_size if chunk_size is not None else resolved_settings.chunking.chunk_size
    )
    _chunk_overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else resolved_settings.chunking.chunk_overlap
    )

    files_to_index, skipped_details = gather_supported_files(path_obj)
    if not files_to_index:
        return {
            "status": "ok",
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_removed": 0,
            "file_details": skipped_details,
            "collection": collection_name,
        }

    # Type-aware ingestion: detect file types via Magika (task 6.3).
    # Falls back to None (extension-based routing) when Magika unavailable.
    from ..codebase.codebase_map import detect_file_types

    content_type_map: dict[str, str] = {}
    try:
        inventory = detect_file_types(str(path_obj))
        for entry in inventory.entries:
            ct = f"{entry.group}/{entry.label}"
            content_type_map[entry.path] = ct
    except Exception as exc:
        logger.warning("Magika detection failed, using extension-based routing: %s", exc)

    # Delete old chunks for upsert semantics (via to_thread).
    chunks_removed_total = 0
    for _f in files_to_index:
        if shutdown_requested.is_set():
            break
        _del_result = await asyncio.to_thread(
            remove_document, str(_f), collection_name
        )
        if _del_result.get("status") == "ok":
            chunks_removed_total += _del_result.get("chunks_removed", 0)

    # Process files sequentially (one at a time per design).
    all_nodes: list = []
    files_indexed = 0
    errors: list[str] = []
    file_details: list[dict] = []

    for i, file_path in enumerate(files_to_index):
        if shutdown_requested.is_set():
            break

        # Determine content_type for this file (task 6.3, 6.7).
        try:
            rel_path = str(file_path.relative_to(path_obj))
        except ValueError:
            rel_path = str(file_path)
        content_type = content_type_map.get(rel_path)

        # Skip binary files (task 6.5).
        if content_type and content_type.startswith("binary"):
            file_details.append(make_file_detail(
                file_name=file_path.name,
                status="skipped",
                chunks=0,
            ))
            logger.info("⊘ %s — binary file skipped", file_path.name)
            if progress_callback:
                progress_callback("read", i + 1, len(files_to_index))
            continue

        try:
            # Phase 4: pass the profile's chunking fallback for ambiguous
            # types and the taxonomy mode for metadata classification.
            # Content-type dispatch still wins for known types.
            nodes = await read_and_chunk_file_async(
                file_path,
                chunk_size=_chunk_size,
                chunk_overlap=_chunk_overlap,
                content_type=content_type,
                fallback_strategy=resolved_settings.chunking.strategy_fallback,
                taxonomy_mode=resolved_settings.metadata.taxonomy_mode,
                settings=resolved_settings,
            )
            all_nodes.extend(nodes)
            files_indexed += 1
            file_details.append(make_file_detail(
                file_name=file_path.name,
                status="indexed",
                chunks=len(nodes),
            ))
            logger.info("✓ %s — %d chunk(s)", file_path.name, len(nodes))
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
            file_details.append(make_file_detail(
                file_name=file_path.name,
                status="failed",
                chunks=0,
                error=str(exc),
            ))
            logger.warning("✗ %s — %s", file_path.name, exc)

        if progress_callback:
            progress_callback("read", i + 1, len(files_to_index))

    # Embed and write to ChromaDB (async, yields the loop).
    try:
        chunks_created = await embed_and_write_async(
            all_nodes, progress_callback, collection_name=collection_name,
            embed_concurrency=resolved_settings.ingestion.embed_concurrency,
        )
    except ConnectionError as exc:
        return {
            "status": "error",
            "error_type": "connection",
            "message": str(exc),
            "file_details": file_details + skipped_details,
            "collection": collection_name,
            "chunks_removed": chunks_removed_total,
        }
    except RuntimeError as exc:
        return {
            "status": "error",
            "error_type": "embedding",
            "message": str(exc),
            "file_details": file_details + skipped_details,
            "collection": collection_name,
            "chunks_removed": chunks_removed_total,
        }

    all_details = file_details + skipped_details

    if files_indexed > 0:
        result: dict = {
            "status": "ok",
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "chunks_removed": chunks_removed_total,
            "collection": collection_name,
            "file_details": all_details,
        }
    else:
        result = {
            "status": "error",
            "error_type": "file",
            "message": (
                f"All {len(files_to_index)} file(s) failed to index. "
                "See file_details for per-file errors."
            ),
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_removed": chunks_removed_total,
            "collection": collection_name,
            "file_details": all_details,
        }
    if errors:
        result["warnings"] = errors

    return result
