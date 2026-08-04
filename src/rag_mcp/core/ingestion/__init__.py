"""Ingestion pipeline subpackage.

Provides the public entry point ``ingest_path_async`` plus file loading,
chunking dispatch, embedding/writing, and deletion operations.  Extracted
from the original ``ingestion.py`` monolith as part of Phase 1.

Pipeline modules are imported **lazily** (PEP 562 ``__getattr__``) so
that importing this package never eagerly imports a pipeline module —
mirrors the lazy-registry contract (PROPOSAL §4.4) and keeps the
config/compose/DI layering free of import cycles.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ingest_path_async",
    "read_and_chunk_file_async",
    "list_documents",
    "preview_delete",
    "remove_document",
    "remove_by_metadata",
    "remove_collection",
    "get_collection_generation",
]

# Legacy name -> owning submodule (imported on demand).
_NAMES: dict[str, str] = {
    "collection_generations": "._state",
    "embed_semaphore": "._state",
    "get_collection_generation": "._state",
    "shutdown_requested": "._state",
    "write_lock": "._state",
    "read_and_chunk_file_async": ".chunker",
    "gather_supported_files": ".loader",
    "list_documents": ".loader",
    "make_file_detail": ".loader",
    "ingest_path_async": ".pipeline",
    "embed_and_write_async": ".writer",
    "preview_delete": ".writer",
    "remove_by_metadata": ".writer",
    "remove_collection": ".writer",
    "remove_document": ".writer",
}


def __getattr__(name: str) -> Any:
    """Resolve a lazily-imported pipeline name (PEP 562)."""
    if name in _NAMES:
        import importlib

        module = importlib.import_module(_NAMES[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
