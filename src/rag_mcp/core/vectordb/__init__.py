"""Vector store abstraction layer (Phase 3 refactor, ADR-034).

Provides the :class:`VectorStore` ABC and a process-wide default store
singleton wired by the composition root (``rag_mcp.compose``).

Pipeline modules access the store through :func:`get_default_store` when
no store is explicitly injected.  ``compose.ensure_runtime_setup``
constructs the default from the ``VECTOR_STORE`` setting and registers
it here so every caller shares one instance (and one generation counter
dict, which the BM25 sparse retriever depends on for cache invalidation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import VectorStore

__all__ = [
    "VectorStore",
    "get_default_store",
    "set_default_store",
    "reset_default_store",
]

# Module-level default store.  Set by ``compose.ensure_runtime_setup``
# so all pipeline callers share one instance.
_default_store: VectorStore | None = None


def get_default_store() -> VectorStore:
    """Return the process-wide default vector store.

    Lazily constructs a ChromaDB-backed store on first call when
    ``compose.ensure_runtime_setup`` has not run yet (e.g. in tests
    that import pipeline modules directly).

    Returns:
        The default :class:`VectorStore` instance.
    """
    global _default_store
    if _default_store is None:
        from .chroma import build_chroma_vector_store

        _default_store = build_chroma_vector_store()
    return _default_store


def set_default_store(store: VectorStore) -> None:
    """Set the process-wide default store (used by the composition root)."""
    global _default_store
    _default_store = store


def reset_default_store() -> None:
    """Clear the default store (test helper)."""
    global _default_store
    _default_store = None


def __getattr__(name: str):
    """Lazy re-export of ``VectorStore`` to avoid eager imports."""
    if name == "VectorStore":
        from .base import VectorStore

        return VectorStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
