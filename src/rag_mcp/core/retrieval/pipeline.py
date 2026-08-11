"""Retrieval pipeline orchestrator.

The main ``search()`` entry point that ties together dense vector search,
sparse BM25/native retrieval, Reciprocal Rank Fusion, and cross-encoder
reranking.  Also hosts ``list_collections()`` and the hybrid query
machinery.  Extracted from the original ``retrieval.py`` monolith as
part of Phase 1; rewired through the vector store ABC in Phase 3.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..settings import resolve_effective_settings
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from .registry import get as _retrieval_get

logger = logging.getLogger(__name__)
_warned_collections: set[str] = set()
_warned_native_fallback_collections: set[str] = set()


def _resolve_store(store: VectorStore | None) -> VectorStore:
    """Return the given store or the process-wide default."""
    return store if store is not None else get_default_store()


def _selected_sparse_backend(settings: Any) -> str:
    """Return the sparse backend from the injected settings.

    The ``auto`` capability probe runs once in the composition root, which
    bakes the concrete backend into ``EffectiveSettings`` — so this is a
    plain read, not a probe.
    """
    return settings.retrieval.hybrid_sparse_backend


def _sparse_bm25_query(
    collection_name: str,
    store: VectorStore,
    query: str,
    fetch_k: int,
) -> list[dict]:
    from .dense import _result_source

    BM25SparseRetriever = _retrieval_get("bm25")
    rows = BM25SparseRetriever(collection_name, store=store).query(query, fetch_k)
    return [
        {
            "id": doc_id,
            "source": _result_source(metadata),
            "page_label": metadata.get("page_label"),
            "text": text,
            "metadata": dict(metadata),
            "reranked": False,
        }
        for _rank, doc_id, text, metadata in rows
    ]


def _emit_mixed_coverage_warning(collection_name: str, store: VectorStore) -> None:
    if collection_name in _warned_collections:
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
) -> list[dict]:
    """Return sparse results for native mode, falling back safely in v1."""
    if collection_name not in _warned_native_fallback_collections:
        _warned_native_fallback_collections.add(collection_name)
        logger.warning(
            "Native ChromaDB sparse retrieval is selected for collection '%s', "
            "but this runtime cannot issue a native sparse query. Falling "
            "back to the BM25 sparse retriever so hybrid retrieval does not "
            "silently degrade to dense-only results.",
            collection_name,
        )
    return _sparse_bm25_query(collection_name, store, query, fetch_k)


def _hybrid_query_rows(
    store: VectorStore,
    collection_name: str,
    query: str,
    fetch_k: int,
    rrf_k: int,
    settings: Any,
    metadata_filter: dict | None = None,
) -> list[dict]:
    backend = _selected_sparse_backend(settings)
    _dense_query_rows = _retrieval_get("dense")
    with ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(
            _dense_query_rows,
            store,
            collection_name,
            query,
            fetch_k,
            metadata_filter,
        )
        if backend == "native":
            _emit_mixed_coverage_warning(collection_name, store)
            sparse_future = executor.submit(
                _native_sparse_query,
                collection_name,
                store,
                query,
                fetch_k,
            )
        else:
            sparse_future = executor.submit(
                _sparse_bm25_query,
                collection_name,
                store,
                query,
                fetch_k,
            )
        dense_rows = dense_future.result()
        sparse_rows = sparse_future.result()

    return _retrieval_get("fusion")(dense_rows, sparse_rows, k=rrf_k)[:fetch_k]


def _strip_internal_result_fields(result: dict) -> dict:
    """Remove retrieval diagnostics that are not public API by default."""
    public = dict(result)
    for key in ("id", "fused_score", "dense_rank", "sparse_rank", "fused_rank"):
        public.pop(key, None)
    return public


def search(
    query: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
    include_diagnostics: bool = False,
    technical_fraction: float | None = None,
    fetch_k: int | None = None,
    reranker: Any = None,
    store: VectorStore | None = None,
    effective_settings: Any = None,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return.  When ``None``, the
            resolved default applies: the profile's ``top_k`` when
            ``effective_settings`` is provided, else ``settings.top_k``.
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).  When ``rerank``
            is True the threshold is scaled down by 30x because
            cross-encoder sigmoid scores occupy a lower range than
            cosine similarity.  For example, 0.3 becomes 0.01.
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
            When ``effective_settings`` is provided, the profile's
            ``reranker_enabled`` takes precedence over the global default.
            Explicit ``rerank`` flags always bypass both.
        hybrid: If True, fuse dense vector results with sparse BM25/native
            sparse rankings via Reciprocal Rank Fusion before reranking.
            When ``None``, the profile's ``hybrid_enabled`` applies if
            ``effective_settings`` is provided, else ``settings.hybrid_enabled``.
        collection_name: Name of the collection to search
            (default ``"documents"`` for backward compatibility).
        metadata_filter: Optional store ``where`` clause to filter
            results by metadata fields (e.g. ``{"category": "AI"}``).
            When provided, the filter is applied server-side — only
            matching chunks are returned from the vector store.
        include_diagnostics: If True, preserve hybrid rank diagnostic
            fields (``id``, ``fused_score``, ``dense_rank``, ``sparse_rank``,
            ``fused_rank``) and policy resolution reason for experiments.
            Public MCP/CLI callers leave this False so result shape stays stable.
        technical_fraction: Optional workload-level identifier-heavy fraction
            (0.0-1.0). When provided, it overrides the single-query classifier
            for policy resolution.
        fetch_k: Optional override for the candidate pool size.  When set,
            bypasses the ``max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)``
            formula so experiment runners can test genuinely distinct pool
            sizes.  Production callers leave this as None.  The value is
            still clamped to the collection size.
        reranker: Optional pre-constructed ``CrossEncoderReranker``
            (dependency injection — the composition root builds one via
            ``rag_mcp.compose.build_reranker``).  When ``None``, a fresh
            instance is constructed; the underlying ONNX session is still
            cached process-wide keyed by model ID, so the model is loaded
            at most once per process regardless of how many instances are
            created.
        store: Optional injected :class:`VectorStore` (defaults to the
            process-wide store constructed by ``compose``).
        effective_settings: Optional :class:`EffectiveSettings` resolved
            by :class:`ProfileResolver` for this collection (Phase 4).
            When provided, its Tier 2 levers (``top_k``, ``reranker_enabled``,
            ``hybrid_enabled``) supply the defaults for omitted parameters,
            taking precedence over the global ``settings`` singleton.

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      - float (0-1, vector similarity or reranker score)
            source     - source file path
            page_label - page number (or None)
            text       - the chunk text
            reranked   - bool (True if cross-encoder re-scored the result)

        When ``include_diagnostics=True``, each result also includes:
            rerank_reason - string explaining the policy decision

    Raises:
        ValueError: If ``metadata_filter`` is rejected by the store
            (unsupported operator, type mismatch, etc.).  Other
            store-side failures propagate as their original exception
            types so the MCP layer can classify them.
    """
    # Phase 4: profile-resolved levers take precedence over global defaults.
    from .policy import (
        _effective_threshold,
        _resolve_fetch_k,
        _resolve_rerank_policy,
    )

    # Resolve the settings ONCE at the entry-point boundary. An explicitly
    # passed instance always wins; otherwise the composition root's default
    # is used. Nothing below this line consults any other source.
    resolved_settings = resolve_effective_settings(effective_settings)

    # A profile-resolved instance carries the profile's reranker decision;
    # the server default does not express a profile opinion.
    profile_reranker = (
        effective_settings.reranker_enabled if effective_settings is not None else None
    )
    if top_k is None:
        top_k = resolved_settings.retrieval.top_k
    if hybrid is None:
        hybrid = resolved_settings.retrieval.hybrid_enabled
    if similarity_threshold is None:
        similarity_threshold = resolved_settings.retrieval.similarity_threshold

    # Resolve effective rerank behaviour from policy.
    effective_rerank, rerank_reason = _resolve_rerank_policy(
        rerank,
        query,
        resolved_settings,
        technical_fraction=technical_fraction,
        profile_reranker_enabled=profile_reranker,
    )

    resolved_store = _resolve_store(store)

    chunk_count = resolved_store.count(collection_name)
    if chunk_count == 0:
        return []

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.  See ADR-016 Decision 2.
    # When fetch_k is explicitly provided (experiment runners), it
    # bypasses the formula to allow genuinely distinct pool sizes.
    resolved_fetch_k = _resolve_fetch_k(
        top_k,
        effective_rerank,
        chunk_count,
        resolved_settings,
        fetch_k_override=fetch_k,
    )

    _dense_query_rows = _retrieval_get("dense")
    if hybrid:
        results = _hybrid_query_rows(
            resolved_store,
            collection_name,
            query,
            resolved_fetch_k,
            resolved_settings.retrieval.hybrid_rrf_k,
            resolved_settings,
            metadata_filter,
        )
    else:
        results = _dense_query_rows(
            resolved_store,
            collection_name,
            query,
            resolved_fetch_k,
            metadata_filter,
        )

    # Optional: re-score with cross-encoder reranker.
    active_backend: str | None = None
    if effective_rerank and results:
        if reranker is None:
            from .backend import build_reranker_from_settings

            reranker = build_reranker_from_settings(resolved_settings)
        results = reranker.rerank(query, results, top_k=top_k)
        # Record which backend actually ran (may differ from the settings
        # value when the torch extra is missing and the helper fell back
        # to ONNX).
        active_backend = getattr(reranker, "backend_name", None)
        # Propagate the reranked flag from the internal _reranked key.
        for r in results:
            r["reranked"] = r.pop("_reranked", False)
        # The reranker's own failure reason (if any) is more specific than
        # the policy string computed before reranking ran — surface it.
        failure_reason = getattr(reranker, "last_failure_reason", None)
        if failure_reason:
            rerank_reason = failure_reason

    # Filter by similarity threshold (applies after reranking).
    #
    # Reranker scores are sigmoid-normalised and occupy a different range
    # than cosine similarity.  A cosine threshold of 0.3 is a weak match,
    # but the reranker may assign a valid result only 0.015 (sigmoid).
    # Scale the threshold down by 30x when reranking to avoid over-filtering.
    # Uses whether reranking actually succeeded (the "reranked" flag), not
    # merely whether it was requested — a failed reranker leaves raw cosine
    # scores in place, which the ÷30-scaled threshold would over-admit.
    rerank_succeeded = (
        effective_rerank and bool(results) and all(r.get("reranked", False) for r in results)
    )
    effective_threshold = _effective_threshold(similarity_threshold, rerank_succeeded)
    if effective_threshold > 0.0:
        results = [r for r in results if r["score"] >= effective_threshold]

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    # Attach policy diagnostics when requested.
    if include_diagnostics:
        for r in results:
            r["rerank_reason"] = rerank_reason
            # Attach the active backend name alongside the failure reason
            # so a torch-fallback or a failed backend is distinguishable
            # from reranking being switched off (ADR-029 §3 deferred
            # item 2, now landed).
            if active_backend is not None:
                r["rerank_backend"] = active_backend

    if not include_diagnostics:
        results = [_strip_internal_result_fields(r) for r in results]
    return results


def list_collections(
    store: VectorStore | None = None,
) -> list[dict]:
    """List all collections with document and chunk counts.

    Args:
        store: Optional injected :class:`VectorStore`.

    Returns:
        A list of dicts, each with:
        - ``name`` — collection name
        - ``document_count`` — approximate number of unique source files
        - ``chunk_count`` — total number of chunks in the collection
    """
    resolved_store = _resolve_store(store)

    collections: list[dict] = []
    for name in resolved_store.list_collections():
        try:
            chunk_count = resolved_store.count(name)
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in resolved_store.iter_metadatas(name):
                    if meta is None:
                        continue
                    source = meta.get("file_path") or meta.get("file_name") or "unknown"
                    doc_sources.add(source)

            collections.append(
                {
                    "name": name,
                    "document_count": len(doc_sources),
                    "chunk_count": chunk_count,
                }
            )
        except Exception:  # noqa: S112
            # Skip collections that can't be accessed
            continue
    return collections
