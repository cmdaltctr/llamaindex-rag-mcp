"""Backward-compatible re-export shim for the reranker subpackage.

.. deprecated::
    Import from ``rag_mcp.core.retrieval.reranker`` instead.  This shim
    will be removed in v2.0.0 after all five refactor phases land.

Note: ``reranker.py`` imports ``dotenv`` independently of ``config.py``
(gotcha #4 — don't "fix", circular import risk).  The actual module at
``core/retrieval/reranker.py`` retains this independent ``load_dotenv()``
call.
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
    RERANK_MODEL,
    TOKENIZER_MAX_LENGTH,
    CrossEncoderReranker,
    _select_onnx_variant,
    _sigmoid,
)
