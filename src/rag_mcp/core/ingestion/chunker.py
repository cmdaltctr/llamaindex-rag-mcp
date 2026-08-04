"""Content-type → chunking strategy dispatch.

Reads files via LlamaIndex's ``SimpleDirectoryReader``, extracts metadata,
and dispatches to the appropriate chunking strategy based on Magika
content-type detection.  Content-type takes precedence over file extension
when available.  Extracted from the original ``ingestion.py`` monolith as
part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

from ...config import settings, MAGIKA_LABEL_TO_TREESITTER

# Kept as module-level alias so existing tests that monkeypatch
# ``MARKDOWN_CHUNK_SIZE`` continue to work; value sourced from settings.
MARKDOWN_CHUNK_SIZE = settings.markdown_chunk_size

from ..chunking.code import chunk_code_file_async
from ..chunking.config_file import chunk_config_file
from ..chunking.markdown import (
    apply_heading_prepend,
    drop_small_markdown_chunks,
    ensure_heading_metadata,
)
from ..chunking.sentence import _split_documents_sync

logger = logging.getLogger(__name__)


async def read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    content_type: str | None = None,
) -> list:
    """Read and chunk a file, dispatching strategy based on content_type.

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
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = settings.chunk_overlap

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
            return await chunk_code_file_async(
                file_path, ts_lang, chunk_size, chunk_overlap, content_type,
            )
        # Unknown code language — fall through to default splitter.
        logger.debug("No CodeSplitter mapping for code language %r", label)

    # Config files: whole-file as single chunk.
    if group == "config":
        return chunk_config_file(
            file_path, content_type,
        )

    # Documents: existing extension-based routing (task 6.2).
    # Azure Document Intelligence branch (task 7.8).
    if group in ("document", "") and group != "config":
        if settings.document_backend == "azure" and file_path.suffix.lower() in {".pdf", ".docx", ".doc"}:
            try:
                from ...azure_reader import read_with_azure_fallback
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
        from ...readers import get_pdf_reader

        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
            file_extractor={".pdf": get_pdf_reader()},
        )
        return reader.load_data()

    documents = await asyncio.to_thread(_read_sync)

    from ..metadata.extractor import extract_metadata_async

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

    # Chunk splitting is CPU-bound and synchronous — offload to a worker
    # thread so the MCP event loop stays responsive while large documents
    # are split.  See ADR-015 / OpenSpec change
    # ``rag-reliability-correctness-fixes`` Decision 1.
    nodes = await asyncio.to_thread(
        _split_documents_sync,
        documents,
        is_markdown,
        effective_chunk_size,
        chunk_overlap,
    )

    if is_markdown:
        ensure_heading_metadata(nodes)
        apply_heading_prepend(nodes)
        nodes = drop_small_markdown_chunks(nodes, effective_chunk_size)

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
