"""Document loading, chunking, and indexing into ChromaDB."""

from __future__ import annotations

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
    if doc_metadata:
        for node in nodes:
            node.metadata.update(doc_metadata)

    return nodes


def _ingest_sequential(
    files: list[Path],
    chunk_size: int,
    chunk_overlap: int,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> tuple[int, int, list[str], list[dict]]:
    """Ingest files sequentially (single-threaded).

    Args:
        files: List of file paths to ingest.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        progress_callback: Optional callable for progress updates.
        collection_name: ChromaDB collection to write to.

    Returns:
        Tuple of (files_indexed, chunks_created, errors, file_details).
        file_details contains per-file dicts with keys: file, status, chunks, error.
    """
    all_nodes = []
    files_indexed = 0
    errors: list[str] = []
    file_details: list[dict] = []

    for i, file_path in enumerate(files):
        if _shutdown_requested.is_set():
            break
        try:
            nodes = _read_and_chunk_file(
                file_path,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            all_nodes.extend(nodes)
            files_indexed += 1
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="indexed",
                chunks=len(nodes),
            ))
            logger.info(
                "✓ %s — %d chunk(s)", file_path.name, len(nodes)
            )
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
            progress_callback("read", i + 1, len(files))

    # Embed and write to ChromaDB
    chunks_created = _embed_and_write(
        all_nodes, progress_callback, collection_name=collection_name
    )
    return files_indexed, chunks_created, errors, file_details


def _ingest_parallel(
    files: list[Path],
    workers: int,
    chunk_size: int,
    chunk_overlap: int,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> tuple[int, int, list[str], list[dict]]:
    """Ingest files using ThreadPoolExecutor for concurrent reading.

    Two-phase pattern:
      Phase 1 (parallel): Read and chunk files concurrently.
      Phase 2 (serial): Embed and write to ChromaDB in one batch.

    Args:
        files: List of file paths to ingest.
        workers: Number of parallel file readers.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        progress_callback: Optional callable for progress updates.
        collection_name: ChromaDB collection to write to.

    Returns:
        Tuple of (files_indexed, chunks_created, errors, file_details).
        file_details contains per-file dicts with keys: file, status, chunks, error.
    """
    all_nodes: list = []
    files_indexed = 0
    errors: list[str] = []
    file_details: list[dict] = []
    completed = 0

    def _process_file(file_path: Path) -> list:
        """Worker function: read and chunk a single file."""
        if _shutdown_requested.is_set():
            return []
        return _read_and_chunk_file(
            file_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _handle_future(
        future,
        file_path: Path,
    ) -> tuple[int, int]:
        """Process a completed future and update tracking collections.

        Args:
            future: Completed future from the thread pool.
            file_path: Path of the file that was processed.

        Returns:
            Tuple of (files_added, errors_added).
        """
        try:
            nodes = future.result()
            all_nodes.extend(nodes)
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="indexed",
                chunks=len(nodes),
            ))
            logger.info("✓ %s — %d chunk(s)", file_path.name, len(nodes))
            return 1, 0
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="failed",
                chunks=0,
                error=str(exc),
            ))
            logger.warning("✗ %s — %s", file_path.name, exc)
            return 0, 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_file = {
            pool.submit(_process_file, f): f for f in files
        }

        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            if _shutdown_requested.is_set():
                pool.shutdown(wait=False, cancel_futures=True)
                break

            completed += 1
            f_added, e_added = _handle_future(future, file_path)
            files_indexed += f_added
            # errors already appended inside _handle_future

            if progress_callback:
                progress_callback("read", completed, len(files))

    # Serial embed + write phase
    chunks_created = _embed_and_write(
        all_nodes, progress_callback, collection_name=collection_name
    )
    return files_indexed, chunks_created, errors, file_details


