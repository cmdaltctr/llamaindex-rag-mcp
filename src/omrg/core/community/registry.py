"""Lazy registry for community-detection strategies.

Maps strategy names to ``"module:attr"`` import strings resolved on first
``get()``.  Importing this module does NOT import any strategy module —
strategies stay importable on demand (shared registry contract,
PROPOSAL §4.4, modelled on ``core/chunking/registry.py``).

Adding a strategy = one new file + one ``register()`` call at the bottom of
this module.  Strategies backed by optional dependencies additionally
register an *availability probe*: a zero-argument callable that raises
``ImportError`` with an installation instruction when the dependency is
missing.  The composition root calls :func:`verify_available` at startup so
an explicit selection of an unavailable strategy fails before graph
construction instead of silently falling back.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_availability: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(
    name: str,
    import_path: str,
    *,
    availability_path: str | None = None,
) -> None:
    """Register a community-detection strategy.

    Args:
        name: The strategy name (e.g. ``"louvain"``, ``"leiden"``).
        import_path: A ``"module:attr"`` string pointing at the partition
            callable.
        availability_path: Optional ``"module:attr"`` string pointing at a
            zero-argument probe that raises ``ImportError`` when the
            strategy's optional dependencies are missing.  Base-install
            strategies omit it.
    """
    _registry[name] = import_path
    if availability_path is None:
        _availability.pop(name, None)
    else:
        _availability[name] = availability_path


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the strategy callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the strategy module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown community strategy {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Community strategy {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered strategy names."""
    return sorted(_registry)


def verify_available(name: str) -> None:
    """Fail loudly when *name* needs an optional dependency that is missing.

    Raises:
        KeyError: If *name* is not registered.
        ImportError: When the registered availability probe raises — the
            probe's message carries the installation instruction.

    Strategies without a registered probe (base-install implementations)
    pass unconditionally.
    """
    if name not in _registry:
        raise KeyError(f"Unknown community strategy {name!r}. Available: {sorted(_registry)}")
    probe_path = _availability.get(name)
    if probe_path is None:
        return
    module_path, attr = probe_path.split(":")
    probe = getattr(importlib.import_module(module_path), attr)
    probe()  # Raises ImportError with the installation instruction.


# ── Built-in strategy registrations ──────────────────────────────────
# Louvain is native (NetworkX is a base dependency) and stays the default.
register("louvain", "omrg.core.community.louvain:partition")
# Leiden delegates to the optional community-leiden extra; the probe lives
# with the adapter so this module never imports igraph.
register(
    "leiden",
    "omrg.core.community.leiden:partition",
    availability_path="omrg.integrations.leidenalg:require_leiden_installed",
)
