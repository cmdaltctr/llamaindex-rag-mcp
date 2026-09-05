"""Lazy registry for vector-store backends.

Maps ``VECTOR_STORE`` names to ``"module:attr"`` import strings resolved
on first ``get()``. Importing this module does NOT import any concrete
store module (shared registry contract, PROPOSAL 4.4) - the pattern
established by ``core/retrieval/registry.py``.

``compose.build_vector_store`` resolves the configured name through
this registry instead of branching over it (architecture invariant
#10). Adding a backend = one new module implementing the
:class:`VectorStore` ABC plus one ``register()`` call below.

Each entry carries optional-backend availability metadata (task 3.1,
design D4): the required import modules and their distributions, the
optional-extra name, backend-specific installation guidance, and a
sparse-capability probe marker. ``availability()``/``verify_available()``
distinguish unknown, absent, partial and broken installs generically -
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
    cross_process_writes_safe: bool = False,
) -> None:
    """Register a vector-store backend."""
    _registry[name] = import_path
    _metadata[name] = {
        "requires": dict(requires or {}),
        "extra": extra,
        "install_hint": install_hint,
        "native_sparse_probe": native_sparse_probe,
        "summary": summary,
        # Whether concurrent writers in SEPARATE processes are isolated
        # (serialised) by the backend itself. Drives the installer's
        # adapter-conditional contention warning (login-watcher design).
        "cross_process_writes_safe": cross_process_writes_safe,
    }


def describe(name: str) -> dict[str, Any]:
    """Return the availability metadata declared for *name*."""
    if name not in _registry:
        raise KeyError(f"Unknown vector store {name!r}. Available: {sorted(_registry)}")
    meta = _metadata.get(name, {})
    return {
        "requires": dict(meta.get("requires", {})),
        "extra": meta.get("extra"),
        "install_hint": meta.get("install_hint"),
        "native_sparse_probe": meta.get("native_sparse_probe"),
        "summary": meta.get("summary"),
        "cross_process_writes_safe": meta.get("cross_process_writes_safe", False),
    }


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the backend factory for *name*."""
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
    """Return whether *module* is discoverable, tolerating halted imports."""
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _availability(name: str) -> tuple[str, BaseException | None]:
    """Return installation status plus the original cause for broken installs."""
    if name not in _registry:
        return "unknown", None

    requires = _metadata.get(name, {}).get("requires", {})
    present = [_spec_present(module) for module in requires]
    if not all(present):
        return ("partial" if any(present) else "absent"), None

    # A discoverable package can still be broken at import time. Import each
    # declared requirement for the selected backend so partial/broken installs
    # fail before the project factory is handed to composition (task 3.2).
    for module in requires:
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - preserve the real import cause
            return "broken", exc

    try:
        get(name)
    except Exception as exc:  # noqa: BLE001 - preserve the real factory cause
        return "broken", exc
    return "available", None


def availability(name: str) -> str:
    """Classify backend installation as unknown/absent/partial/broken/available."""
    status, _ = _availability(name)
    return status


def verify_available(name: str) -> Callable[..., Any]:
    """Return the factory or raise an actionable availability error.

    Broken installs retain the original dependency/factory import exception
    as ``__cause__`` (task 3.2).
    """
    if name not in _registry:
        raise KeyError(f"Unknown vector store {name!r}. Available: {sorted(_registry)}")
    status, cause = _availability(name)
    if status == "available":
        return get(name)
    meta = _metadata.get(name, {})
    requires = meta.get("requires", {})
    missing = {module: dist for module, dist in requires.items() if not _spec_present(module)}
    diagnostic_packages = missing or requires
    package_label = "Missing packages" if missing else "Required packages"
    details = (
        ", ".join(f"{module} ({dist})" for module, dist in diagnostic_packages.items())
        or "no declared required packages"
    )
    extra = meta.get("extra")
    hint = meta.get("install_hint")
    extra_note = f" via the {extra!r} extra" if extra else ""
    if hint:
        guidance = hint
    elif extra:
        guidance = f"Install the {extra!r} extra."
    else:
        guidance = ""
    guidance_note = f" {guidance}" if guidance else ""
    raise ImportError(
        f"Vector store {name!r} is unavailable: {status} installation."
        f"{extra_note} {package_label}: {details}.{guidance_note}"
    ) from cause


def available() -> list[str]:
    """Return the sorted list of registered backend names."""
    return sorted(_registry)


register(
    "chroma",
    "omrg.core.vectordb.chroma:build_vector_store_from_settings",
    requires={
        "chromadb": "chromadb",
        "llama_index.vector_stores.chroma": "llama-index-vector-stores-chroma",
    },
    extra="chroma",
    install_hint=(
        "Supported default: lancedb. Install Chroma with "
        'uv sync --extra chroma (source checkout) or pip install "omrg[chroma]" (packaged).'
    ),
    # Native sparse is out of scope while the runtime is quarantined
    # behind the chroma extra (ADR-049); a later Chroma adapter could
    # register a real probe here without pipeline changes.
    native_sparse_probe=None,
    summary="omrg.core.vectordb.summary:chroma_storage_summary",
)
register(
    "lancedb",
    "omrg.core.vectordb.lancedb:build_vector_store_from_settings",
    requires={"lancedb": "lancedb"},
    extra=None,
    # Real native-FTS capability probe (task 3.2,
    # implement-native-sparse-backend-strategy): the composition root
    # resolves this import string lazily and asks the installed runtime
    # whether the pinned FTS surface is present — replacing the
    # Chroma-specific detect_native_sparse_capability route.
    native_sparse_probe="omrg.core.vectordb.lance_fts:probe_native_fts",
    summary="omrg.core.vectordb.summary:lancedb_storage_summary",
    # Cross-process concurrent writes are UNVERIFIED for both backends.
    # No backend may claim safety without a two-process, two-collection
    # concurrent-write experiment (add-per-collection-persist-dirs).
)
