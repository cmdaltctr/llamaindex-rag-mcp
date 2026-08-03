"""Backward-compatible re-export shim for the sparse retrieval subpackage.

.. deprecated::
    Import from ``rag_mcp.core.retrieval.sparse`` instead.  This shim
    will be removed in v2.0.0 after all five refactor phases land.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.sparse_retriever is deprecated; "
    "import from rag_mcp.core.retrieval.sparse instead. "
    "Removal in v2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

from .core.retrieval.sparse import (  # noqa: F401
    BM25SparseRetriever,
    _ChunkRow,
    _CachedBM25,
    _SimpleBM25Okapi,
    _detect_native_sparse_capability,
    _make_bm25,
    _read_collection_rows,
    tokenize_english,
)
