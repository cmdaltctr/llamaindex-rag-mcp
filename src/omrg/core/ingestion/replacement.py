"""Bounded, failure-safe replacement of one indexed source.

Two callable seams make up one replacement: :func:`prepare_source_embeddings`
(lineage stamping, embedding, norm guard; no lock) and
``commit.commit_prepared_source`` (write, verification, stale cleanup; write
lock held). :func:`replace_source_nodes_async` composes them for the
standard ingestion path, and a graph runner calls the same two seams.

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
from typing import Any

from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import BaseNode, MetadataMode

from ..norm_guard import check_ingest_vectors
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ._state import get_embed_semaphore, shutdown_requested
from .commit import (
    STALE_DELETE_ID_BATCH_LIMIT,
    IngestionStageError,
    PreparedSource,
    ReplaceSourceOutcome,
    WriteTimings,
    commit_prepared_source,
)
from .source_state import new_source_attempt, stamp_source_lineage

__all__ = [
    "STALE_DELETE_ID_BATCH_LIMIT",
    "IngestionStageError",
    "PreparedSource",
    "ReplaceSourceOutcome",
    "WriteTimings",
    "commit_prepared_source",
    "prepare_source_embeddings",
    "replace_source_nodes_async",
]

logger = logging.getLogger(__name__)


def _resolve_store(store: VectorStore | None) -> VectorStore:
    """Return the injected store or the process-wide default."""
    return store if store is not None else get_default_store()


def _embed_model_name(embed_model: Any = None) -> str:
    """Return a diagnostic model name without assuming one provider shape."""
    model = embed_model if embed_model is not None else LlamaIndexSettings.embed_model
    return str(getattr(model, "model_name", type(model).__name__))


def _embed_missing_nodes(nodes: list[BaseNode], embed_model: Any = None) -> None:
    """Populate missing embeddings using VectorStoreIndex's embedding text.

    Pre-embedding is required only to distinguish embedding wall time from
    store-write wall time. Concrete stores still receive normal LlamaIndex
    nodes; their ``VectorStoreIndex`` adapters reuse populated embeddings.
    """
    missing = [node for node in nodes if node.embedding is None]
    if not missing:
        return
    if embed_model is None:
        embed_model = LlamaIndexSettings.embed_model
    texts = [node.get_content(metadata_mode=MetadataMode.EMBED) for node in missing]
    embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)
    if len(embeddings) != len(missing):
        raise RuntimeError(
            f"Embedding provider returned {len(embeddings)} vectors for {len(missing)} nodes."
        )
    for node, embedding in zip(missing, embeddings, strict=True):
        node.embedding = embedding


def prepare_source_embeddings(
    nodes: list[BaseNode],
    *,
    file_path: str,
    source_id: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
    source_attempt: str,
    embed_model: Any = None,
    embed_concurrency: int = 2,
    norm_guard_enabled: bool = True,
    norm_tolerance: float = 0.001,
) -> PreparedSource:
    """Stamp lineage and embed one bounded node set outside the write lock.

    Embedding dominates replacement wall time (Experiment 18), and the node
    list is caller-private until the store write, so this phase needs no
    mutual exclusion. Lineage is stamped before embedding so every machine
    identity key is already excluded from embedding text;
    ``stamp_source_lineage`` derives the stable chunk IDs and the
    attempt-scoped row IDs in one coherent operation.

    The norm guard runs after the embed step and before the write: a
    violating vector aborts here, inside the attributed embedding stage, so
    ``write_nodes`` never sees it and the previous version stays searchable.
    This function is blocking; async callers run it in a worker thread.

    Args:
        nodes: Parsed/chunked nodes for exactly one source file.
        file_path: Canonical source path stored as human-readable metadata.
        source_id: Stable logical identity derived from the canonical path.
        content_hash: SHA-256 identity of source bytes.
        index_identity: Hash of all index-shaping configuration.
        source_version: Stable hash of content plus index identity.
        source_attempt: Unique identifier of this replacement attempt.
        embed_model: Optional injected embedding model.
        embed_concurrency: Process semaphore width limiting concurrent
            embedding. The semaphore (not the write lock) is the only
            serialiser of the embed phase.
        norm_guard_enabled: Embedding norm-guard switch from the injected
            ``EffectiveSettings`` embedding block.
        norm_tolerance: Maximum permitted ``|norm - 1.0|`` (inclusive).

    Returns:
        The prepared attempt record for :func:`commit_prepared_source`.

    Raises:
        ConnectionError: When the embedding backend reports a connection
            failure.
        IngestionStageError: ``embedding`` stage for provider, count, or
            norm-guard failures.
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
                _embed_model_name(embed_model),
            )
            _embed_missing_nodes(nodes, embed_model)
        norm_band = check_ingest_vectors(
            [node.embedding for node in nodes if node.embedding is not None],
            model_name=_embed_model_name(embed_model),
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
    return PreparedSource(
        file_path=file_path,
        source_id=source_id,
        source_attempt=source_attempt,
        chunk_count=len(nodes),
        embedding_seconds=time.perf_counter() - embedding_started,
        norm_band=norm_band,
    )


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
    embed_model: Any = None,
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

    Composes :func:`prepare_source_embeddings` (worker thread, no lock) and
    :func:`commit_prepared_source` (worker thread, write lock held).

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
        embed_model: Optional injected embedding model.
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
    if not nodes or shutdown_requested.is_set():
        return ReplaceSourceOutcome(0, 0, source_attempt, WriteTimings())
    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    resolved_store = _resolve_store(store)
    prepared = await asyncio.to_thread(
        prepare_source_embeddings,
        nodes,
        file_path=file_path,
        source_id=source_id,
        content_hash=content_hash,
        index_identity=index_identity,
        source_version=source_version,
        source_attempt=source_attempt,
        embed_model=embed_model,
        embed_concurrency=embed_concurrency,
        norm_guard_enabled=norm_guard_enabled,
        norm_tolerance=norm_tolerance,
    )
    if shutdown_requested.is_set():
        return ReplaceSourceOutcome(
            0,
            0,
            source_attempt,
            WriteTimings(embedding_seconds=prepared.embedding_seconds),
            norm_band=prepared.norm_band,
        )
    outcome = await asyncio.to_thread(
        commit_prepared_source,
        nodes,
        prepared,
        collection_name=collection_name,
        store=resolved_store,
        embed_model=embed_model,
    )
    if progress_callback:
        progress_callback("embed", outcome.chunks_written, outcome.chunks_written)
    return outcome
