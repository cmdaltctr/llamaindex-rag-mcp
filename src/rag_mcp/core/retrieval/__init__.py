"""Retrieval pipeline subpackage.

Provides the public entry points ``search`` and ``list_collections``,
plus the dense, sparse, fusion, policy, and reranker submodules.
Extracted from the original ``retrieval.py``, ``sparse_retriever.py``,
and ``reranker.py`` monoliths as part of Phase 1.
"""

from __future__ import annotations

from .dense import (
    _cached_query_embedding,
    _dense_query_rows,
    _distance_to_score,
    _embed_query,
    _result_source,
)
from .fusion import reciprocal_rank_fusion, rrf_with_metadata
from .pipeline import (
    _hybrid_query_rows,
    _native_sparse_query,
    _selected_sparse_backend,
    _sparse_bm25_query,
    _strip_internal_result_fields,
    list_collections,
    search,
)
from .policy import (
    _classify_query_technical,
    _effective_threshold,
    _resolve_fetch_k,
    _resolve_rerank_policy,
)
from .reranker import CrossEncoderReranker
from .sparse import (
    BM25SparseRetriever,
    _detect_native_sparse_capability,
    _make_bm25,
    _read_collection_rows,
    tokenize_english,
)

__all__ = [
    "search",
    "list_collections",
    "CrossEncoderReranker",
    "BM25SparseRetriever",
    "reciprocal_rank_fusion",
    "rrf_with_metadata",
    "tokenize_english",
]
