"""Lazy registry for LLM providers (used by metadata extraction).

Maps provider names to ``"module:attr"`` import strings resolved on first
``get()``.  Adding a provider = one new file + one ``register()`` call at
the bottom of this module (or at composition time).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from .connection import ConnectionDescriptor
from .reply import NO_FACTS, ReplyFacts

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
    "anthropic": "anthropic",
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


def describe_all() -> dict[str, ConnectionDescriptor]:
    """Return each registered provider's connection descriptor, in registration order.

    Imports each provider module, which is cheap because modules import
    LlamaIndex only inside ``build()``. A module without a ``CONNECTION``
    descriptor has no card and is left out.
    """
    described: dict[str, ConnectionDescriptor] = {}
    for name, import_path in _registry.items():
        descriptor = getattr(importlib.import_module(import_path.split(":")[0]), "CONNECTION", None)
        if descriptor is not None:
            described[name] = descriptor
    return described


def _module_attr(name: str, attr: str) -> Any:
    """Return *attr* of provider *name*'s module, or ``None`` when absent or unknown."""
    import_path = _registry.get(name)
    if import_path is None:
        return None
    return getattr(importlib.import_module(import_path.split(":")[0]), attr, None)


def reasoning_kwargs(name: str, level: str) -> dict[str, Any] | None:
    """Return the request fields provider *name* sends for reasoning *level*.

    ``None`` means nothing is sent: the level is empty, or the provider
    ignores levels (it has no ``reasoning_kwargs`` or it returns ``None``).
    """
    if not level:
        return None
    mapper = _module_attr(name, "reasoning_kwargs")
    return mapper(level) if mapper is not None else None


def ignores_reasoning(name: str) -> bool:
    """Return whether provider *name* sends nothing for any reasoning level."""
    mapper = _module_attr(name, "reasoning_kwargs")
    return mapper is None or mapper("low") is None


def reply_reader(name: str) -> Callable[[Any], ReplyFacts]:
    """Return provider *name*'s ``read_reply``, or a reader that reports nothing."""
    reader = _module_attr(name, "read_reply")
    return reader if reader is not None else (lambda _raw: NO_FACTS)


def available() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(_registry)


# ── Built-in provider registrations ────────────────────────────────────
register("ollama", "omrs.core.providers.llm.ollama:build")
register("llamacpp", "omrs.core.providers.llm.llamacpp:build")
register("openrouter", "omrs.core.providers.llm.openrouter:build")
register("openai_compatible", "omrs.core.providers.llm.openai_compatible:build")
register("anthropic", "omrs.core.providers.llm.anthropic:build")
