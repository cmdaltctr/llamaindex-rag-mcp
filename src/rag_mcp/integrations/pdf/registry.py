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
_probe_modules: dict[str, str] = {}
_cache: dict[str, type[Any]] = {}


def register(name: str, import_path: str, probe_module: str | None = None) -> None:
    """Register a concrete PDF reader class and its dependency probe.

    Args:
        name: Concrete ``PDF_READER`` value.
        import_path: ``"module:ClassName"`` import string.
        probe_module: Importable dependency required by the reader. Defaults
            to the adapter module from ``import_path``.
    """
    _registry[name] = import_path
    _probe_modules[name] = probe_module or import_path.split(":", maxsplit=1)[0]


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


register("pypdf", "rag_mcp.integrations.pdf.pypdf:PyPDFReader", "pypdf")
register("pypdfium2", "rag_mcp.integrations.pdf.pypdfium:PyPDFium2Reader", "pypdfium2")
register("liteparse", "rag_mcp.integrations.pdf.liteparse:LiteParseReader", "liteparse")
register(
    "pdf_inspector",
    "rag_mcp.integrations.pdf.pdf_inspector:PdfInspectorReader",
    "pdf_inspector",
)
