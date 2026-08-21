"""Lazy registry for vector-store backends.

Maps ``VECTOR_STORE`` names to ``"module:attr"`` import strings resolved
on first ``get()``.  Importing this module does NOT import any concrete
store module (shared registry contract, PROPOSAL §4.4) — the pattern
established by ``core/retrieval/registry.py``.

``compose.build_vector_store`` resolves the configured name through
this registry instead of branching over it (architecture invariant
#10).  Adding a backend = one new module implementing the
:class:`VectorStore` ABC plus one ``register()`` call below.

Each entry carries optional-backend availability metadata (task 3.1,
design D4): the required import modules and their distributions, the
optional-extra name, backend-specific installation guidance, and a
sparse-capability probe marker.  ``availability()``/``verify_available()``
distinguish unknown, absent, partial and broken installs generically —
no store-name branches in the dispatch path.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from importlib.util import find_spec
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, Callable[..., Any]] = {}
_metadata: dict[str, dict[str, Any]] = {}


def register(
    name: str,
    import_path: str,
    *,
    requires: dict[str, str] | None = None,
    extra: str | None = None,
    install_hint: str | None = None,
    native_sparse_probe: Any = None,
    summary: str | None = None,
) -> None:
    """Register a vector-store backend.

    Args:
        name: The backend name (the ``VECTOR_STORE`` value, e.g.
            ``"chroma"``, ``"lancedb"``).
        import_path: A ``"module:attr"`` string pointing at the
            settings-driven factory callable.
        requires: Mapping of import-module name to distribution name the
            backend needs (empty means "no optional requirement").
        extra: The optional-extra name the packages ship under, or
            ``None`` for a base-install backend.
        install_hint: Operator-facing installation guidance.
        native_sparse_probe: Truthy when the backend advertises a native
            sparse retrieval route, else ``None``.
        summary: A ``"module:attr"`` string resolving to a
            ``(settings) -> str`` one-line storage summary, or ``None``.
    """
    _registry[name] = import_path
    _metadata[name] = {
        "requires": dict(requires or {}),
        "extra": extra,
        "install_hint": install_hint,
        "native_sparse_probe": native_sparse_probe,
        "summary": summary,
    }


def describe(name: str) -> dict[str, Any]:
    """Return the availability metadata declared for *name*.

    Args:
        name: A registered backend name.

    Returns:
        A copy of the entry metadata: ``requires`` (module → distribution),
        ``extra``, ``install_hint``, ``native_sparse_probe`` and
        ``summary``.

    Raises:
        KeyError: If *name* is not registered.
    """
    if name not in _registry:
        raise KeyError(f"Unknown vector store {name!r}. Available: {sorted(_registry)}")
    meta = _metadata.get(name, {})
    return {
        "requires": dict(meta.get("requires", {})),
        "extra": meta.get("extra"),
        "install_hint": meta.get("install_hint"),
        "native_sparse_probe": meta.get("native_sparse_probe"),
        "summary": meta.get("summary"),
    }


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


def _spec_present(module: str) -> bool:
    """Return whether *module* is importable, tolerating halted imports."""
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # A poisoned sys.modules entry (``sys.modules["x"] = None``) makes
        # find_spec raise; the module is not usable either way.
        return False


def availability(name: str) -> str:
    """Classify the installation state of backend *name* generically.

    Returns:
        - ``"unknown"`` — not registered;
        - ``"absent"`` — no declared required package present;
        - ``"partial"`` — some required packages present, some absent;
        - ``"broken"`` — all required packages importable but the factory
          module raises on import;
        - ``"available"`` — the factory resolves.
    """
    if name not in _registry:
        return "unknown"
    requires = _metadata.get(name, {}).get("requires", {})
    present = [_spec_present(module) for module in requires]
    if not all(present):
        return "partial" if any(present) else "absent"
    try:
        get(name)
    except Exception:  # noqa: BLE001 - any import failure is a broken install
        return "broken"
    return "available"


def verify_available(name: str) -> Callable[..., Any]:
    """Return the factory for *name* or raise a generic actionable error.

    Unknown names raise ``KeyError``; absent/partial/broken installs raise
    ``ImportError`` naming the backend, its required packages, the
    optional extra, and installation guidance. A broken install retains
    the original import exception as ``__cause__`` (task 3.2).
    """
    if name not in _registry:
        raise KeyError(f"Unknown vector store {name!r}. Available: {sorted(_registry)}")
    status = availability(name)
    if status == "available":
        return get(name)
    meta = _metadata.get(name, {})
    requires = meta.get("requires", {})
    details = (
        ", ".join(f"{module} ({dist})" for module, dist in requires.items())
        or "no declared required packages"
    )
    extra = meta.get("extra")
    hint = meta.get("install_hint")
    extra_note = f" via the {extra!r} extra" if extra else ""
    hint_note = f" {hint}" if hint else ""
    cause = None
    if status == "broken":
        # Re-attempt the import so the real cause can be chained.
        try:
            get(name)
        except Exception as exc:  # noqa: BLE001 - chain the original
            cause = exc
    raise ImportError(
        f"Vector store {name!r} is unavailable: {status} installation."
        f"{extra_note} Required packages: {details}.{hint_note}"
    ) from cause


def available() -> list[str]:
    """Return the sorted list of registered backend names."""
    return sorted(_registry)


# ── Built-in backend registrations ────────────────────────────────────

register(
    "chroma",
    "rag_mcp.core.vectordb.chroma:build_vector_store_from_settings",
    requires={
        "chromadb": "chromadb",
        "llama_index.vector_stores.chroma": "llama-index-vector-stores-chroma",
    },
    extra="chroma",
    install_hint=(
        'uv sync --extra chroma (source checkout) or pip install "rag-mcp[chroma]" (packaged)'
    ),
    native_sparse_probe=True,
    summary="rag_mcp.core.vectordb.summary:chroma_storage_summary",
)
register(
    "lancedb",
    "rag_mcp.core.vectordb.lancedb:build_vector_store_from_settings",
    requires={"lancedb": "lancedb"},
    extra=None,
    native_sparse_probe=None,
    summary="rag_mcp.core.vectordb.summary:lancedb_storage_summary",
)
