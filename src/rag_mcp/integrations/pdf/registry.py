"""Lazy registry for concrete PDF reader adapters.

``auto`` is deliberately absent: it is a capability-resolution policy owned
by ``compose.resolve_pdf_reader`` and :mod:`integrations.pdf.factory`, not a
reader implementation.  The three concrete values accepted by
``PDF_READER`` resolve through this registry and share the ``load_data``
contract expected by LlamaIndex's ``SimpleDirectoryReader``.

Each entry carries its declared metadata (spec pdf-reader: "Readers declare
their emitted text format"): ``text_format`` (what the reader emits —
downstream consumers route on it instead of inferring format from the
source extension) and ``page_provenance`` (whether the reader can observe
page boundaries). Inspect them with :func:`describe`.

Importing this module does NOT import any adapter or optional dependency.
"""

from __future__ import annotations

import importlib
from typing import Any, Literal

#: The text format a reader declares for its emitted documents
#: (spec pdf-reader: "Readers declare their emitted text format").
#: Downstream consumers route on this declaration instead of inferring
#: format from the source file's extension.
TextFormat = Literal["plain", "markdown"]

_registry: dict[str, str] = {}
_probe_modules: dict[str, str] = {}
_text_formats: dict[str, TextFormat] = {}
_page_provenance: dict[str, bool] = {}
_cache: dict[str, type[Any]] = {}


def register(
    name: str,
    import_path: str,
    probe_module: str | None = None,
    *,
    text_format: TextFormat,
    page_provenance: bool,
) -> None:
    """Register a concrete PDF reader class and its dependency probe.

    Args:
        name: Concrete ``PDF_READER`` value.
        import_path: ``"module:ClassName"`` import string.
        probe_module: Importable dependency required by the reader. Defaults
            to the adapter module from ``import_path``.
        text_format: REQUIRED declaration of the emitted text format
            (``"plain"`` or ``"markdown"``). Registration fails without it —
            a new reader must never default silently.
        page_provenance: Whether the reader can observe page boundaries
            (emits ``page_label``); machine-discoverable capability.

    Raises:
        ValueError: If ``text_format`` is not ``"plain"`` or
            ``"markdown"``.
    """
    if text_format not in ("plain", "markdown"):
        raise ValueError(
            f"PDF reader {name!r} declared text_format={text_format!r}; "
            "expected 'plain' or 'markdown'."
        )
    _registry[name] = import_path
    _probe_modules[name] = probe_module or import_path.split(":", maxsplit=1)[0]
    _text_formats[name] = text_format
    _page_provenance[name] = page_provenance


def describe(name: str) -> dict[str, Any]:
    """Return the declared reader metadata for *name*.

    Mirrors the document-backend registry pattern
    (``core/ingestion/backends/registry.py``): the descriptor carries the
    declared ``text_format`` and ``page_provenance`` capability alongside
    the import string and dependency probe.

    Raises:
        KeyError: If *name* is not registered (lists available names).
    """
    if name not in _registry:
        raise KeyError(f"Unknown PDF reader {name!r}. Available: {sorted(_registry)}")
    return {
        "import_path": _registry[name],
        "probe_module": _probe_modules[name],
        "text_format": _text_formats[name],
        "page_provenance": _page_provenance[name],
    }


def get(name: str) -> type[Any]:
    """Resolve and cache the reader class for *name*.

    Args:
        name: Registered concrete reader name.

    Returns:
        Reader adapter class with a ``load_data`` method.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the adapter module cannot be imported.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown PDF reader {name!r}. Available: {sorted(_registry)}")
    module_path, attr = _registry[name].split(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"PDF reader {name!r} could not be imported (module {module_path!r}): {exc}"
        ) from exc
    reader_class = getattr(module, attr)
    _cache[name] = reader_class
    return reader_class


def probe(name: str) -> None:
    """Verify that a registered reader dependency is importable.

    Args:
        name: Concrete ``PDF_READER`` value.

    Raises:
        KeyError: If *name* is not registered.
        ImportError: If the reader dependency is unavailable.
    """
    if name not in _registry:
        raise KeyError(f"Unknown PDF reader {name!r}. Available: {sorted(_registry)}")
    module_name = _probe_modules[name]
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"PDF reader {name!r} dependency {module_name!r} is not importable: {exc}"
        ) from exc


def available() -> list[str]:
    """Return the sorted registered concrete reader names."""
    return sorted(_registry)


register(
    "pypdf",
    "rag_mcp.integrations.pdf.pypdf:PyPDFReader",
    "pypdf",
    text_format="plain",
    page_provenance=True,
)
register(
    "pypdfium2",
    "rag_mcp.integrations.pdf.pypdfium:PyPDFium2Reader",
    "pypdfium2",
    text_format="plain",
    page_provenance=True,
)
register(
    "liteparse",
    "rag_mcp.integrations.pdf.liteparse:LiteParseReader",
    "liteparse",
    text_format="plain",
    page_provenance=True,
)
register(
    "pdf_inspector",
    "rag_mcp.integrations.pdf.pdf_inspector:PdfInspectorReader",
    "pdf_inspector",
    text_format="markdown",
    page_provenance=False,
)