def _embed_and_write(
    nodes: list,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> int:
    """Embed nodes and write to ChromaDB.

    When ``EMBED_CONCURRENCY <= 1``, uses the original ``VectorStoreIndex``
    path (sequential, backwards compatible).  When ``EMBED_CONCURRENCY > 1``,
    splits nodes into batches of ``EMBED_BATCH_SIZE``, embeds them
    concurrently via ``ThreadPoolExecutor``, and writes to ChromaDB only
    after all batches succeed (all-or-nothing).

    If the shutdown flag is set before embedding begins, returns 0
    immediately to avoid partial writes.

    Args:
        nodes: List of LlamaIndex Node objects.
        progress_callback: Optional callable for progress updates.
        collection_name: ChromaDB collection to write to.

    Returns:
        Number of chunks written.
    """
    if not nodes:
        return 0

    # Bail out before starting the expensive embedding work.
    if _shutdown_requested.is_set():
        return 0

    # Notify caller that embedding is about to begin.
    if progress_callback:
        progress_callback("embed_start", 0, len(nodes))

    with _write_lock:
        # Re-check inside the lock in case SIGINT arrived while
        # we were waiting for the lock.
        if _shutdown_requested.is_set():
            return 0

        collection = _get_chroma_collection(collection_name)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        if EMBED_CONCURRENCY <= 1:
            # Sequential path: original VectorStoreIndex behaviour.
            with _embed_semaphore:
                logger.info(
                    "Embedding %d chunks via %s (sequential)...",
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
        else:
            # Concurrent path: embed batches in parallel, write once.
            _embed_and_write_concurrent(
                nodes, collection, progress_callback
            )

        if progress_callback:
            progress_callback("embed", len(nodes), len(nodes))

    return len(nodes)


def _embed_and_write_concurrent(
    nodes: list,
    collection: chromadb.Collection,
    progress_callback: Callable | None = None,
) -> None:
    """Embed nodes concurrently and write all results to ChromaDB.

    Splits nodes into batches of ``EMBED_BATCH_SIZE`` and dispatches
    them across ``EMBED_CONCURRENCY`` workers.  If any batch fails,
    no data is written to ChromaDB (all-or-nothing).

    Args:
        nodes: List of LlamaIndex Node objects.
        collection: ChromaDB collection to write to.
        progress_callback: Optional callable for progress updates.

    Raises:
        ConnectionError: If any embedding batch fails due to Ollama
            connectivity issues — no data is written to ChromaDB.
        RuntimeError: If any non-connection embedding batch fails —
            no data is written to ChromaDB (all-or-nothing semantics).
    """
    batch_size = max(1, EMBED_BATCH_SIZE)
    node_batches: list[list] = [
        nodes[i : i + batch_size]
        for i in range(0, len(nodes), batch_size)
    ]

    logger.info(
        "Embedding %d chunks via %s (concurrent, %d batch(es), "
        "%d worker(s))...",
        len(nodes),
        Settings.embed_model.model_name,
        len(node_batches),
        EMBED_CONCURRENCY,
    )

    # Collect embeddings for each batch.
    all_embeddings: list[list[float]] = [None] * len(nodes)
    batch_errors: list[str] = []

    def _embed_batch(batch_idx: int, batch: list) -> None:
        """Embed a single batch and store results."""
        texts = [n.get_content() for n in batch]
        embeddings = Settings.embed_model.get_text_embedding_batch(texts)
        start = batch_idx * batch_size
        for j, emb in enumerate(embeddings):
            all_embeddings[start + j] = emb

    with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as pool:
        futures = {
            pool.submit(_embed_batch, i, batch): i
            for i, batch in enumerate(node_batches)
        }
        has_connection_error = False
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                future.result()
            except ConnectionError as exc:
                has_connection_error = True
                batch_errors.append(
                    f"Batch {batch_idx} failed (connection): {exc}"
                )
                logger.error(
                    "Embedding batch %d failed (connection): %s",
                    batch_idx,
                    exc,
                )
            except Exception as exc:
                batch_errors.append(
                    f"Batch {batch_idx} failed: {exc}"
                )
                logger.error("Embedding batch %d failed: %s", batch_idx, exc)

    # All-or-nothing: if any batch failed, abort without writing.
    if batch_errors:
        if has_connection_error:
            raise ConnectionError(
                f"Embedding failed for {len(batch_errors)} batch(es). "
                "No data written to ChromaDB."
            )
        raise RuntimeError(
            f"Embedding failed for {len(batch_errors)} batch(es). "
            "No data written to ChromaDB."
        )

    # Write all nodes with their embeddings to ChromaDB in one go.
    # Build the VectorStoreIndex with pre-embedded nodes so the
    # embedding step is skipped.
    for node, emb in zip(nodes, all_embeddings):
        node.embedding = emb

    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        show_progress=False,
    )
    logger.info(
        "Successfully stored %d chunks in ChromaDB (concurrent)", len(nodes)
    )


def ingest_path(
    path: str,
    workers: int = 1,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    progress_callback: Callable | None = None,
    collection_name: str = "documents",
) -> dict:
    """Index a single file or an entire directory into the RAG vector store.

    Args:
        path: Absolute or relative path to a file or directory.
        workers: Number of parallel file readers (default 1 = sequential).
        chunk_size: Override CHUNK_SIZE for this ingestion.
        chunk_overlap: Override CHUNK_OVERLAP for this ingestion.
        progress_callback: Optional callable ``(phase, current, total)``
            for progress reporting.  *phase* is one of ``"read"``,
            ``"embed_start"``, or ``"embed"``.
        collection_name: Name of the ChromaDB collection to write to
            (default ``"documents"`` for backward compatibility).

    Returns:
        A dict with keys:
        - ``status``: ``"ok"`` or ``"error"``
        - ``files_indexed``: Number of files successfully indexed
        - ``chunks_created``: Total chunks written to ChromaDB
        - ``collection``: Name of the collection used
        - ``file_details``: List of per-file dicts with keys ``file``,
          ``status`` (indexed/failed/skipped), ``chunks``, and optional
          ``error``
        - ``warnings``: (optional) List of error strings

        On error, also includes:
        - ``error_type``: One of ``"file"`` (path/extension errors or all files
          failed), ``"connection"`` (Ollama connectivity failure), or
          ``"embedding"`` (non-connection embedding failure)
        - ``message``: Human-readable error description
    """
    # Reset shutdown flag for fresh run
    _shutdown_requested.clear()

    # Resolve path
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

    # Single-file unsupported extension check (backwards compatible)
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

    # Apply chunk overrides
    _chunk_size = chunk_size if chunk_size is not None else CHUNK_SIZE
    _chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP
    )

    # Gather supported files (and track skipped unsupported files)
    files_to_index, skipped_details = _gather_supported_files(path_obj)
    if not files_to_index:
        result: dict = {
            "status": "ok",
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_removed": 0,
            "file_details": skipped_details,
            "collection": collection_name,
        }
        return result

    # Delete old chunks for upsert semantics (delete-before-read).
    # Re-ingesting a file replaces old chunks rather than appending duplicates.
    # This runs single-threaded before the parallel read phase to avoid
    # concurrent ChromaDB access issues.
    chunks_removed_total = 0
    for _f in files_to_index:
        if _shutdown_requested.is_set():
            break
        _del_result = remove_document(
            str(_f), collection_name=collection_name
        )
        if _del_result.get("status") == "ok":
            chunks_removed_total += _del_result.get("chunks_removed", 0)

    # Single file — always sequential
    if len(files_to_index) == 1:
        workers = 1

    # Clamp workers
    workers = max(1, workers)

    # Choose ingestion strategy
    file_details: list[dict] = []
    try:
        if workers > 1:
            files_idx, chunks, errors, file_details = _ingest_parallel(
                files_to_index, workers, _chunk_size, _chunk_overlap,
                progress_callback, collection_name=collection_name,
            )
        else:
            files_idx, chunks, errors, file_details = _ingest_sequential(
                files_to_index, _chunk_size, _chunk_overlap,
                progress_callback, collection_name=collection_name,
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

    # Merge skipped files into file_details for a complete picture
    all_details = file_details + skipped_details

    if files_idx > 0:
        result: dict = {
            "status": "ok",
            "files_indexed": files_idx,
            "chunks_created": chunks,
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
