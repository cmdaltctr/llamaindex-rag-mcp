"""Document loading, chunking, and indexing into ChromaDB."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Callable

import chromadb
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY,
    MAGIKA_LABEL_TO_TREESITTER,
    MARKDOWN_CHUNK_SIZE,
    MARKDOWN_HEADING_PREPEND,
    MARKDOWN_MIN_CHUNK_FRACTION,
    SUPPORTED_EXTENSIONS,
    Settings,
)
from .chroma_utils import iter_collection_metadatas

logger = logging.getLogger(__name__)

# ── Thread-safety primitives ─────────────────────────────────────────────
_write_lock = threading.Lock()
_embed_semaphore = threading.BoundedSemaphore(value=EMBED_CONCURRENCY)
_collection_generations: dict[str, int] = {}

# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
_shutdown_requested = threading.Event()


def get_collection_generation(collection_name: str = "documents") -> int:
    """Return the process-local generation counter for a collection."""
    return _collection_generations.get(collection_name, 0)


def _bump_collection_generation(collection_name: str = "documents") -> None:
    """Advance BM25 cache generation; callers hold ``_write_lock``."""
    _collection_generations[collection_name] = (
        _collection_generations.get(collection_name, 0) + 1
    )


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


# ── Async ingestion path ───────────────────────────────────────────────────


def _ensure_heading_metadata(nodes: list) -> None:
    """Defensively copy source heading metadata onto emitted child nodes.

    Experiment 6c recovery hook.  LlamaIndex splitters can emit child nodes
    whose own metadata omits heading information even though their
    ``source_node`` still has it.  This idempotently preserves that metadata
    for evidence/section evaluators and downstream search results.

    Args:
        nodes: Nodes emitted by the Markdown parser / splitter pipeline.
    """
    for node in nodes:
        source_node = getattr(node, "source_node", None)
        source_meta = getattr(source_node, "metadata", {}) if source_node else {}
        header_path = source_meta.get("header_path") or source_meta.get("heading_path")
        if header_path:
            node.metadata.setdefault("header_path", header_path)


def _apply_heading_prepend(nodes: list) -> None:
    """Optionally prepend heading path to Markdown chunk text.

    Experiment 6c recovery knob controlled by ``MARKDOWN_HEADING_PREPEND``.
    Disabled by default.  When enabled, heading context becomes part of the
    embedded text while a double-prepend guard keeps repeated processing safe.

    Args:
        nodes: Markdown nodes after heading metadata propagation.
    """
    if not MARKDOWN_HEADING_PREPEND:
        return
    for node in nodes:
        header_path = node.metadata.get("header_path") or node.metadata.get("heading_path")
        if not header_path:
            continue
        prefix = f"[{header_path}] "
        text = getattr(node, "text", "")
        if text.startswith(prefix):
            continue
        node.text = prefix + text


def _drop_small_markdown_chunks(nodes: list, chunk_size: int) -> list:
    """Optionally drop tiny Markdown chunks before embedding.

    Experiment 6c recovery knob controlled by
    ``MARKDOWN_MIN_CHUNK_FRACTION``.  Disabled by default.  Uses the same
    four-characters-per-token estimate used in the 6b/6c chunk-size reports.

    Args:
        nodes: Markdown nodes to filter.
        chunk_size: Effective Markdown chunk size for this ingestion run.

    Returns:
        The original node list when disabled, otherwise only nodes meeting
        the configured minimum estimated size.
    """
    if MARKDOWN_MIN_CHUNK_FRACTION <= 0:
        return nodes
    min_chars = int(chunk_size * 4 * MARKDOWN_MIN_CHUNK_FRACTION)
    kept = [node for node in nodes if len(getattr(node, "text", "")) >= min_chars]
    dropped = len(nodes) - len(kept)
    if dropped:
        logger.info("Dropped %d Markdown chunk(s) below min-size floor", dropped)
    return kept


async def _chunk_code_file_async(
    file_path: Path,
    language: str,
    chunk_size: int,
    chunk_overlap: int,
    content_type: str,
) -> list:
    """Chunk a code file using LlamaIndex's CodeSplitter.

    Uses tree-sitter function/class boundaries for semantically coherent
    chunks. Falls back to SentenceSplitter if CodeSplitter fails.

    Args:
        file_path: Path to the code file.
        language: Tree-sitter language identifier (e.g., "python").
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        content_type: Magika content-type string for metadata.

    Returns:
        List of LlamaIndex Node objects with content_type metadata.
    """
    from llama_index.core.node_parser import CodeSplitter

    def _read_and_split() -> list:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        splitter = CodeSplitter(
            language=language,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        from llama_index.core import Document
        doc = Document(text=content, metadata={"file_path": str(file_path)})
        return splitter.get_nodes_from_documents([doc])

    try:
        nodes = await asyncio.to_thread(_read_and_split)
    except Exception as exc:
        logger.warning(
            "CodeSplitter failed for %s (language=%s): %s — falling back to SentenceSplitter",
            file_path.name, language, exc,
        )
        # Fall back to SentenceSplitter.
        content = file_path.read_text(encoding="utf-8", errors="replace")
        from llama_index.core import Document
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        doc = Document(text=content, metadata={"file_path": str(file_path)})
        nodes = splitter.get_nodes_from_documents([doc])

    for node in nodes:
        node.metadata.setdefault("content_type", content_type)
        node.metadata.setdefault("file_path", str(file_path))

    return nodes


async def _chunk_config_file_async(
    file_path: Path,
    content_type: str,
) -> list:
    """Chunk a config file as a single whole-file chunk.

    Config files (YAML, JSON, TOML, INI) are small enough to be a single chunk.

    Args:
        file_path: Path to the config file.
        content_type: Magika content-type string for metadata.

    Returns:
        List containing a single LlamaIndex Node with the full file content.
    """
    from llama_index.core import Document
    from llama_index.core.schema import TextNode

    content = file_path.read_text(encoding="utf-8", errors="replace")
    node = TextNode(
        text=content,
        metadata={
            "content_type": content_type,
            "file_path": str(file_path),
            "file_name": file_path.name,
        },
    )
    return [node]


async def _read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    content_type: str | None = None,
) -> list:
    """Async version of ``_read_and_chunk_file``.

    Reads the file via ``asyncio.to_thread`` (sync file readers stay sync),
    calls ``extract_metadata_async`` for non-blocking metadata extraction,
    and returns chunked nodes with metadata attached.

    When ``content_type`` is provided (from Magika detection), the chunking
    strategy is selected based on content type: ``code/*`` uses
    ``CodeSplitter``, ``config/*`` uses whole-file chunking, and documents
    use the existing ``SentenceSplitter`` / ``MarkdownNodeParser`` path.
    When ``content_type`` is None, falls back to extension-based routing.

    Args:
        file_path: Path to the document file.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        content_type: Magika content-type string (e.g., ``"code/python"``).
            When provided, takes precedence over file extension.

    Returns:
        List of LlamaIndex Node objects, each with metadata attached.

    Raises:
        Exception: If the file cannot be read or parsed.
    """
    # Determine chunking strategy based on content_type (task 6.2, 6.6).
    # Content_type takes precedence over extension when available.
    if content_type:
        group, _, label = content_type.partition("/")
    else:
        group, label = "", ""

    # Code files: use CodeSplitter with tree-sitter boundaries.
    if group == "code":
        ts_lang = MAGIKA_LABEL_TO_TREESITTER.get(label)
        if ts_lang:
            return await _chunk_code_file_async(
                file_path, ts_lang, chunk_size, chunk_overlap, content_type,
            )
        # Unknown code language — fall through to default splitter.
        logger.debug("No CodeSplitter mapping for code language %r", label)

    # Config files: whole-file as single chunk.
    if group == "config":
        return await _chunk_config_file_async(
            file_path, content_type,
        )

    # Documents: existing extension-based routing (task 6.2).
    # Azure Document Intelligence branch (task 7.8).
    if group in ("document", "") and not group == "config":
        from .config import DOCUMENT_BACKEND
        if DOCUMENT_BACKEND == "azure" and file_path.suffix.lower() in {".pdf", ".docx", ".doc"}:
            try:
                from .azure_reader import read_with_azure_fallback
                documents = await read_with_azure_fallback(file_path)
                # Add content_type metadata to Azure documents.
                if content_type:
                    for doc in documents:
                        doc.metadata.setdefault("content_type", content_type)
                # Chunk Azure documents with SentenceSplitter.
                effective_chunk_size = MARKDOWN_CHUNK_SIZE if file_path.suffix.lower() == ".md" else chunk_size
                splitter = SentenceSplitter(
                    chunk_size=effective_chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                nodes = await asyncio.to_thread(
                    lambda: splitter.get_nodes_from_documents(documents)
                )
                if content_type:
                    for node in nodes:
                        node.metadata.setdefault("content_type", content_type)
                return nodes
            except Exception as exc:
                logger.warning(
                    "Azure reader failed for %s: %s — falling back to local chain",
                    file_path.name, exc,
                )

    def _read_sync() -> list:
        from .readers import get_pdf_reader

        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
            file_extractor={".pdf": get_pdf_reader()},
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

    # Markdown files use a heading-aware parser chained with the sentence
    # splitter so heading boundaries are preserved wherever the
    # heading-bounded section fits in ``chunk_size``, while longer
    # sections are still split so no chunk exceeds ``chunk_size``.
    # See ADR-016 / OpenSpec change ``rag-retrieval-quality-improvements``
    # Decision 1.  Non-Markdown files retain the existing splitter.
    is_markdown = file_path.suffix.lower() == ".md"
    effective_chunk_size = MARKDOWN_CHUNK_SIZE if is_markdown else chunk_size
    splitter = SentenceSplitter(
        chunk_size=effective_chunk_size,
        chunk_overlap=chunk_overlap,
    )

    def _split_sync() -> list:
        if is_markdown:
            md_parser = MarkdownNodeParser()
            heading_nodes = md_parser.get_nodes_from_documents(documents)
            return splitter.get_nodes_from_documents(heading_nodes)
        return splitter.get_nodes_from_documents(documents)

    # Chunk splitting is CPU-bound and synchronous — offload to a worker
    # thread so the MCP event loop stays responsive while large documents
    # are split.  See ADR-015 / OpenSpec change
    # ``rag-reliability-correctness-fixes`` Decision 1.
    nodes = await asyncio.to_thread(_split_sync)

    if is_markdown:
        _ensure_heading_metadata(nodes)
        _apply_heading_prepend(nodes)
        nodes = _drop_small_markdown_chunks(nodes, effective_chunk_size)

    # Add content_type metadata to all nodes (task 6.4).
    if content_type:
        for node in nodes:
            node.metadata.setdefault("content_type", content_type)

    if doc_metadata:
        flat_metadata = {
            k: ", ".join(str(x) for x in v) if isinstance(v, list) else v
            for k, v in doc_metadata.items()
        }
        for node in nodes:
            node.metadata.update(flat_metadata)

    return nodes


async def read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    content_type: str | None = None,
) -> list:
    """Read and chunk a file for internal ingestion and benchmark callers.

    This is an internal-supported helper shared with the benchmark CLI so
    cross-module usage does not depend on an underscored private function. It
    is not a stable external public API and may change between minor releases.
    """
    return await _read_and_chunk_file_async(
        file_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        content_type=content_type,
    )


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
                _bump_collection_generation(collection_name)
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

    # Type-aware ingestion: detect file types via Magika (task 6.3).
    # Falls back to None (extension-based routing) when Magika unavailable.
    from .codebase_map import detect_file_types

    content_type_map: dict[str, str] = {}
    try:
        inventory = detect_file_types(str(path_obj))
        for entry in inventory.entries:
            ct = f"{entry.group}/{entry.label}"
            content_type_map[entry.path] = ct
    except Exception as exc:
        logger.warning("Magika detection failed, using extension-based routing: %s", exc)

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

        # Determine content_type for this file (task 6.3, 6.7).
        try:
            rel_path = str(file_path.relative_to(path_obj))
        except ValueError:
            rel_path = str(file_path)
        content_type = content_type_map.get(rel_path)

        # Skip binary files (task 6.5).
        if content_type and content_type.startswith("binary"):
            file_details.append(_make_file_detail(
                file_name=file_path.name,
                status="skipped",
                chunks=0,
            ))
            logger.info("⊘ %s — binary file skipped", file_path.name)
            if progress_callback:
                progress_callback("read", i + 1, len(files_to_index))
            continue

        try:
            nodes = await _read_and_chunk_file_async(
                file_path,
                chunk_size=_chunk_size,
                chunk_overlap=_chunk_overlap,
                content_type=content_type,
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


def preview_delete(
    *,
    path: str | None = None,
    metadata_filter: dict | None = None,
    collection_name: str = "documents",
) -> dict:
    """Preview a delete operation without modifying ChromaDB.

    Supports the three delete modes used by the CLI and MCP tool:
    deleting chunks for a source file path, deleting chunks matching a
    metadata filter, or dropping an entire collection. Missing collections
    intentionally preview as ``would_delete: 0`` to preserve existing dry-run
    behavior.

    Args:
        path: Source file path used as ``file_path`` metadata. Mutually
            exclusive with ``metadata_filter``.
        metadata_filter: ChromaDB-compatible ``where`` clause. Mutually
            exclusive with ``path``.
        collection_name: ChromaDB collection to preview against.

    Returns:
        Dict with keys ``status``, ``dry_run``, ``mode``, ``collection``, and
        ``would_delete``. On invalid input, returns ``status: error``.
    """
    if path is not None and metadata_filter is not None:
        return {
            "status": "error",
            "message": "path and metadata_filter are mutually exclusive.",
            "dry_run": True,
            "collection": collection_name,
            "would_delete": 0,
        }

    if path is not None:
        mode = "path"
        where = {"file_path": str(path)}
    elif metadata_filter is not None:
        mode = "metadata"
        where = metadata_filter
    else:
        mode = "collection"
        where = None

    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(collection_name)
        count = collection.count() if where is None else _count_chunks(
            collection, where,
        )
    except Exception:
        count = 0

    return {
        "status": "ok",
        "dry_run": True,
        "mode": mode,
        "collection": collection_name,
        "would_delete": count,
    }


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
            with _write_lock:
                collection.delete(where=where)
                _bump_collection_generation(collection_name)
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
            with _write_lock:
                collection.delete(where=metadata_filter)
                _bump_collection_generation(collection_name)
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
        with _write_lock:
            db.delete_collection(collection_name)
            _bump_collection_generation(collection_name)
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
