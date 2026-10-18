"""Protected commit of one prepared source attempt.

The commit is the indivisible mutation section of source replacement: the
store write, the exact attempt-count verification, and the stale cleanup
run under the process-wide write lock. It is a separate seam so a graph
runner can commit a prepared source through the same guarantees as
``ingest_path_async``; ``replacement.replace_source_nodes_async`` composes
it after embedding preparation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from llama_index.core.schema import BaseNode

from ..vectordb.base import VectorStore
from ._state import shutdown_requested, write_lock
from .source_state import (
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_COUNT_KEY,
    SOURCE_CHUNK_INDEX_KEY,
    SOURCE_ID_KEY,
    source_attempt_where,
)

logger = logging.getLogger(__name__)

# LanceDB rejects a filter whose ``$in`` list exceeds 100 entries, so a
# stale cleanup with more IDs than this must issue multiple delete calls,
# each within the cap. Shorter lists are safe on every backend.
STALE_DELETE_ID_BATCH_LIMIT = 100


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


@dataclass(frozen=True)
class PreparedSource:
    """One source attempt whose nodes are stamped, embedded and guarded.

    Produced by ``replacement.prepare_source_embeddings`` and consumed by
    :func:`commit_prepared_source`. The nodes stay caller-owned; the commit
    re-checks them against this record before any store mutation.
    """

    file_path: str
    source_id: str
    source_attempt: str
    chunk_count: int
    embedding_seconds: float
    norm_band: tuple[float, float] | None


def _stale_source_ids(
    store: VectorStore,
    collection_name: str,
    *,
    source_id: str,
    source_attempt: str,
) -> list[str]:
    """Return stale row IDs for one source using a source-scoped read.

    Selection reads only rows whose ``source_id`` matches through the
    store-neutral filtered row-read contract, so the work performed is
    proportional to the source's own row count, never the collection's
    (the old full-collection scan held the global write lock for
    O(collection size) per replaced file).

    The ``source_attempt`` comparison stays in Python rather than a
    backend ``$ne`` filter because stores differ in whether a missing
    metadata key satisfies inequality — only a Python comparison treats
    rows lacking the attempt key uniformly across backends. Production
    ingestion rejects pre-lineage rows before mutation, so rows without
    ``source_id`` cannot reach this scan through the normal path.
    """
    return [
        row_id
        for row_id, _text, metadata in store.iter_filtered_documents(
            collection_name,
            {SOURCE_ID_KEY: source_id},
        )
        if metadata.get(SOURCE_ATTEMPT_KEY) != source_attempt
    ]


def _check_prepared_lineage(nodes: list[BaseNode], prepared: PreparedSource) -> None:
    """Reject nodes that do not belong, complete and in order, to *prepared*.

    A graph can reach the commit seam without the standard composition, so
    the commit re-checks the lineage contract before taking the lock. A
    mismatch would otherwise write rows that verification later rejects.
    """
    problems: list[str] = []
    if len(nodes) != prepared.chunk_count:
        problems.append(f"expected {prepared.chunk_count} node(s), got {len(nodes)}")
    for index, node in enumerate(nodes):
        metadata = node.metadata
        expected = {
            SOURCE_ID_KEY: prepared.source_id,
            SOURCE_ATTEMPT_KEY: prepared.source_attempt,
            SOURCE_CHUNK_COUNT_KEY: prepared.chunk_count,
            SOURCE_CHUNK_INDEX_KEY: index,
        }
        mismatched = sorted(key for key, value in expected.items() if metadata.get(key) != value)
        if mismatched:
            problems.append(f"node {index} disagrees on {', '.join(mismatched)}")
        if node.embedding is None:
            problems.append(f"node {index} has no prepared embedding")
    if problems:
        raise IngestionStageError(
            "lineage",
            f"Prepared lineage check failed for '{prepared.file_path}': " + "; ".join(problems),
        )


def commit_prepared_source(
    nodes: list[BaseNode],
    prepared: PreparedSource,
    *,
    collection_name: str,
    store: VectorStore,
    embed_model: Any = None,
    embedding_identity: Any = None,
) -> ReplaceSourceOutcome:
    """Write, verify, and clean stale rows as one indivisible locked operation.

    The process-wide write lock is held across the store write, the exact
    attempt-count verification, and the stale cleanup. A failure before or
    during this section leaves the previous searchable version intact; a
    shutdown observed after the lock is acquired writes nothing. This
    function is blocking; async callers run it in a worker thread.

    Args:
        nodes: The nodes prepared by :func:`prepare_source_embeddings`.
        prepared: The matching prepared attempt record.
        collection_name: Target vector-store collection.
        store: The owning vector store (required; no process default).
        embed_model: Optional injected embedding model for the store write.
        embedding_identity: Optional provider and model that made the vectors
            (ADR-081). The store checks and stamps it; sent only when set.

    Returns:
        Counts plus stage timing diagnostics for this bounded source.

    Raises:
        ConnectionError: When the store backend reports a connection failure.
        IngestionStageError: ``lineage``, ``store_write``, ``store_verify``
            or ``stale_cleanup`` stage failures.
    """
    _check_prepared_lineage(nodes, prepared)
    file_path = prepared.file_path
    source_id = prepared.source_id
    source_attempt = prepared.source_attempt
    lock_started = time.perf_counter()
    with write_lock:
        lock_wait = time.perf_counter() - lock_started
        if shutdown_requested.is_set():
            return ReplaceSourceOutcome(
                0,
                0,
                source_attempt,
                WriteTimings(
                    embedding_seconds=prepared.embedding_seconds,
                    lock_wait_seconds=lock_wait,
                ),
                norm_band=prepared.norm_band,
            )

        write_started = time.perf_counter()
        identity_kwargs = {"embedding_identity": embedding_identity} if embedding_identity else {}
        try:
            store.write_nodes(nodes, collection_name, embed_model=embed_model, **identity_kwargs)
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
            durable_count = store.count_where(collection_name, verify_where)
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
                store,
                collection_name,
                source_id=source_id,
                source_attempt=source_attempt,
            )
            if stale_ids:
                # One call per slice: stores cap the IDs a single delete
                # accepts (LanceDB: 100 per ``$in`` list).
                for start in range(0, len(stale_ids), STALE_DELETE_ID_BATCH_LIMIT):
                    store.delete_ids(
                        collection_name,
                        stale_ids[start : start + STALE_DELETE_ID_BATCH_LIMIT],
                    )
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
                embedding_seconds=prepared.embedding_seconds,
                store_write_seconds=store_write_seconds,
                lock_wait_seconds=lock_wait,
                cleanup_seconds=cleanup_seconds,
            ),
            norm_band=prepared.norm_band,
        )
