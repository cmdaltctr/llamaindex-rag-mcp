"""Document loading, chunking, and indexing into ChromaDB."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import chromadb
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY,
    SUPPORTED_EXTENSIONS,
    Settings,
)

logger = logging.getLogger(__name__)

# ── Thread-safety primitives ─────────────────────────────────────────────
_write_lock = threading.Lock()
_embed_semaphore = threading.BoundedSemaphore(value=EMBED_CONCURRENCY)

# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
_shutdown_requested = threading.Event()


def _make_file_detail(
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


def _get_chroma_collection(
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


def _gather_supported_files(path_obj: Path) -> tuple[list[Path], list[dict]]:
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
            # Single unsupported file — tracked as skipped
            pass
    else:
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(path_obj.rglob(f"*{ext}"))

        # Discover all files in the directory and identify unsupported ones.
        all_files = {p for p in path_obj.rglob("*") if p.is_file()}
        supported_set = set(files)
        unsupported = sorted(all_files - supported_set, key=lambda p: p.name)
        for f in unsupported:
            skipped.append(_make_file_detail(
                file_name=f.name,
                status="skipped",
                chunks=0,
                error=f"Unsupported extension: {f.suffix}",
            ))
            logger.info("⏭ %s — unsupported extension %s", f.name, f.suffix)

    return files, skipped


def _read_and_chunk_file(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list:
    """Read a single file, extract metadata, and split into LlamaIndex nodes.

    After loading and chunking, calls ``extract_metadata()`` once on the
    full document text and attaches the resulting metadata dict to every
    node's ``.metadata`` field.

    Args:
        file_path: Path to the document file.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of LlamaIndex Node objects, each with metadata attached.

    Raises:
        Exception: If the file cannot be read or parsed.
    """
    reader = SimpleDirectoryReader(
        input_files=[str(file_path)],
        filename_as_id=True,
    )
    documents = reader.load_data()

    # Extract metadata once per file and attach to all chunks.
    from .metadata_extractor import extract_metadata

    if documents:
        file_text = "\n".join(
            d.get_content()
            for d in documents
            if hasattr(d, "get_content")
        )
        doc_metadata = extract_metadata(file_text, file_path.name)
    else:
        doc_metadata = {}
        logger.debug(
            "No documents loaded from %s — skipping metadata extraction",
            file_path.name,
        )

    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = splitter.get_nodes_from_documents(documents)

    # Attach extracted metadata to every node.
    # ChromaDB rejects non-scalar metadata values (list/dict), so flatten
    # any list values (e.g. ``keywords``) into comma-separated strings.
    if doc_metadata:
        flat_metadata = {
            k: ", ".join(str(x) for x in v) if isinstance(v, list) else v
            for k, v in doc_metadata.items()
        }
        for node in nodes:
            node.metadata.update(flat_metadata)

    return nodes



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

    # Fetch everything so we can group by source file.
    # Capped at 10,000 chunks to avoid memory pressure on large collections.
    all_data = collection.get(
        include=["metadatas"], limit=10000,
    )
    source_counts: dict[str, int] = {}
    for meta in all_data["metadatas"]:
        if meta is None:
            continue
        source = meta.get("file_path") or meta.get("file_name") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    return [
        {"source": src, "chunks": cnt}
        for src, cnt in sorted(source_counts.items())
    ]


# ── Async ingestion path ───────────────────────────────────────────────────


async def _read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list:
    """Async version of ``_read_and_chunk_file``.

    Reads the file via ``asyncio.to_thread`` (sync file readers stay sync),
    calls ``extract_metadata_async`` for non-blocking metadata extraction,
    and returns chunked nodes with metadata attached.

    Args:
        file_path: Path to the document file.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of LlamaIndex Node objects, each with metadata attached.

    Raises:
        Exception: If the file cannot be read or parsed.
    """
    def _read_sync() -> list:
        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
        )
        return reader.load_data()

    documents = await asyncio.to_thread(_read_sync)

    from .metadata_extractor import extract_metadata_async

    if documents:
        file_text = "\n".join(
            d.get_content()
            for d in documents
            if hasattr(d, "get_content")
        )
        doc_metadata = await extract_metadata_async(file_text, file_path.name)
    else:
        doc_metadata = {}
        logger.debug(
            "No documents loaded from %s — skipping metadata extraction",
            file_path.name,
        )

    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = splitter.get_nodes_from_documents(documents)

    if doc_metadata:
        flat_metadata = {
            k: ", ".join(str(x) for x in v) if isinstance(v, list) else v
            for k, v in doc_metadata.items()
        }
        for node in nodes:
            node.metadata.update(flat_metadata)

    return nodes


async def _embed_and_write_async(
    nodes: list,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> int:
    """Async version of embed and write to ChromaDB.

    Wraps ChromaDB sync calls in ``asyncio.to_thread`` to yield the
    event loop during writes.

    Args:
        nodes: List of LlamaIndex Node objects.
        progress_callback: Optional callable for progress updates.
        collection_name: ChromaDB collection to write to.

    Returns:
        Number of chunks written.
    """
    if not nodes:
        return 0

    if _shutdown_requested.is_set():
        return 0

    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    def _write_sync() -> int:
        with _write_lock:
            if _shutdown_requested.is_set():
                return 0

            collection = _get_chroma_collection(collection_name)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store
            )

            with _embed_semaphore:
                logger.info(
                    "Embedding %d chunks via %s...",
                    len(nodes),
                    Settings.embed_model.model_name,
                )
                VectorStoreIndex(
                    nodes,
                    storage_context=storage_context,
                    show_progress=False,
                )
                logger.info(
                    "Successfully stored %d chunks in ChromaDB", len(nodes)
                )
            return len(nodes)

    chunks_written = await asyncio.to_thread(_write_sync)

    if progress_callback:
        progress_callback("embed", chunks_written, chunks_written)

    return chunks_written


async def ingest_path_async(
    path: str,
    workers: int = 1,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> dict:
    """Async ingestion entry point — indexes files into ChromaDB.

    Yields the event loop during file I/O, metadata extraction, and
    ChromaDB writes so the MCP server remains responsive.

    Args:
        path: Absolute or relative path to a file or directory.
        workers: Unused (kept for API compatibility).
        chunk_size: Override CHUNK_SIZE for this ingestion.
        chunk_overlap: Override CHUNK_OVERLAP for this ingestion.
        progress_callback: Optional callable ``(phase, current, total)``.
        collection_name: Name of the ChromaDB collection to write to.

    Returns:
        Same dict shape as the former sync ``ingest_path()``.
    """
    _shutdown_requested.clear()

    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        return {
            "status": "error",
            "error_type": "file",
            "message": f"Path not found: {path}",
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
        }

    if path_obj.is_file() and path_obj.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "error_type": "file",
            "message": (
                f"Unsupported file extension: {path_obj.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
            "file_details": [],
            "collection": collection_name,
            "chunks_removed": 0,
        }

    _chunk_size = chunk_size if chunk_size is not None else CHUNK_SIZE
    _chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP
    )

    files_to_index, skipped_details = _gather_supported_files(path_obj)
    if not files_to_index:
        return {
            "status": "ok",
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_removed": 0,
            "file_details": skipped_details,
            "collection": collection_name,
        }

    # Delete old chunks for upsert semantics (via to_thread).
    chunks_removed_total = 0
    for _f in files_to_index:
        if _shutdown_requested.is_set():
            break
        _del_result = await asyncio.to_thread(
            remove_document, str(_f), collection_name
        )
        if _del_result.get("status") == "ok":
            chunks_removed_total += _del_result.get("chunks_removed", 0)

    # Process files sequentially (one at a time per design).
    all_nodes: list = []
    files_indexed = 0
    errors: list[str] = []
    file_details: list[dict] = []

    for i, file_path in enumerate(files_to_index):
        if _shutdown_requested.is_set():
            break
        try:
            nodes = await _read_and_chunk_file_async(
                file_path,
                chunk_size=_chunk_size,
                chunk_overlap=_chunk_overlap,
            )
            all_nodes.extend(nodes)
            files_indexed += 1
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="indexed",
                chunks=len(nodes),
            ))
            logger.info("✓ %s — %d chunk(s)", file_path.name, len(nodes))
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="failed",
                chunks=0,
                error=str(exc),
            ))
            logger.warning("✗ %s — %s", file_path.name, exc)

        if progress_callback:
            progress_callback("read", i + 1, len(files_to_index))

    # Embed and write to ChromaDB (async, yields the loop).
    try:
        chunks_created = await _embed_and_write_async(
            all_nodes, progress_callback, collection_name=collection_name
        )
    except ConnectionError as exc:
        return {
            "status": "error",
            "error_type": "connection",
            "message": str(exc),
            "file_details": file_details + skipped_details,
            "collection": collection_name,
            "chunks_removed": chunks_removed_total,
        }
    except RuntimeError as exc:
        return {
            "status": "error",
            "error_type": "embedding",
            "message": str(exc),
            "file_details": file_details + skipped_details,
            "collection": collection_name,
            "chunks_removed": chunks_removed_total,
        }

    all_details = file_details + skipped_details

    if files_indexed > 0:
        result: dict = {
            "status": "ok",
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "chunks_removed": chunks_removed_total,
            "collection": collection_name,
            "file_details": all_details,
        }
    else:
        result = {
            "status": "error",
            "error_type": "file",
            "message": (
                f"All {len(files_to_index)} file(s) failed to index. "
                "See file_details for per-file errors."
            ),
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_removed": chunks_removed_total,
            "collection": collection_name,
            "file_details": all_details,
        }
    if errors:
        result["warnings"] = errors

    return result


# ── Deletion functions ─────────────────────────────────────────────────────


def _count_chunks(
    collection: chromadb.Collection,
    where: dict,
) -> int:
    """Count chunks matching a ChromaDB ``where`` filter.

    Args:
        collection: A ChromaDB collection object.
        where: A ChromaDB-compatible ``where`` clause.

    Returns:
        Number of matching chunks.
    """
    result = collection.get(where=where, include=[])
    return len(result.get("ids", []))


def remove_document(
    file_path: str,
    collection_name: str = "documents",
) -> dict:
    """Remove all chunks for a source file from the vector store.

    Idempotent — calling this on a file with no indexed chunks returns
    ``chunks_removed: 0``.

    Args:
        file_path: The source file path used as ``file_path`` metadata.
        collection_name: ChromaDB collection to delete from
            (default ``"documents"``).

    Returns:
        Dict with keys ``status``, ``chunks_removed``, and ``collection``.
        On error, includes ``message``.
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    where = {"file_path": file_path}
    try:
        chunks_removed = _count_chunks(collection, where)
        if chunks_removed > 0:
            collection.delete(where=where)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete chunks for '{file_path}': {exc}",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    logger.info(
        "Removed %d chunk(s) for %s from '%s'",
        chunks_removed,
        file_path,
        collection_name,
    )
    return {
        "status": "ok",
        "chunks_removed": chunks_removed,
        "collection": collection_name,
    }


