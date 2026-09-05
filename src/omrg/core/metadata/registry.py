"""Lazy registry for metadata extraction strategies.

Maps strategy names to ``"module:attr"`` import strings resolved on first
``get()``.  Importing this module does NOT import any strategy module
(shared registry contract, PROPOSAL §4.4).

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
    """Register a metadata extraction strategy.

    Args:
        name: The strategy name (e.g. ``"keyword"``, ``"ollama"``).
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
        raise KeyError(f"Unknown metadata strategy {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Metadata strategy {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered strategy names."""
    return sorted(_registry)


# ── Built-in strategy registrations ────────────────────────────────────
register("keyword", "omrg.core.metadata.keyword:_extract_keyword_async")
register("ollama", "omrg.core.metadata.ollama:_extract_ollama_async")
register("llamacpp", "omrg.core.metadata.llamacpp:_extract_llamacpp_chat_async")
register("llamaindex", "omrg.core.metadata.llamaindex:_extract_llamaindex_async")
register("openrouter", "omrg.core.metadata.openrouter:_extract_openrouter_chat_async")
