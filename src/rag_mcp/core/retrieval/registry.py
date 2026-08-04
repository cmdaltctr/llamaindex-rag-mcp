"""Lazy registry for retrieval strategies.

Maps strategy names to ``"module:attr"`` import strings resolved on
first ``get()``.  Importing this module does NOT import any strategy
module (shared registry contract, PROPOSAL §4.4).

Adding a strategy = one new file + one line in ``REGISTRY``.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

REGISTRY: dict[str, str] = {
    "dense": "rag_mcp.core.retrieval.dense:_dense_query_rows",
    "bm25": "rag_mcp.core.retrieval.sparse:BM25SparseRetriever",
    "fusion": "rag_mcp.core.retrieval.fusion:rrf_with_metadata",
    "reranker": "rag_mcp.core.retrieval.reranker:CrossEncoderReranker",
}

_cache: dict[str, Callable[..., Any]] = {}


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the strategy callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the strategy module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in REGISTRY:
        raise KeyError(
            f"Unknown retrieval strategy {name!r}. "
            f"Available: {sorted(REGISTRY)}"
        )
    module_path, attr = REGISTRY[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Retrieval strategy {name!r} could not be imported "
            f"(module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered strategy names."""
    return sorted(REGISTRY)
