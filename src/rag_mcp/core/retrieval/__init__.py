"""Retrieval pipeline subpackage.

Provides the public entry points ``search`` and ``list_collections``,
plus the dense, sparse, fusion, policy, and reranker submodules.
Extracted from the original ``retrieval.py``, ``sparse_retriever.py``,
and ``reranker.py`` monoliths as part of Phase 1.

Pipeline modules are imported **lazily** (PEP 562 ``__getattr__``) so
that importing this package never eagerly imports a pipeline module —
mirrors the lazy-registry contract (PROPOSAL §4.4) and keeps the
config/compose/DI layering free of import cycles.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "search",
    "list_collections",
    "CrossEncoderReranker",
    "BM25SparseRetriever",
    "reciprocal_rank_fusion",
    "rrf_with_metadata",
    "tokenize_english",
]

# Legacy name -> owning submodule (imported on demand).
_NAMES: dict[str, str] = {
    "_cached_query_embedding": ".dense",
    "_dense_query_rows": ".dense",
    "_embed_query": ".dense",
    "_result_source": ".dense",
    "reciprocal_rank_fusion": ".fusion",
    "rrf_with_metadata": ".fusion",
    "_hybrid_query_rows": ".pipeline",
    "_native_sparse_query": ".pipeline",
    "_selected_sparse_backend": ".pipeline",
    "_sparse_bm25_query": ".pipeline",
    "_strip_internal_result_fields": ".pipeline",
    "list_collections": ".pipeline",
    "search": ".pipeline",
    "_classify_query_technical": ".policy",
    "_effective_threshold": ".policy",
    "_resolve_fetch_k": ".policy",
    "_resolve_rerank_policy": ".policy",
    "CrossEncoderReranker": ".reranker",
    "BM25SparseRetriever": ".sparse",
    "_detect_native_sparse_capability": ".sparse",
    "_make_bm25": ".sparse",
    "_read_collection_rows": ".sparse",
    "tokenize_english": ".sparse",
}


def __getattr__(name: str) -> Any:
    """Resolve a lazily-imported pipeline name (PEP 562)."""
    if name in _NAMES:
        import importlib

        module = importlib.import_module(_NAMES[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
