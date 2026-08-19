"""Bounded, failure-safe replacement of one indexed source.

Stage 3A keeps the existing global mutation lock around embedding and all
store mutations, so this module instruments the serialized design without
widening effective ingestion concurrency.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import BaseNode, MetadataMode

from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ._state import get_embed_semaphore, shutdown_requested, write_lock
from .source_state import (
    SOURCE_CHUNK_COUNT_KEY,
    new_source_attempt,
    source_attempt_where,
    stale_attempts_where,
    stamp_source_attempt,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteTimings:
    """Measured stages inside the serialized embed/write section."""

    embedding_seconds: float = 0.0
    store_write_seconds: float = 0.0
    lock_wait_seconds: float = 0.0
    cleanup_seconds: float = 0.0

    def as_dict(self) -> dict[str, float]:
        """Return JSON-friendly timing diagnostics."""
        return {
            "embedding_seconds": self.embedding_seconds,
            "store_write_seconds": self.store_write_seconds,
            "lock_wait_seconds": self.lock_wait_seconds,
            "cleanup_seconds": self.cleanup_seconds,
        }


@dataclass(frozen=True)
class ReplaceSourceOutcome:
    """Result of one bounded source replacement."""

    chunks_written: int
    chunks_removed: int
    source_attempt: str
    timings: WriteTimings


class IngestionStageError(RuntimeError):
    """Failure attributed to one ingestion stage without hiding its cause."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _resolve_store(store: VectorStore | None) -> VectorStore:
    """Return the injected store or the process-wide default."""
    return store if store is not None else get_default_store()


def _embed_model_name() -> str:
    """Return a diagnostic model name without assuming one provider shape."""
    model = LlamaIndexSettings.embed_model
    return str(getattr(model, "model_name", type(model).__name__))


def _embed_missing_nodes(nodes: list[BaseNode]) -> None:
    """Populate missing embeddings using VectorStoreIndex's embedding text.

    Pre-embedding is required only to distinguish embedding wall time from
    store-write wall time. Concrete stores still receive normal LlamaIndex
    nodes; their ``VectorStoreIndex`` adapters reuse populated embeddings.
    """
    missing = [node for node in nodes if node.embedding is None]
    if not missing:
        return
    embed_model = LlamaIndexSettings.embed_model
    texts = [node.get_content(metadata_mode=MetadataMode.EMBED) for node in missing]
    embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)
    if len(embeddings) != len(missing):
        raise RuntimeError(
            "Embedding provider returned "
            f"{len(embeddings)} vectors for {len(missing)} nodes."
        )
    for node, embedding in zip(missing, embeddings, strict=True):
        node.embedding = embedding


