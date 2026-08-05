"""Backward-compatible re-export shim for the reranker subpackage.

.. deprecated::
    Import from ``rag_mcp.core.retrieval.reranker`` instead.  This shim
    will be removed in v2.0.0 after all five refactor phases land.

Note: since ADR-031 (Phase 2) the reranker is a plain class constructed
by the composition root (``rag_mcp.compose.build_reranker``) with an
injected model ID.  The former independent ``load_dotenv()`` (gotcha #4)
was removed — settings are now injected, so the circular-import risk that
motivated it no longer exists.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.reranker is deprecated; "
    "import from rag_mcp.core.retrieval.reranker instead. "
    "Removal in v2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

from .core.retrieval.reranker import (  # noqa: F401
    TOKENIZER_MAX_LENGTH,
    CrossEncoderReranker,
    _select_onnx_variant,
    _sigmoid,
)
