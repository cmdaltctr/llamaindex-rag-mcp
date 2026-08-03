"""Backward-compatible re-export shim for the retrieval pipeline subpackage.

.. deprecated::
    Import from ``rag_mcp.core.retrieval`` instead.  This shim will be
    removed in v2.0.0 after all five refactor phases land.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.retrieval is deprecated; "
    "import from rag_mcp.core.retrieval instead. "
    "Removal in v2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

# ── Config variables (re-exported for backward compatibility) ───────────
from .config import (  # noqa: F401
    CHROMA_PERSIST_DIR,
    HYBRID_ENABLED,
    HYBRID_RRF_K,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from .chroma_utils import iter_collection_metadatas  # noqa: F401

# ── Dense ───────────────────────────────────────────────────────────────
from .core.retrieval.dense import (  # noqa: F401
    _QUERY_EMBED_CACHE_MAXSIZE,
    _cached_query_embedding,
    _dense_query_rows,
    _distance_to_score,
    _embed_query,
    _result_source,
)

# ── Fusion ──────────────────────────────────────────────────────────────
from .core.retrieval.fusion import (  # noqa: F401
    reciprocal_rank_fusion,
    rrf_with_metadata,
)

# ── Policy ──────────────────────────────────────────────────────────────
from .core.retrieval.policy import (  # noqa: F401
    _classify_query_technical,
    _effective_threshold,
    _resolve_fetch_k,
    _resolve_rerank_policy,
)

# ── Reranker ────────────────────────────────────────────────────────────
from .core.retrieval.reranker import CrossEncoderReranker  # noqa: F401

# ── Pipeline ────────────────────────────────────────────────────────────
from .core.retrieval.pipeline import (  # noqa: F401
    _hybrid_query_rows,
    _native_sparse_query,
    _selected_sparse_backend,
    _sparse_bm25_query,
    _strip_internal_result_fields,
    list_collections,
    search,
)

# ── Logger (for tests that patch rag_mcp.retrieval.logger) ──────────────
import logging  # noqa: E402

logger = logging.getLogger(__name__)  # noqa: F401