def remove_by_metadata(
    metadata_filter: dict,
    collection_name: str = "documents",
) -> dict:
    """Remove all chunks matching an arbitrary metadata filter.

    Args:
        metadata_filter: A ChromaDB-compatible ``where`` clause.
        collection_name: ChromaDB collection to delete from
            (default ``"documents"``).

    Returns:
        Dict with keys ``status``, ``chunks_removed``, and ``collection``.
        On error, includes ``message``.
    """
    if not metadata_filter:
        return {
            "status": "error",
            "message": "Empty metadata filter is not allowed.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return {
            "status": "error",
            "message": f"Collection '{collection_name}' does not exist.",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    try:
        chunks_removed = _count_chunks(collection, metadata_filter)
        if chunks_removed > 0:
            collection.delete(where=metadata_filter)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete chunks matching filter: {exc}",
            "chunks_removed": 0,
            "collection": collection_name,
        }

    logger.info(
        "Removed %d chunk(s) matching filter from '%s'",
        chunks_removed,
        collection_name,
    )
    return {
        "status": "ok",
        "chunks_removed": chunks_removed,
        "collection": collection_name,
    }


def remove_collection(
    collection_name: str,
) -> dict:
    """Permanently delete an entire ChromaDB collection.

    Args:
        collection_name: Name of the collection to drop.

    Returns:
        Dict with keys ``status`` and ``collection``.
        On error, includes ``message``.
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        db.delete_collection(collection_name)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to delete collection '{collection_name}': {exc}",
            "collection": collection_name,
        }

    logger.info("Dropped collection '%s'", collection_name)
    return {
        "status": "ok",
        "collection": collection_name,
    }
