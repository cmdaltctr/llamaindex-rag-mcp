"""Lazy registry for embedding providers.

Maps provider names to ``"module:attr"`` import strings resolved on first
``get()``.  Importing this module does NOT import any provider module.
Adding a provider = one new file + one line in ``REGISTRY``.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

REGISTRY: dict[str, str] = {
    "ollama": "rag_mcp.core.providers.embeddings.ollama:build",
    "llamacpp": "rag_mcp.core.providers.embeddings.llamacpp:build",
    "openrouter": "rag_mcp.core.providers.embeddings.openrouter:build",
}

_cache: dict[str, Callable[..., Any]] = {}


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the ``build(settings)`` callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the provider module's optional dependency is missing.
    """
    if name in _cache:
        return _cache[name]
    if name not in REGISTRY:
        raise KeyError(
            f"Unknown embedding provider {name!r}. "
            f"Available: {sorted(REGISTRY)}"
        )
    module_path, attr = REGISTRY[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Provider {name!r} requires an optional dependency. "
            f"Install it with:  uv sync --extra {name}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(REGISTRY)
