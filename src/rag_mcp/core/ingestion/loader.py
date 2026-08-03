"""File gathering and reader dispatch for the ingestion pipeline.

Discovers supported files, identifies skipped (unsupported) files, and
provides the ChromaDB collection accessor.  Extracted from the original
``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb

from ...chroma_utils import iter_collection_metadatas
from ...config import CHROMA_PERSIST_DIR, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


def make_file_detail(
    file_name: str,
    status: str,
    chunks: int,
    error: str = "",
) -> dict:
    """Create a standardised per-file detail dict.

    Args:
        file_name: Name of the file (not full path).
        status: One of ``"indexed"``, ``"failed"``, or ``"skipped"``.
        chunks: Number of chunks produced (0 for failed/skipped).
        error: Error message, present only when status is ``"failed"``.

    Returns:
        A dict with keys ``file``, ``status``, ``chunks``, and optionally
        ``error``.
    """
    detail: dict = {"file": file_name, "status": status, "chunks": chunks}
    if error:
        detail["error"] = error
    return detail


def get_chroma_collection(
    collection_name: str = "documents",
) -> chromadb.Collection:
    """Return (or create) a named ChromaDB collection.

    Args:
        collection_name: Name of the ChromaDB collection.  Defaults to
            ``"documents"`` for backward compatibility.

    Returns:
        The ChromaDB collection object (created if it did not exist).
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return db.get_or_create_collection(collection_name)


def gather_supported_files(path_obj: Path) -> tuple[list[Path], list[dict]]:
    """Discover supported files and identify skipped (unsupported) files.

    Args:
        path_obj: A file or directory path.

    Returns:
        Tuple of (supported files, skipped file details).
        Each skipped entry is a dict with keys ``file``, ``status``,
        ``chunks``, and optionally ``error``.
    """
    files: list[Path] = []
    skipped: list[dict] = []

    if path_obj.is_file():
        if path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path_obj)
    else:
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(path_obj.rglob(f"*{ext}"))

        # Discover all files in the directory and identify unsupported ones.
        all_files = {p for p in path_obj.rglob("*") if p.is_file()}
        supported_set = set(files)
        unsupported = sorted(all_files - supported_set, key=lambda p: p.name)
        for f in unsupported:
            skipped.append(make_file_detail(
                file_name=f.name,
                status="skipped",
                chunks=0,
                error=f"Unsupported extension: {f.suffix}",
            ))
            logger.info("⏭ %s — unsupported extension %s", f.name, f.suffix)

    return files, skipped


def list_documents(collection_name: str = "documents") -> list[dict]:
    """Return unique source file paths and their chunk counts from the index.

    Args:
        collection_name: Name of the ChromaDB collection to query
            (default ``"documents"`` for backward compatibility).

    Returns:
        List of dicts, each with: ``{"source": str, "chunks": int}``.
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return []  # collection hasn't been created yet

    count = collection.count()
    if count == 0:
        return []

    source_counts: dict[str, int] = {}
    for meta in iter_collection_metadatas(collection):
        if meta is None:
            continue
        source = meta.get("file_path") or meta.get("file_name") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    return [
        {"source": src, "chunks": cnt}
        for src, cnt in sorted(source_counts.items())
    ]
