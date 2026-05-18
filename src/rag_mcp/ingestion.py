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
    EMBED_CONCURRENCY,
    SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# ── Thread-safety primitives ─────────────────────────────────────────────
_write_lock = threading.Lock()
_embed_semaphore = threading.BoundedSemaphore(value=EMBED_CONCURRENCY)

# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
_shutdown_requested = threading.Event()


def _get_chroma_collection():
    """Return (or create) the ChromaDB collection used for storing vectors."""
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return db.get_or_create_collection(COLLECTION_NAME)


def _gather_supported_files(path_obj: Path) -> list[Path]:
    """Discover all supported files from a path.

    Args:
        path_obj: A file or directory path.

    Returns:
        List of Path objects for supported file types.
    """
    files: list[Path] = []
    if path_obj.is_file():
        if path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path_obj)
    else:
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(path_obj.rglob(f"*{ext}"))
    return files


def _read_and_chunk_file(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list:
    """Read a single file and split it into LlamaIndex nodes.

    Args:
        file_path: Path to the document file.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of LlamaIndex Node objects.

    Raises:
        Exception: If the file cannot be read or parsed.
    """
    reader = SimpleDirectoryReader(
        input_files=[str(file_path)],
        filename_as_id=True,
    )
    documents = reader.load_data()

    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.get_nodes_from_documents(documents)


def _ingest_sequential(
    files: list[Path],
    chunk_size: int,
    chunk_overlap: int,
    progress_callback: Callable | None = None,
) -> tuple[int, int, list[str]]:
    """Ingest files sequentially (single-threaded).

    Args:
        files: List of file paths to ingest.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        progress_callback: Optional callable for progress updates.

    Returns:
        Tuple of (files_indexed, chunks_created, errors).
    """
    all_nodes = []
    files_indexed = 0
    errors: list[str] = []

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
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
            logger.warning("Failed to read %s: %s", file_path, exc)

        if progress_callback:
            progress_callback("read", i + 1, len(files))

    # Embed and write to ChromaDB
    chunks_created = _embed_and_write(all_nodes, progress_callback)
    return files_indexed, chunks_created, errors


def _ingest_parallel(
    files: list[Path],
    workers: int,
    chunk_size: int,
    chunk_overlap: int,
    progress_callback: Callable | None = None,
) -> tuple[int, int, list[str]]:
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

    Returns:
        Tuple of (files_indexed, chunks_created, errors).
    """
    all_nodes = []
    files_indexed = 0
    errors: list[str] = []
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
            try:
                nodes = future.result()
                all_nodes.extend(nodes)
                files_indexed += 1
            except Exception as exc:
                errors.append(f"{file_path.name}: {exc}")
                logger.warning(
                    "Failed to process %s: %s", file_path, exc
                )

            if progress_callback:
                progress_callback("read", completed, len(files))

    # Serial embed + write phase
    chunks_created = _embed_and_write(all_nodes, progress_callback)
    return files_indexed, chunks_created, errors


def _embed_and_write(
    nodes: list,
    progress_callback: Callable | None = None,
) -> int:
    """Embed nodes and write to ChromaDB (serial, behind lock).

    If the shutdown flag is set before embedding begins, returns 0
    immediately to avoid partial writes.  Once VectorStoreIndex
    construction starts, the underlying Ollama call completes before
    the ChromaDB ``add()`` happens — there is no mid-write cancellation.

    Args:
        nodes: List of LlamaIndex Node objects.
        progress_callback: Optional callable for progress updates.

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

        collection = _get_chroma_collection()
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        with _embed_semaphore:
            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                show_progress=False,
            )

        if progress_callback:
            progress_callback("embed", len(nodes), len(nodes))

    return len(nodes)


def ingest_path(
    path: str,
    workers: int = 1,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    progress_callback: Callable | None = None,
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

    Returns:
        A dict with one of two shapes:
        - success: {"status": "ok", "files_indexed": N, "chunks_created": M}
        - error:   {"status": "error", "message": "..."}
    """
    # Reset shutdown flag for fresh run
    _shutdown_requested.clear()

    # Resolve path
    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        return {"status": "error", "message": f"Path not found: {path}"}

    # Single-file unsupported extension check (backward compatible)
    if path_obj.is_file() and path_obj.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "message": (
                f"Unsupported file extension: {path_obj.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        }

    # Apply chunk overrides
    _chunk_size = chunk_size if chunk_size is not None else CHUNK_SIZE
    _chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP
    )

    # Gather supported files
    files_to_index = _gather_supported_files(path_obj)
    if not files_to_index:
        return {
            "status": "ok",
            "files_indexed": 0,
            "chunks_created": 0,
        }

    # Single file — always sequential
    if len(files_to_index) == 1:
        workers = 1

    # Clamp workers
    workers = max(1, workers)

    # Choose ingestion strategy
    if workers > 1:
        files_idx, chunks, errors = _ingest_parallel(
            files_to_index, workers, _chunk_size, _chunk_overlap,
            progress_callback,
        )
    else:
        files_idx, chunks, errors = _ingest_sequential(
            files_to_index, _chunk_size, _chunk_overlap,
            progress_callback,
        )

    result: dict = {
        "status": "ok" if files_idx > 0 else "error",
        "files_indexed": files_idx,
        "chunks_created": chunks,
    }
    if errors:
        result["warnings"] = errors

    return result


def list_documents() -> list[dict]:
    """Return unique source file paths and their chunk counts from the index.

    Each entry: {"source": str, "chunks": int}
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(COLLECTION_NAME)
    except Exception:
        return []  # collection hasn't been created yet

    count = collection.count()
    if count == 0:
        return []

    # Fetch everything so we can group by source file
    all_data = collection.get(include=["metadatas"])
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
