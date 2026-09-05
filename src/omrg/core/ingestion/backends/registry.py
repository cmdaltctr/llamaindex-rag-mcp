"""Lazy registry for document-backend strategies.

Maps ``DOCUMENT_BACKEND`` names to ``"module:attr"`` import strings
resolved on first ``get()`` (shared registry contract, PROPOSAL §4.4,
modelled on ``core/community/registry.py``).  Importing this module does
NOT import any backend module — backends stay importable on demand.

Each entry carries orchestration metadata (design D1: the registry is a
dispatch table; retry and fallback POLICY lives in
``core/ingestion/backends/orchestrator.py``):

``availability_path``
    ``"module:attr"`` of a zero-argument probe that raises
    ``ImportError`` with an installation instruction when the backend's
    optional dependency is missing.
``fallback``
    Registered name handed the file when this backend is unavailable at
    runtime or its suffix gate excludes the file.
``document_suffixes``
    ``None`` reads every file type; a frozenset restricts the backend
    to those suffixes (the Azure set preserves the chunker's historical
    ``.pdf``/``.docx``/``.doc`` reach).
``structured_output``
    ``True`` when the backend returns pre-structured documents
    (paragraphs/tables) the chunker splits directly, without file-level
    metadata extraction.
``text_format``
    Declared emitted-text format (``"plain"``/``"markdown"``) used for
    Markdown routing (spec pdf-reader: readers declare their emitted text
    format). A STATIC value is definitive (``azure`` emits plain). ``None``
    marks a DYNAMIC declaration resolved at read time from the configured
    PDF reader for ``.pdf`` files and ``plain`` otherwise (the ``local``
    chain delegates to the reader registry).

Adding a backend = one new adapter module + one ``register()`` call at
the bottom of this module.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, str] = {}
_availability: dict[str, str | None] = {}
_cache: dict[str, Callable[..., Any]] = {}
_metadata: dict[str, dict[str, Any]] = {}


def register(
    name: str,
    import_path: str,
    *,
    availability_path: str | None = None,
    fallback: str | None = None,
    document_suffixes: frozenset[str] | None = None,
    structured_output: bool = False,
    text_format: str | None = None,
) -> None:
    """Register a document backend under its configured name.

    Args:
        name: The backend name (e.g. ``"local"``, ``"azure"``).
        import_path: A ``"module:attr"`` string pointing at the async
            reader callable satisfying the ``DocumentBackend`` contract.
        availability_path: Optional ``"module:attr"`` string pointing at
            a zero-argument probe that raises ``ImportError`` when the
            backend's optional dependencies are missing.  Base-install
            backends omit it.
        fallback: Registered name used when this backend fails at
            runtime or its suffix gate excludes the file.
        document_suffixes: File suffixes this backend handles; ``None``
            handles every type.
        structured_output: Whether the backend returns pre-structured
            documents the chunker splits directly.
        text_format: Static declared text format; ``None`` for a dynamic
            declaration resolved from the PDF reader (see module docstring).
    """
    _registry[name] = import_path
    _availability[name] = availability_path
    _metadata[name] = {
        "availability_path": availability_path,
        "fallback": fallback,
        "document_suffixes": document_suffixes,
        "structured_output": structured_output,
        "text_format": text_format,
    }


def describe(name: str) -> dict[str, Any]:
    """Return the orchestration metadata declared for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
    """
    if name not in _registry:
        raise KeyError(f"Unknown document backend {name!r}. Available: {sorted(_registry)}")
    meta = _metadata.get(name, {})
    return {
        "availability_path": meta.get("availability_path"),
        "fallback": meta.get("fallback"),
        "document_suffixes": meta.get("document_suffixes"),
        "structured_output": meta.get("structured_output"),
        "text_format": meta.get("text_format"),
    }


def get(name: str) -> Callable[..., Any]:
    """Resolve and cache the backend callable for *name*.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the backend module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown document backend {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Document backend {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    fn = getattr(mod, attr)
    _cache[name] = fn
    return fn


def available() -> list[str]:
    """Return the sorted list of registered backend names."""
    return sorted(_registry)


def verify_available(name: str) -> None:
    """Fail loudly when *name* needs an optional dependency that is missing.

    Raises:
        KeyError: If *name* is not registered.
        ImportError: When the registered availability probe raises — the
            probe's message carries the installation instruction.

    Backends without a registered probe (base-install implementations)
    pass unconditionally.
    """
    if name not in _registry:
        raise KeyError(f"Unknown document backend {name!r}. Available: {sorted(_registry)}")
    probe_path = _availability.get(name)
    if probe_path is None:
        return
    module_path, attr = probe_path.split(":")
    probe = getattr(importlib.import_module(module_path), attr)
    probe()  # Raises ImportError with the installation instruction.


# ── Built-in backend registrations ──────────────────────────────────
# Local is native (LlamaIndex readers plus the PDF factory) and stays
# the default. Its text format is DYNAMIC: resolved from the configured
# PDF reader for PDFs, plain otherwise (see the module docstring and the
# orchestrator's pre-read resolver). Azure is the optional cloud path
# (ADR-024 cloud opt-in); its SDK import stays inside the adapter, never
# at module load, and it emits plain text (it already sets structured).
register("local", "omrg.core.ingestion.backends.local:read_documents")
register(
    "azure",
    "omrg.integrations.azure:read_documents",
    availability_path="omrg.integrations.azure:require_azure_installed",
    fallback="local",
    document_suffixes=frozenset({".pdf", ".docx", ".doc"}),
    structured_output=True,
    text_format="plain",
)
