"""Sparse dispatch for the hybrid retrieval pipeline.

Owns the sparse side of hybrid retrieval (tasks 2.3/3.3/3.4,
``implement-native-sparse-backend-strategy``): registry-routed
execution of the concrete sparse backends, the shared query-contract
normalisation, the native policy's mixed-coverage warning and BM25
fallback net, and the one-shot warning state.

Extracted from ``pipeline.py`` so that module stays inside the
500-line ceiling (invariant #11); ``pipeline`` re-exports the public
runners and the warning-state sets for existing callers and tests.

Design decisions pinned here:

- **Registry routing (D2/3.3):** every backend execution resolves
  through ``core/retrieval/sparse_registry.py`` — no ``if/elif``
  over backend names in execution paths.  Only the *policy* runner
  selection (native safety net versus plain BM25) is expressed once
  in ``pipeline._hybrid_query_rows``.
- **Fallback outside the strategy (D3):** the native strategy
  (:class:`~omrg.core.retrieval.native_sparse.NativeSparseRetriever`)
  propagates failures; this module catches them, emits one visible
  warning per collection, and serves BM25 through the same contract.
- **Honest diagnostics (3.4):** the ``report`` dict records the
  backend that actually ran; a fallen-back query reports ``bm25``,
  never native.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..vectordb.base import VectorStore

logger = logging.getLogger(__name__)

# One-shot warning state (per process): mixed-coverage warnings and
# native-fallback warnings fire at most once per collection.
_warned_collections: set[str] = set()
_warned_native_fallback_collections: set[str] = set()

__all__ = [
    "_emit_mixed_coverage_warning",
    "_native_sparse_query",
    "_sparse_bm25_query",
    "_sparse_query_rows",
]


def _sparse_query_rows(
    collection_name: str,
    store: VectorStore,
    query: str,
    fetch_k: int,
    backend: str = "bm25",
    metadata_filter: dict | None = None,
    *,
    timing_report: dict | None = None,
) -> list[dict]:
    """Run one registered sparse backend and normalise to pipeline rows.

    The shared sparse query contract (task 2.3): every registered
    backend returns ``(rank, doc_id, text, metadata)`` tuples through
    one interface resolved from the sparse-backend registry, and this
    converts them into the row shape the fusion stage consumes.

    Args:
        timing_report: Optional dict to accumulate ``sparse_seconds``
            into. A failed query (exception before completion) does not
            record a duration, so the fallback path's successful query
            is the only one timed (design D5).
    """
    from . import sparse_registry as _sparse_registry
    from .dense import _lineage_fields, _result_source

    Retriever = _sparse_registry.get(backend)
    t0 = time.perf_counter()
    rows = Retriever(collection_name, store=store).query(
        query,
        fetch_k,
        metadata_filter=metadata_filter,
    )
    t1 = time.perf_counter()
    if timing_report is not None:
        timing_report["sparse_seconds"] = timing_report.get("sparse_seconds", 0.0) + (t1 - t0)
    return [
        {
            "id": doc_id,
            "source": _result_source(metadata),
            "page_label": metadata.get("page_label"),
            "text": text,
            "metadata": dict(metadata),
            "reranked": False,
            **_lineage_fields(metadata),
        }
        for _rank, doc_id, text, metadata in rows
    ]


def _sparse_bm25_query(
    collection_name: str,
    store: VectorStore,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
    report: dict | None = None,
    *,
    timing_report: dict | None = None,
) -> list[dict]:
    """Run the registered BM25 backend (the fallback target)."""
    rows = _sparse_query_rows(
        collection_name,
        store,
        query,
        fetch_k,
        "bm25",
        metadata_filter,
        timing_report=timing_report,
    )
    if report is not None:
        report["sparse_backend"] = "bm25"
    return rows


def _emit_mixed_coverage_warning(collection_name: str, store: VectorStore) -> None:
    """Warn once per collection when sparse coverage is partial.

    Two eras of coverage signal: FTS-backed stores report durable
    indexed/unindexed statistics (restated for indexed versus
    unindexed rows, task 2.2); sparse-vector stores keep the
    Chroma-era paged ``has_sparse_vector`` scan.
    """
    if collection_name in _warned_collections:
        return
    coverage_fn: Callable[[str], dict | None] | None = getattr(
        store, "native_sparse_coverage", None
    )
    if coverage_fn is not None:
        try:
            stats = coverage_fn(collection_name)
        except Exception:
            return
        if stats is not None and 0 < stats["indexed"] < stats["total"]:
            _warned_collections.add(collection_name)
            logger.warning(
                "Hybrid native sparse retrieval on collection '%s' has "
                "mixed full-text coverage: %d/%d chunks are indexed by "
                "the FTS index. The next native query refreshes the "
                "index; re-ingest or create the FTS index for full "
                "durable hybrid coverage.",
                collection_name,
                stats["indexed"],
                stats["total"],
            )
        return
    total = 0
    covered = 0
    try:
        for meta in store.iter_metadatas(collection_name):
            total += 1
            if isinstance(meta, dict) and meta.get("has_sparse_vector"):
                covered += 1
    except Exception:
        return
    if 0 < covered < total:
        _warned_collections.add(collection_name)
        logger.warning(
            "Hybrid native sparse retrieval on collection '%s' has mixed "
            "coverage: %d/%d chunks have sparse vectors. Re-ingest the "
            "collection for full hybrid coverage.",
            collection_name,
            covered,
            total,
        )


def _native_sparse_query(
    collection_name: str,
    store: VectorStore,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
    report: dict | None = None,
    *,
    timing_report: dict | None = None,
) -> list[dict]:
    """Run the native policy: coverage warning, native attempt, fallback.

    The fallback net is a dispatch-boundary concern, not strategy
    behaviour (design decision 3): any native failure — capability
    absence (``NotImplementedError`` from the store's unsupported
    response) or a lifecycle/query runtime error — emits one visible
    warning per collection and serves BM25 results through the same
    contract.  The resulting sparse ranking is never labelled native:
    *report* (when supplied) records the backend that actually ran.
    """
    _emit_mixed_coverage_warning(collection_name, store)
    try:
        rows = _sparse_query_rows(
            collection_name,
            store,
            query,
            fetch_k,
            "native",
            metadata_filter,
            timing_report=timing_report,
        )
    except Exception as exc:
        if collection_name not in _warned_native_fallback_collections:
            _warned_native_fallback_collections.add(collection_name)
            logger.warning(
                "Native sparse retrieval is selected for collection '%s', "
                "but the native backend could not serve the query (%s: %s). "
                "Falling back to the BM25 sparse retriever so hybrid "
                "retrieval does not silently degrade to dense-only results.",
                collection_name,
                type(exc).__name__,
                exc,
            )
        rows = _sparse_bm25_query(
            collection_name,
            store,
            query,
            fetch_k,
            metadata_filter,
            timing_report=timing_report,
        )
        if report is not None:
            report["sparse_backend"] = "bm25"
        return rows
    if report is not None:
        report["sparse_backend"] = "native"
    return rows


def reset_warning_state() -> dict[str, set[str]]:
    """Clear the one-shot warning state (test isolation helper)."""
    _warned_collections.clear()
    _warned_native_fallback_collections.clear()
    return {
        "collections": _warned_collections,
        "native_fallback": _warned_native_fallback_collections,
    }
