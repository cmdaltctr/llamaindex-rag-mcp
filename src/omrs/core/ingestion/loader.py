"""File gathering and reader dispatch for the ingestion pipeline.

Discovers supported files, identifies skipped (unsupported) files, and
provides the document-listing accessor.  Extracted from the original
``ingestion.py`` monolith as part of Phase 1; rewired through the
vector store ABC in Phase 3.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from .settings import DEFAULT_INGEST_EXTENSIONS
from .source_state import SOURCE_ID_KEY

logger = logging.getLogger(__name__)


# File extensions the ingestion pipeline accepts — the DEFAULT value of
# the profile-scoped ``ingestion.ingest_extensions`` setting (design D4:
# the set resolves from the active profile, not from this global). Kept as
# a module constant for callers without resolved settings (the watcher's
# fallback, historical imports) and as ``gather_supported_files``'s
# default argument. Derives from the settings-model default so the two
# cannot drift.
SUPPORTED_EXTENSIONS = set(DEFAULT_INGEST_EXTENSIONS)


def make_file_detail(
    file_name: str,
    status: str,
    chunks: int,
    error: str = "",
    metadata_degraded: bool = False,
) -> dict:
    """Create a standardised per-file detail dict.

    Args:
        file_name: Name of the file (not full path).
        status: One of ``"indexed"``, ``"failed"``, or ``"skipped"``.
        chunks: Number of chunks produced (0 for failed/skipped).
        error: Error message, present only when status is ``"failed"``.
        metadata_degraded: Whether this file's metadata was produced by a
            fallback tier rather than the configured LLM-backed mode. When
            ``False`` (the default), no marker key is added — only
            affected files carry it (fix-silent-metadata-degradation).

    Returns:
        A dict with keys ``file``, ``status``, ``chunks``, and optionally
        ``error`` and ``metadata_degraded``.
    """
    detail: dict = {"file": file_name, "status": status, "chunks": chunks}
    if error:
        detail["error"] = error
    if metadata_degraded:
        detail["metadata_degraded"] = True
    return detail


def gather_supported_files(
    path_obj: Path,
    extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
) -> tuple[list[Path], list[dict]]:
    """Discover supported files and identify skipped (unsupported) files.

    Args:
        path_obj: A file or directory path.
        extensions: The resolved ingestible extension set (design D4).
            Callers with settings MUST pass
            ``resolved.ingestion.ingest_extensions``; the module constant
            default serves only callers without resolved settings.

    Returns:
        Tuple of (supported files, skipped file details).
        Each skipped entry is a dict with keys ``file``, ``status``,
        ``chunks``, and optionally ``error``.
    """
    files: list[Path] = []
    skipped: list[dict] = []
    extension_set = set(extensions)

    if path_obj.is_file():
        if path_obj.suffix.lower() in extension_set:
            files.append(path_obj)
    else:
        for ext in sorted(extension_set):
            files.extend(path_obj.rglob(f"*{ext}"))

        # Discover all files in the directory and identify unsupported ones.
        all_files = {p for p in path_obj.rglob("*") if p.is_file()}
        supported_set = set(files)
        unsupported = sorted(all_files - supported_set, key=lambda p: p.name)
        for f in unsupported:
            skipped.append(
                make_file_detail(
                    file_name=f.name,
                    status="skipped",
                    chunks=0,
                    error=f"Unsupported extension: {f.suffix}",
                )
            )
            logger.info("⏭ %s — unsupported extension %s", f.name, f.suffix)

    return files, skipped


def _is_orphaned(source: str) -> bool | None:
    """Return whether an indexed source is missing on this machine."""
    path = Path(source)
    if not path.is_absolute():
        return None
    return not path.exists()


def list_documents(
    collection_name: str = "documents",
    store: VectorStore | None = None,
) -> list[dict]:
    """Return unique sources, chunk counts, and machine-local orphan status.

    Production-ingested chunks are grouped by their stable ``source_id``
    while the human-readable source path is retained for display. Rows
    without lineage metadata (for example experiment precomputed rows)
    fall back to the legacy ``file_path``/``file_name`` grouping and
    report ``source_id: None``.

    Args:
        collection_name: Name of the collection to query
            (default ``"documents"`` for backward compatibility).
        store: Optional injected :class:`VectorStore`.

    Returns:
        List of dicts, each with: ``{"source": str, "source_id": str | None,
        "chunks": int, "orphaned": bool | None}``. ``orphaned`` means
        missing on this machine and is ``None`` without a local absolute path.
    """
    resolved_store = store if store is not None else get_default_store()

    count = resolved_store.count(collection_name)
    if count == 0:
        return []

    chunk_counts: dict[str, int] = {}
    display_paths: dict[str, str] = {}
    for meta in resolved_store.iter_metadatas(collection_name):
        if meta is None:
            continue
        source_id = meta.get(SOURCE_ID_KEY)
        display = meta.get("file_path") or meta.get("file_name") or "unknown"
        group = source_id if source_id is not None else display
        chunk_counts[group] = chunk_counts.get(group, 0) + 1
        if source_id is not None:
            display_paths.setdefault(group, display)

    documents: list[dict] = []
    for group, chunks in sorted(
        chunk_counts.items(),
        key=lambda item: display_paths.get(item[0], item[0]),
    ):
        source = display_paths.get(group, group)
        documents.append(
            {
                "source": source,
                "source_id": group if group in display_paths else None,
                "chunks": chunks,
                "orphaned": _is_orphaned(source),
            }
        )
    return documents
