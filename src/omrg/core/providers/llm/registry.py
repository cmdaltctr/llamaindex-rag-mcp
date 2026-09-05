"""Lazy registry for LLM providers (used by metadata extraction).

Maps provider names to ``"module:attr"`` import strings resolved on first
``get()``.  Adding a provider = one new file + one ``register()`` call at
the bottom of this module (or at composition time).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register an LLM provider.

    Args:
        name: The provider name (e.g. ``"ollama"``, ``"llamacpp"``).
        import_path: A ``"module:attr"`` string pointing at the ``build``
            callable.
    """
    _registry[name] = import_path


# Provider name → the pyproject.toml optional-dependency extra that supplies
# it.  Providers absent from this map ship in the base install; a missing
# import for one of those is a genuine environment fault, not a missing extra.
_PROVIDER_EXTRAS: dict[str, str] = {
    "llamacpp": "llamacpp",
    "openrouter": "openrouter",
}


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the ``build(settings)`` callable for *name*.

    Raises:
        KeyError: If *name* is not registered.
        ImportError: If the optional dependency is missing.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown LLM provider {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        # Only suggest `--extra <x>` when that extra actually exists in
        # pyproject.toml.  Not every provider name is an extra name — e.g.
        # `ollama` ships in the base install — and pointing an operator at a
        # non-existent extra turns a clear error into a wild goose chase.
        hint = (
            f"  Install it with:  uv sync --extra {_PROVIDER_EXTRAS[name]}"
            if name in _PROVIDER_EXTRAS
            else f"  Missing import: {exc}"
        )
        raise ImportError(f"Provider {name!r} requires an optional dependency.\n{hint}") from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(_registry)


# ── Built-in provider registrations ────────────────────────────────────
register("ollama", "omrg.core.providers.llm.ollama:build")
register("llamacpp", "omrg.core.providers.llm.llamacpp:build")
register("openrouter", "omrg.core.providers.llm.openrouter:build")
