"""Lazy registry for document chunking strategies.

Maps strategy names to ``"module:attr"`` import strings resolved on first
``get()``.  Importing this module does NOT import any strategy module —
strategies stay importable on demand (shared registry contract,
PROPOSAL §4.4).

Adding a strategy = one new file + one ``register()`` call at the bottom of
this module (or at composition time).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register a chunking strategy.

    Args:
        name: The strategy name (e.g. ``"code"``, ``"sentence"``).
        import_path: A ``"module:attr"`` string pointing at the callable.
    """
    _registry[name] = import_path


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the strategy callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the strategy module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown chunking strategy {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Chunking strategy {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered strategy names."""
    return sorted(_registry)


# ── Built-in strategy registrations ────────────────────────────────────
register("sentence", "rag_mcp.core.chunking.sentence:chunk_sentence_file_async")
register("code", "rag_mcp.core.chunking.code:chunk_code_file_async")
register("config", "rag_mcp.core.chunking.config_file:chunk_config_file")
