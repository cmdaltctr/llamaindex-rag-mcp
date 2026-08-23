"""Lazy registry for concrete PDF reader adapters.

``auto`` is deliberately absent: it is a capability-resolution policy owned
by ``compose.resolve_pdf_reader`` and :mod:`integrations.pdf.factory`, not a
reader implementation.  The three concrete values accepted by
``PDF_READER`` resolve through this registry and share the ``load_data``
contract expected by LlamaIndex's ``SimpleDirectoryReader``.

Importing this module does NOT import any adapter or optional dependency.
"""

from __future__ import annotations

import importlib
from typing import Any

_registry: dict[str, str] = {}
_cache: dict[str, type[Any]] = {}


def register(name: str, import_path: str) -> None:
    """Register a concrete PDF reader class.

    Args:
        name: Concrete ``PDF_READER`` value.
        import_path: ``"module:ClassName"`` import string.
    """
    _registry[name] = import_path


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


def available() -> list[str]:
    """Return the sorted registered concrete reader names."""
    return sorted(_registry)


register("pypdf", "rag_mcp.integrations.pdf.pypdf:PyPDFReader")
register("pypdfium2", "rag_mcp.integrations.pdf.pypdfium:PyPDFium2Reader")
register("liteparse", "rag_mcp.integrations.pdf.liteparse:LiteParseReader")
register("pdf_inspector", "rag_mcp.integrations.pdf.pdf_inspector:PdfInspectorReader")
