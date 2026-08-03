"""Ingestion pipeline subpackage.

Provides the public entry point ``ingest_path_async`` plus file loading,
chunking dispatch, embedding/writing, and deletion operations.  Extracted
from the original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

from ._state import (
    collection_generations,
    embed_semaphore,
    get_collection_generation,
    shutdown_requested,
    write_lock,
)
from .chunker import read_and_chunk_file_async
from .loader import (
    gather_supported_files,
    get_chroma_collection,
    list_documents,
    make_file_detail,
)
from .pipeline import ingest_path_async
from .writer import (
    embed_and_write_async,
    preview_delete,
    remove_by_metadata,
    remove_collection,
    remove_document,
)

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
