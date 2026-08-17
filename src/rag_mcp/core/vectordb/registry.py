"""Lazy registry for vector-store backends.

Maps ``VECTOR_STORE`` names to ``"module:attr"`` import strings resolved
on first ``get()``.  Importing this module does NOT import any concrete
store module (shared registry contract, PROPOSAL §4.4) — the pattern
established by ``core/retrieval/registry.py``.

``compose.build_vector_store`` resolves the configured name through
this registry instead of branching over it (architecture invariant
#10).  Adding a backend = one new module implementing the
:class:`VectorStore` ABC plus one ``register()`` call below.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register a vector-store backend.

    Args:
        name: The backend name (the ``VECTOR_STORE`` value, e.g.
            ``"chroma"``, ``"lancedb"``).
        import_path: A ``"module:attr"`` string pointing at the
            settings-driven factory callable.
    """
    _registry[name] = import_path


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the backend factory for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the backend module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown vector store {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Vector store {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered backend names."""
    return sorted(_registry)


# ── Built-in backend registrations ────────────────────────────────────
register("chroma", "rag_mcp.core.vectordb.chroma:build_vector_store_from_settings")
register("lancedb", "rag_mcp.core.vectordb.lancedb:build_vector_store_from_settings")
