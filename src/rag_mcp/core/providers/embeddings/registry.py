"""Lazy registry for embedding providers.

Maps provider names to ``"module:attr"`` import strings resolved on first
``get()``.  Importing this module does NOT import any provider module.
Adding a provider = one new file + one ``register()`` call at the bottom of
this module (or at composition time).
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register an embedding provider.

    Args:
        name: The provider name (e.g. ``"ollama"``, ``"llamacpp"``).
        import_path: A ``"module:attr"`` string pointing at the ``build``
            callable.
    """
    _registry[name] = import_path


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the ``build(settings)`` callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the provider module's optional dependency is missing.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(
            f"Unknown embedding provider {name!r}. "
            f"Available: {sorted(_registry)}"
        )
    module_path, attr = _registry[name].split(":")
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
    return sorted(_registry)


# ── Built-in provider registrations ────────────────────────────────────
register("ollama", "rag_mcp.core.providers.embeddings.ollama:build")
register("llamacpp", "rag_mcp.core.providers.embeddings.llamacpp:build")
register("openrouter", "rag_mcp.core.providers.embeddings.openrouter:build")
