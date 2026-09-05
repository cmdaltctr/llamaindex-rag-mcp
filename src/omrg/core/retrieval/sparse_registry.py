"""Lazy registry for concrete sparse retrieval backends.

Maps concrete sparse backend names to ``"module:attr"`` import
strings resolved on first :func:`get`.  Importing this module does
NOT import any strategy module (shared registry contract, PROPOSAL
§4.4) — the pattern established by ``core/retrieval/registry.py``
and ``core/vectordb/registry.py``.

``auto`` is deliberately NOT registered here: it is a
capability-selection policy resolved by the composition root to one
of the concrete names before query execution (design decision 2).
Name validation at the composition boundary lists ``auto`` plus
:func:`available` (task 3.5).

Adding a backend = one new file + one ``register()`` call at the
bottom of this module.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register a concrete sparse backend strategy.

    Args:
        name: The backend name (``"bm25"``, ``"native"``).
        import_path: A ``"module:attr"`` string pointing at the
            strategy class.
    """
    _registry[name] = import_path


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the backend class for *name*.

    Args:
        name: The concrete backend name (e.g. ``"bm25"``, ``"native"``).

    Returns:
        The registered backend class, imported on first use and
        cached afterwards.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the strategy module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown sparse backend {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Sparse backend {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered concrete backend names.

    Returns:
        Sorted names of every registered concrete backend (``auto``
        is never included — it is an unregistered policy).
    """
    return sorted(_registry)


# ── Built-in backend registrations ────────────────────────────────────
register("bm25", "omrg.core.retrieval.sparse:BM25SparseRetriever")
register("native", "omrg.core.retrieval.native_sparse:NativeSparseRetriever")
