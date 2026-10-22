"""Chunking strategy subpackage.

Provides the four chunking strategies (code, markdown, sentence, config)
used by the ingestion pipeline.  Extracted from the original
``ingestion.py`` monolith as part of Phase 1.

Strategy modules are imported **lazily** (PEP 562 ``__getattr__``) so
that importing this package never eagerly imports a strategy module —
mirrors the lazy-registry contract (PROPOSAL §4.4) and keeps the
config/compose/DI layering free of import cycles.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "chunk_code_file_async",
    "chunk_config_file",
    "chunk_sentence_file_async",
    "ensure_heading_metadata",
    "apply_heading_prepend",
    "drop_small_markdown_chunks",
]

# Legacy name -> owning submodule (imported on demand).
_NAMES: dict[str, str] = {
    "chunk_code_file_async": ".code",
    "chunk_config_file": ".config_file",
    "chunk_sentence_file_async": ".sentence",
    "ensure_heading_metadata": ".markdown",
    "apply_heading_prepend": ".markdown",
    "drop_small_markdown_chunks": ".markdown",
}


def __getattr__(name: str) -> Any:
    """Resolve a lazily-imported strategy name (PEP 562)."""
    if name in _NAMES:
        import importlib

        module = importlib.import_module(_NAMES[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
