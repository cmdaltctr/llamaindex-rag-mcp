"""Retrieval pipeline orchestrator.

The main ``search()`` entry point that ties together dense vector search,
sparse BM25/native retrieval, Reciprocal Rank Fusion, and cross-encoder
reranking.  Also hosts ``list_collections()`` and the hybrid query
machinery.  Extracted from the original ``retrieval.py`` monolith as
part of Phase 1.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import chromadb

from ...chroma_utils import iter_collection_metadatas
from ...config import (
    CHROMA_PERSIST_DIR,
    HYBRID_ENABLED,
    HYBRID_RRF_K,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from .dense import _dense_query_rows, _result_source
from .fusion import rrf_with_metadata
from .policy import (
    _classify_query_technical,
    _effective_threshold,
    _resolve_fetch_k,
    _resolve_rerank_policy,
)
from .reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)
_warned_collections: set[str] = set()
_warned_native_fallback_collections: set[str] = set()


def _selected_sparse_backend() -> str:
    from ... import config as _config

    return getattr(
        _config,
        "RESOLVED_HYBRID_SPARSE_BACKEND",
        getattr(_config, "HYBRID_SPARSE_BACKEND", "bm25"),
    )


def _sparse_bm25_query(
    collection_name: str,
    collection: Any,
    query: str,
    fetch_k: int,
) -> list[dict]:
    from .sparse import BM25SparseRetriever

    rows = BM25SparseRetriever(collection_name, collection=collection).query(query, fetch_k)
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


def _emit_mixed_coverage_warning(collection_name: str, collection: Any) -> None:
    if collection_name in _warned_collections:
        return
    total = 0
    covered = 0
    try:
        for meta in iter_collection_metadatas(collection):
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
    collection: Any,
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
    return _sparse_bm25_query(collection_name, collection, query, fetch_k)


def _hybrid_query_rows(
    collection: Any,
    collection_name: str,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
) -> list[dict]:
    backend = _selected_sparse_backend()
    with ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(
            _dense_query_rows, collection, query, fetch_k, metadata_filter,
        )
        if backend == "native":
            _emit_mixed_coverage_warning(collection_name, collection)
            sparse_future = executor.submit(
                _native_sparse_query, collection_name, collection, query, fetch_k,
            )
        else:
            sparse_future = executor.submit(
                _sparse_bm25_query, collection_name, collection, query, fetch_k,
            )
        dense_rows = dense_future.result()
        sparse_rows = sparse_future.result()

    return rrf_with_metadata(dense_rows, sparse_rows, k=HYBRID_RRF_K)[:fetch_k]


def _strip_internal_result_fields(result: dict) -> dict:
    """Remove retrieval diagnostics that are not public API by default."""
    public = dict(result)
    for key in ("id", "fused_score", "dense_rank", "sparse_rank", "fused_rank"):
        public.pop(key, None)
    return public


def search(
    query: str,
    top_k: int = TOP_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    rerank: bool | None = None,
    hybrid: bool = HYBRID_ENABLED,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
    include_diagnostics: bool = False,
    technical_fraction: float | None = None,
    fetch_k: int | None = None,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return (default from env or 5).
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).  When ``rerank``
            is True the threshold is scaled down by 30× because
            cross-encoder sigmoid scores occupy a lower range than
            cosine similarity.  For example, 0.3 becomes 0.01.
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
            The policy resolver checks ``RERANK_ENABLED``, then
            ``RERANK_ENABLED_FOR_SEMANTIC`` and ``HARD_TECHNICAL_THRESHOLD``
            to decide whether to enable reranking based on query type.
        hybrid: If True, fuse dense vector results with sparse BM25/native
            sparse rankings via Reciprocal Rank Fusion before reranking.
        collection_name: Name of the ChromaDB collection to search
            (default ``"documents"`` for backward compatibility).
        metadata_filter: Optional ChromaDB ``where`` clause to filter
            results by metadata fields (e.g. ``{"category": "AI"}``).
            When provided, the filter is applied server-side via
            ChromaDB's native ``where`` parameter — only matching
            chunks are returned from the vector store.
        include_diagnostics: If True, preserve hybrid rank diagnostic
            fields (``id``, ``fused_score``, ``dense_rank``, ``sparse_rank``,
            ``fused_rank``) and policy resolution reason for experiments.
            Public MCP/CLI callers leave this False so result shape stays stable.
        technical_fraction: Optional workload-level identifier-heavy fraction
            (0.0–1.0). When provided, it overrides the single-query classifier
            for policy resolution.
        fetch_k: Optional override for the candidate pool size.  When set,
            bypasses the ``max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)``
            formula so experiment runners can test genuinely distinct pool
            sizes.  Production callers leave this as None.  The value is
            still clamped to the collection size.

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      – float (0–1, vector similarity or reranker score)
            source     – source file path
            page_label – page number (or None)
            text       – the chunk text
            reranked   – bool (True if cross-encoder re-scored the result)

        When ``include_diagnostics=True``, each result also includes:
            rerank_reason – string explaining the policy decision

    Raises:
        ValueError: If ``metadata_filter`` is rejected by ChromaDB
            (unsupported operator, type mismatch, etc.).  Other
            ChromaDB-side failures propagate as their original
            exception types so the MCP layer can classify them.
    """
    # Resolve effective rerank behaviour from policy.
    effective_rerank, rerank_reason = _resolve_rerank_policy(
        rerank, query, technical_fraction=technical_fraction,
    )

    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.  See ADR-016 Decision 2.
    # When fetch_k is explicitly provided (experiment runners), it
    # bypasses the formula to allow genuinely distinct pool sizes.
    resolved_fetch_k = _resolve_fetch_k(
        top_k, effective_rerank, collection.count(),
        fetch_k_override=fetch_k,
    )

    if hybrid:
        results = _hybrid_query_rows(
            collection, collection_name, query, resolved_fetch_k, metadata_filter,
        )
    else:
        results = _dense_query_rows(
            collection, query, resolved_fetch_k, metadata_filter,
        )

    # Optional: re-score with cross-encoder reranker.
    if effective_rerank and results:
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, results, top_k=top_k)
        # Propagate the reranked flag from the internal _reranked key.
        for r in results:
            r["reranked"] = r.pop("_reranked", False)

    # Filter by similarity threshold (applies after reranking).
    #
    # Reranker scores are sigmoid-normalised and occupy a different range
    # than cosine similarity.  A cosine threshold of 0.3 is a weak match,
    # but the reranker may assign a valid result only 0.015 (sigmoid).
    # Scale the threshold down by 30× when reranking to avoid over-filtering.
    effective_threshold = _effective_threshold(similarity_threshold, effective_rerank)
    if effective_threshold > 0.0:
        results = [
            r for r in results if r["score"] >= effective_threshold
        ]

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    # Attach policy diagnostics when requested.
    if include_diagnostics:
        for r in results:
            r["rerank_reason"] = rerank_reason

    if not include_diagnostics:
        results = [_strip_internal_result_fields(r) for r in results]
    return results


def list_collections() -> list[dict]:
    """List all ChromaDB collections with document and chunk counts.

    Returns:
        A list of dicts, each with:
        - ``name`` — collection name
        - ``document_count`` — approximate number of unique source files
        - ``chunk_count`` — total number of chunks in the collection
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    collections: list[dict] = []
    for coll in db.list_collections():
        try:
            chunk_count = coll.count()
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in iter_collection_metadatas(coll):
                    if meta is None:
                        continue
                    source = (
                        meta.get("file_path")
                        or meta.get("file_name")
                        or "unknown"
                    )
                    doc_sources.add(source)

            collections.append({
                "name": coll.name,
                "document_count": len(doc_sources),
                "chunk_count": chunk_count,
            })
        except Exception:
            # Skip collections that can't be accessed
            continue
    return collections
