"""Embedding, vector store write, and deletion operations.

Handles embedding nodes via the configured embed model, writing to the
vector store through the :class:`VectorStore` interface, and all
deletion operations (per-file, per-metadata-filter, per-collection).
Includes the collection generation bumping for BM25 cache
invalidation.  Extracted from the original ``ingestion.py`` monolith
as part of Phase 1; rewired through the vector store ABC in Phase 3.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from llama_index.core import Settings as LlamaIndexSettings

from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ._state import embed_semaphore, shutdown_requested, write_lock

logger = logging.getLogger(__name__)


def _resolve_store(store: VectorStore | None) -> VectorStore:
    """Return the given store or the process-wide default."""
    return store if store is not None else get_default_store()


async def embed_and_write_async(
    nodes: list,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
    store: VectorStore | None = None,
) -> int:
    """Async version of embed and write to the vector store.

    Wraps the store's sync write in ``asyncio.to_thread`` to yield the
    event loop during writes.

    Args:
        nodes: List of LlamaIndex Node objects.
        progress_callback: Optional callable for progress updates.
        collection_name: Vector store collection to write to.
        store: Optional injected :class:`VectorStore` (defaults to the
            process-wide store constructed by ``compose``).

    Returns:
        Number of chunks written.
    """
    if not nodes:
        return 0

    if shutdown_requested.is_set():
        return 0

    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    resolved_store = _resolve_store(store)

    def _write_sync() -> int:
        with write_lock:
            if shutdown_requested.is_set():
                return 0

            with embed_semaphore:
                logger.info(
                    "Embedding %d chunks via %s...",
                    len(nodes),
                    LlamaIndexSettings.embed_model.model_name,
                )
                resolved_store.write_nodes(nodes, collection_name)
                resolved_store.bump_generation(collection_name)
                logger.info(
                    "Successfully stored %d chunks in vector store", len(nodes)
                )
            return len(nodes)

    chunks_written = await asyncio.to_thread(_write_sync)

    if progress_callback:
        progress_callback("embed", chunks_written, chunks_written)

    return chunks_written


# ── Deletion functions ─────────────────────────────────────────────────────


def preview_delete(
    *,
    path: str | None = None,
    metadata_filter: dict | None = None,
    collection_name: str = "documents",
    store: VectorStore | None = None,
) -> dict:
    """Preview a delete operation without modifying the vector store.

    Supports the three delete modes used by the CLI and MCP tool:
    deleting chunks for a source file path, deleting chunks matching a
    metadata filter, or dropping an entire collection. Missing collections
    intentionally preview as ``would_delete: 0`` to preserve existing dry-run
    behavior.

    Args:
        path: Source file path used as ``file_path`` metadata. Mutually
            exclusive with ``metadata_filter``.
        metadata_filter: Store-compatible ``where`` clause. Mutually
            exclusive with ``path``.
        collection_name: Collection to preview against.
        store: Optional injected :class:`VectorStore`.

    Returns:
        Dict with keys ``status``, ``dry_run``, ``mode``, ``collection``, and
        ``would_delete``. On invalid input, returns ``status: error``.
    """
    if path is not None and metadata_filter is not None:
        return {
            "status": "error",
            "message": "path and metadata_filter are mutually exclusive.",
            "dry_run": True,
            "collection": collection_name,
            "would_delete": 0,
        }

    resolved_store = _resolve_store(store)

    if path is not None:
        mode = "path"
        where = {"file_path": str(path)}
    elif metadata_filter is not None:
        mode = "metadata"
        where = metadata_filter
    else:
        mode = "collection"
        where = None

    try:
        if where is None:
            count = resolved_store.count(collection_name)
        else:
            count = resolved_store.count_where(collection_name, where)
    except Exception:
        count = 0

    return {
        "status": "ok",
        "dry_run": True,
        "mode": mode,
        "collection": collection_name,
        "would_delete": count,
    }


def remove_document(
    file_path: str,
    collection_name: str = "documents",
    store: VectorStore | None = None,
) -> dict:
    """Remove all chunks for a source file from the vector store.

    Idempotent — calling this on a file with no indexed chunks returns
    ``chunks_removed: 0``.

    Args:
        file_path: The source file path used as ``file_path`` metadata.
        collection_name: Collection to delete from
            (default ``"documents"``).
        store: Optional injected :class:`VectorStore`.

    Returns:
        Dict with keys ``status``, ``chunks_removed``, and ``collection``.
        On error, includes ``message``.
    """
    resolved_store = _resolve_store(store)
    if not resolved_store.collection_exists(collection_name):
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    where = {"file_path": file_path}
    try:
        chunks_removed = resolved_store.count_where(collection_name, where)
        if chunks_removed > 0:
            with write_lock:
                resolved_store.delete_where(collection_name, where)
                resolved_store.bump_generation(collection_name)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete chunks for '{file_path}': {exc}",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    logger.info(
        "Removed %d chunk(s) for %s from '%s'",
        chunks_removed,
        file_path,
        collection_name,
    )
    return {
        "status": "ok",
        "chunks_removed": chunks_removed,
        "collection": collection_name,
    }


def remove_by_metadata(
    metadata_filter: dict,
    collection_name: str = "documents",
    store: VectorStore | None = None,
) -> dict:
    """Remove all chunks matching an arbitrary metadata filter.

    Args:
        metadata_filter: A store-compatible ``where`` clause.
        collection_name: Collection to delete from
            (default ``"documents"``).
        store: Optional injected :class:`VectorStore`.

    Returns:
        Dict with keys ``status``, ``chunks_removed``, and ``collection``.
        On error, includes ``message``.
    """
    if not metadata_filter:
        return {
            "status": "error",
            "message": "Empty metadata filter is not allowed.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    resolved_store = _resolve_store(store)
    if not resolved_store.collection_exists(collection_name):
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    try:
        chunks_removed = resolved_store.count_where(
            collection_name, metadata_filter
        )
        if chunks_removed > 0:
            with write_lock:
                resolved_store.delete_where(collection_name, metadata_filter)
                resolved_store.bump_generation(collection_name)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete chunks matching filter: {exc}",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    logger.info(
        "Removed %d chunk(s) matching filter from '%s'",
        chunks_removed,
        collection_name,
    )
    return {
        "status": "ok",
        "chunks_removed": chunks_removed,
        "collection": collection_name,
    }


def remove_collection(
    collection_name: str,
    store: VectorStore | None = None,
) -> dict:
    """Permanently delete an entire collection.

    Args:
        collection_name: Name of the collection to drop.
        store: Optional injected :class:`VectorStore`.

    Returns:
        Dict with keys ``status`` and ``collection``.
        On error, includes ``message``.
    """
    resolved_store = _resolve_store(store)
    try:
        with write_lock:
            resolved_store.delete_collection(collection_name)
            resolved_store.bump_generation(collection_name)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete collection '{collection_name}': {exc}",
            "collection": collection_name,
        }

    logger.info("Dropped collection '%s'", collection_name)
    return {
        "status": "ok",
        "collection": collection_name,
    }
