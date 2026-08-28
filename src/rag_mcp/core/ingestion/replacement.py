"""Bounded, failure-safe replacement of one indexed source.

Stage 3B (Experiment 18 evidence) narrows the global write lock to the
mutation section only: lineage/attempt stamping and embedding run before the
lock is acquired, while the store write, durability verification, and stale
cleanup stay inside it. Concurrent ingestion operations can therefore embed in
parallel while store mutations remain serialised. The failure-safety
ordering from ADR-048 is unchanged — a failure before or during the locked
section still leaves the previous searchable version intact.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import BaseNode, MetadataMode

from ..norm_guard import check_ingest_vectors
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ._state import get_embed_semaphore, shutdown_requested, write_lock
from .source_state import (
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_COUNT_KEY,
    SOURCE_ID_KEY,
    new_source_attempt,
    source_attempt_where,
    stamp_source_lineage,
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
    # Observed (min, max) embedding-vector L2 norms for this source, or
    # ``None`` when the embedding norm guard is disabled (design: report
    # what ran, not what did not).
    norm_band: tuple[float, float] | None = None


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
            f"Embedding provider returned {len(embeddings)} vectors for {len(missing)} nodes."
        )
    for node, embedding in zip(missing, embeddings, strict=True):
        node.embedding = embedding


def _stale_source_ids(
    store: VectorStore,
    collection_name: str,
    *,
    source_id: str,
    source_attempt: str,
) -> list[str]:
    """Return stale row IDs for one source using a bounded store-neutral scan.

    Selection is scoped to the source's stable ``source_id`` so rows for a
    different source — including byte-identical files at other paths — are
    never removed. Selection happens in Python rather than a backend
    ``$ne`` filter because stores differ in whether a missing metadata key
    satisfies inequality. Production ingestion rejects pre-lineage rows
    before mutation, so rows without ``source_id`` cannot reach this scan
    through the normal path.
    """
    return [
        row_id
        for row_id, _, metadata in store.iter_documents(collection_name)
        if metadata.get(SOURCE_ID_KEY) == source_id
        and metadata.get(SOURCE_ATTEMPT_KEY) != source_attempt
    ]


async def replace_source_nodes_async(
    nodes: list[BaseNode],
    *,
    file_path: str,
    source_id: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
    store: VectorStore | None = None,
    embed_concurrency: int = 2,
    norm_guard_enabled: bool = True,
    norm_tolerance: float = 0.001,
) -> ReplaceSourceOutcome:
    """Embed, verify, and failure-safely replace one source version.

    Old rows are not deleted before the new attempt is durable. A unique
    attempt id makes old, new, and interrupted partial writes
    distinguishable while stable ``chunk_id`` values reproduce across
    attempts. Once the exact attempt row count is verified, a bounded
    store-neutral scan selects stale IDs for the same ``source_id`` and
    deletes only those IDs.

    Args:
        nodes: Parsed/chunked nodes for exactly one source file.
        file_path: Canonical source path stored as human-readable metadata.
        source_id: Stable logical identity derived from the canonical path.
        content_hash: SHA-256 identity of source bytes.
        index_identity: Hash of all index-shaping configuration.
        source_version: Stable hash of content plus index identity.
        progress_callback: Optional ``(phase, current, total)`` callback.
        collection_name: Target vector-store collection.
        store: Optional injected vector store.
        embed_concurrency: Process semaphore width limiting concurrent
            embedding. Since Stage 3B the semaphore (not the write lock)
            is the only serialiser of the embed phase; the write lock
            covers the store mutation section only.
        norm_guard_enabled: Embedding norm-guard switch from the injected
            ``EffectiveSettings`` embedding block. When true, every
            storage-bound vector is verified unit-normalised within
            ``norm_tolerance`` before any write (fail-closed; design D2 of
            the guard-embedding-normalisation change).
        norm_tolerance: Maximum permitted ``|norm - 1.0|`` (inclusive).

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

    def _prepare_sync() -> tuple[float, tuple[float, float] | None]:
        """Stamp lineage and embed the bounded node set outside the lock.

        Embedding dominates replacement wall time (Experiment 18), and the
        node list is caller-private until the store write, so this phase
        needs no mutual exclusion. Lineage is stamped before embedding so
        every machine identity key is already excluded from embedding
        text; ``stamp_source_lineage`` derives the stable chunk IDs and
        the attempt-scoped row IDs in one coherent operation.

        The norm guard runs after the embed step and before the write:
        a violating vector aborts here, inside the attributed embedding
        stage, so ``write_nodes`` never sees it and the failure-safe
        ordering keeps the previous version searchable.
        """
        embedding_started = time.perf_counter()
        stamp_source_lineage(
            nodes,
            file_path=file_path,
            source_id=source_id,
            content_hash=content_hash,
            index_identity=index_identity,
            source_version=source_version,
            source_attempt=source_attempt,
        )
        try:
            with get_embed_semaphore(embed_concurrency):
                logger.info(
                    "Embedding %d chunks via %s...",
                    len(nodes),
                    _embed_model_name(),
                )
                _embed_missing_nodes(nodes)
            norm_band = check_ingest_vectors(
                [node.embedding for node in nodes if node.embedding is not None],
                model_name=_embed_model_name(),
                enabled=norm_guard_enabled,
                tolerance=norm_tolerance,
            )
        except ConnectionError:
            raise
        except Exception as exc:
            raise IngestionStageError(
                "embedding",
                f"Embedding failed for '{file_path}': {exc}",
            ) from exc
        return time.perf_counter() - embedding_started, norm_band

    def _commit_sync(
        embedding_seconds: float,
        norm_band: tuple[float, float] | None,
    ) -> ReplaceSourceOutcome:
        """Write, verify, and clean stale rows inside the mutation lock."""
        lock_started = time.perf_counter()
        with write_lock:
            lock_wait = time.perf_counter() - lock_started
            if shutdown_requested.is_set():
                return ReplaceSourceOutcome(
                    0,
                    0,
                    source_attempt,
                    WriteTimings(
                        embedding_seconds=embedding_seconds,
                        lock_wait_seconds=lock_wait,
                    ),
                    norm_band=norm_band,
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
                    *source_attempt_where(source_id, source_attempt)["$and"],
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
            try:
                stale_ids = _stale_source_ids(
                    resolved_store,
                    collection_name,
                    source_id=source_id,
                    source_attempt=source_attempt,
                )
                if stale_ids:
                    resolved_store.delete_ids(collection_name, stale_ids)
            except Exception as exc:
                raise IngestionStageError(
                    "stale_cleanup",
                    f"Stale-version cleanup failed for '{file_path}': {exc}",
                ) from exc
            stale_count = len(stale_ids)
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
                norm_band=norm_band,
            )

    embedding_seconds, norm_band = await asyncio.to_thread(_prepare_sync)
    if shutdown_requested.is_set():
        return ReplaceSourceOutcome(
            0,
            0,
            source_attempt,
            WriteTimings(embedding_seconds=embedding_seconds),
            norm_band=norm_band,
        )
    outcome = await asyncio.to_thread(_commit_sync, embedding_seconds, norm_band)
    if progress_callback:
        progress_callback("embed", outcome.chunks_written, outcome.chunks_written)
    return outcome
