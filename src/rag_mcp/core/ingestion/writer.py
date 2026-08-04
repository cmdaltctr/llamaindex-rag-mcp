"""Embedding, ChromaDB write, and deletion operations.

Handles embedding nodes via the configured embed model, writing to
ChromaDB, and all deletion operations (per-file, per-metadata-filter,
per-collection).  Includes the collection generation bumping for BM25
cache invalidation.  Extracted from the original ``ingestion.py``
monolith as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import chromadb
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from llama_index.core import Settings as LlamaIndexSettings

from ...config import settings as _cfg
from ._state import (
    bump_collection_generation,
    embed_semaphore,
    shutdown_requested,
    write_lock,
)
from .loader import get_chroma_collection

logger = logging.getLogger(__name__)


async def embed_and_write_async(
    nodes: list,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> int:
    """Async version of embed and write to ChromaDB.

    Wraps ChromaDB sync calls in ``asyncio.to_thread`` to yield the
    event loop during writes.

    Args:
        nodes: List of LlamaIndex Node objects.
        progress_callback: Optional callable for progress updates.
        collection_name: ChromaDB collection to write to.

    Returns:
        Number of chunks written.
    """
    if not nodes:
        return 0

    if shutdown_requested.is_set():
        return 0

    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    def _write_sync() -> int:
        with write_lock:
            if shutdown_requested.is_set():
                return 0

            collection = get_chroma_collection(collection_name)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store
            )

            with embed_semaphore:
                logger.info(
                    "Embedding %d chunks via %s...",
                    len(nodes),
                    LlamaIndexSettings.embed_model.model_name,
                )
                VectorStoreIndex(
                    nodes,
                    storage_context=storage_context,
                    show_progress=False,
                )
                bump_collection_generation(collection_name)
                logger.info(
                    "Successfully stored %d chunks in ChromaDB", len(nodes)
                )
            return len(nodes)

    chunks_written = await asyncio.to_thread(_write_sync)

    if progress_callback:
        progress_callback("embed", chunks_written, chunks_written)

    return chunks_written


# ── Deletion functions ─────────────────────────────────────────────────────


def _count_chunks(
    collection: chromadb.Collection,
    where: dict,
) -> int:
    """Count chunks matching a ChromaDB ``where`` filter.

    Args:
        collection: A ChromaDB collection object.
        where: A ChromaDB-compatible ``where`` clause.

    Returns:
        Number of matching chunks.
    """
    result = collection.get(where=where, include=[])
    return len(result.get("ids", []))


def preview_delete(
    *,
    path: str | None = None,
    metadata_filter: dict | None = None,
    collection_name: str = "documents",
) -> dict:
    """Preview a delete operation without modifying ChromaDB.

    Supports the three delete modes used by the CLI and MCP tool:
    deleting chunks for a source file path, deleting chunks matching a
    metadata filter, or dropping an entire collection. Missing collections
    intentionally preview as ``would_delete: 0`` to preserve existing dry-run
    behavior.

    Args:
        path: Source file path used as ``file_path`` metadata. Mutually
            exclusive with ``metadata_filter``.
        metadata_filter: ChromaDB-compatible ``where`` clause. Mutually
            exclusive with ``path``.
        collection_name: ChromaDB collection to preview against.

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

    if path is not None:
        mode = "path"
        where = {"file_path": str(path)}
    elif metadata_filter is not None:
        mode = "metadata"
        where = metadata_filter
    else:
        mode = "collection"
        where = None

    db = chromadb.PersistentClient(path=_cfg.chroma_persist_dir)
    try:
        collection = db.get_collection(collection_name)
        count = collection.count() if where is None else _count_chunks(
            collection, where,
        )
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
) -> dict:
    """Remove all chunks for a source file from the vector store.

    Idempotent — calling this on a file with no indexed chunks returns
    ``chunks_removed: 0``.

    Args:
        file_path: The source file path used as ``file_path`` metadata.
        collection_name: ChromaDB collection to delete from
            (default ``"documents"``).

    Returns:
        Dict with keys ``status``, ``chunks_removed``, and ``collection``.
        On error, includes ``message``.
    """
    db = chromadb.PersistentClient(path=_cfg.chroma_persist_dir)
    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    where = {"file_path": file_path}
    try:
        chunks_removed = _count_chunks(collection, where)
        if chunks_removed > 0:
            with write_lock:
                collection.delete(where=where)
                bump_collection_generation(collection_name)
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
) -> dict:
    """Remove all chunks matching an arbitrary metadata filter.

    Args:
        metadata_filter: A ChromaDB-compatible ``where`` clause.
        collection_name: ChromaDB collection to delete from
            (default ``"documents"``).

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

    db = chromadb.PersistentClient(path=_cfg.chroma_persist_dir)
    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    try:
        chunks_removed = _count_chunks(collection, metadata_filter)
        if chunks_removed > 0:
            with write_lock:
                collection.delete(where=metadata_filter)
                bump_collection_generation(collection_name)
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
) -> dict:
    """Permanently delete an entire ChromaDB collection.

    Args:
        collection_name: Name of the collection to drop.

    Returns:
        Dict with keys ``status`` and ``collection``.
        On error, includes ``message``.
    """
    db = chromadb.PersistentClient(path=_cfg.chroma_persist_dir)
    try:
        with write_lock:
            db.delete_collection(collection_name)
            bump_collection_generation(collection_name)
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