async def replace_source_nodes_async(
    nodes: list[BaseNode],
    *,
    file_path: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
    store: VectorStore | None = None,
    embed_concurrency: int = 2,
) -> ReplaceSourceOutcome:
    """Embed, verify, and failure-safely replace one source version.

    Old rows are not deleted before the new attempt is durable. A unique
    attempt id makes old, new, and interrupted partial writes distinguishable.
    Once the exact attempt row count is verified, rows for the same source
    carrying a different (or legacy-missing) attempt id are stale.

    Args:
        nodes: Parsed/chunked nodes for exactly one source file.
        file_path: Canonical source path stored in metadata.
        content_hash: SHA-256 identity of source bytes.
        index_identity: Hash of all index-shaping configuration.
        source_version: Stable hash of content plus index identity.
        progress_callback: Optional ``(phase, current, total)`` callback.
        collection_name: Target vector-store collection.
        store: Optional injected vector store.
        embed_concurrency: Existing process semaphore width. The global
            write lock still serializes the complete embed/write section.

    Returns:
        Counts plus stage timing diagnostics for this bounded source.

    Raises:
        ConnectionError: When the embedding/store backend reports a
            connection failure.
        IngestionStageError: For attributed embedding, store-write,
            durability-verification, or stale-cleanup failures.
    """
    source_attempt = new_source_attempt()
    empty = ReplaceSourceOutcome(0, 0, source_attempt, WriteTimings())
    if not nodes or shutdown_requested.is_set():
        return empty
    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    resolved_store = _resolve_store(store)

    def _replace_sync() -> ReplaceSourceOutcome:
        lock_started = time.perf_counter()
        with write_lock:
            lock_wait = time.perf_counter() - lock_started
            if shutdown_requested.is_set():
                return ReplaceSourceOutcome(
                    0,
                    0,
                    source_attempt,
                    WriteTimings(lock_wait_seconds=lock_wait),
                )

            embedding_started = time.perf_counter()
            try:
                with get_embed_semaphore(embed_concurrency):
                    logger.info(
                        "Embedding %d chunks via %s...",
                        len(nodes),
                        _embed_model_name(),
                    )
                    _embed_missing_nodes(nodes)
            except ConnectionError:
                raise
            except Exception as exc:
                raise IngestionStageError(
                    "embedding",
                    f"Embedding failed for '{file_path}': {exc}",
                ) from exc
            embedding_seconds = time.perf_counter() - embedding_started

            if shutdown_requested.is_set():
                return ReplaceSourceOutcome(
                    0,
                    0,
                    source_attempt,
                    WriteTimings(
                        embedding_seconds=embedding_seconds,
                        lock_wait_seconds=lock_wait,
                    ),
                )

            stamp_source_attempt(
                nodes,
                file_path=file_path,
                content_hash=content_hash,
                index_identity=index_identity,
                source_version=source_version,
                source_attempt=source_attempt,
            )

            write_started = time.perf_counter()
            try:
                resolved_store.write_nodes(nodes, collection_name)
            except ConnectionError:
                raise
            except Exception as exc:
                raise IngestionStageError(
                    "store_write",
                    f"Store write failed for '{file_path}': {exc}",
                ) from exc
            store_write_seconds = time.perf_counter() - write_started

            verify_where = {
                "$and": [
                    *source_attempt_where(file_path, source_attempt)["$and"],
                    {SOURCE_CHUNK_COUNT_KEY: len(nodes)},
                ]
            }
            try:
                durable_count = resolved_store.count_where(
                    collection_name,
                    verify_where,
                )
            except Exception as exc:
                raise IngestionStageError(
                    "store_verify",
                    f"Durability verification failed for '{file_path}': {exc}",
                ) from exc
            if durable_count != len(nodes):
                raise IngestionStageError(
                    "store_verify",
                    f"Durability verification failed for '{file_path}': "
                    f"expected {len(nodes)} rows for attempt {source_attempt}, "
                    f"found {durable_count}.",
                )

            cleanup_started = time.perf_counter()
            stale_where = stale_attempts_where(file_path, source_attempt)
            try:
                stale_count = resolved_store.count_where(
                    collection_name,
                    stale_where,
                )
                if stale_count > 0:
                    resolved_store.delete_where(collection_name, stale_where)
            except Exception as exc:
                raise IngestionStageError(
                    "stale_cleanup",
                    f"Stale-version cleanup failed for '{file_path}': {exc}",
                ) from exc
            cleanup_seconds = time.perf_counter() - cleanup_started

            logger.info(
                "Stored %d verified chunk(s) for %s; removed %d stale chunk(s)",
                len(nodes),
                file_path,
                stale_count,
            )
            return ReplaceSourceOutcome(
                chunks_written=len(nodes),
                chunks_removed=stale_count,
                source_attempt=source_attempt,
                timings=WriteTimings(
                    embedding_seconds=embedding_seconds,
                    store_write_seconds=store_write_seconds,
                    lock_wait_seconds=lock_wait,
                    cleanup_seconds=cleanup_seconds,
                ),
            )

    outcome = await asyncio.to_thread(_replace_sync)
    if progress_callback:
        progress_callback("embed", outcome.chunks_written, outcome.chunks_written)
    return outcome
