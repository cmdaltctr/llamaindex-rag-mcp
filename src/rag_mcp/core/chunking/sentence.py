"""Sentence chunking strategy using LlamaIndex's SentenceSplitter.

Handles both plain-text and Markdown document splitting.  For Markdown,
chains ``MarkdownNodeParser`` with ``SentenceSplitter`` so heading
boundaries are preserved wherever the heading-bounded section fits in
``chunk_size``, while longer sections are still split so no chunk exceeds
``chunk_size`` (ADR-016).  Extracted from the original ``ingestion.py``
monolith as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging

from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter

from ..settings import resolve_effective_settings
from .markdown import (
    apply_heading_prepend,
    drop_small_markdown_chunks,
    ensure_heading_metadata,
)

logger = logging.getLogger(__name__)


def _split_documents_sync(
    documents: list,
    is_markdown: bool,
    chunk_size: int,
    chunk_overlap: int,
) -> list:
    """Synchronous document splitting — called via ``asyncio.to_thread``.

    Args:
        documents: LlamaIndex Document objects.
        is_markdown: Whether to use the Markdown heading-aware parser.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of LlamaIndex Node objects.
    """
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if is_markdown:
        md_parser = MarkdownNodeParser()
        heading_nodes = md_parser.get_nodes_from_documents(documents)
        return splitter.get_nodes_from_documents(heading_nodes)
    return splitter.get_nodes_from_documents(documents)


async def chunk_sentence_file_async(
    documents: list,
    file_path: str,
    is_markdown: bool,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: object | None = None,
) -> list:
    """Chunk documents using SentenceSplitter (and MarkdownNodeParser for .md).

    Args:
        documents: LlamaIndex Document objects from the file reader.
        file_path: Path string (used for logging only).
        is_markdown: Whether to apply the Markdown heading-aware parser
            and post-processing hooks (heading metadata, heading prepend,
            small-chunk dropping).
        chunk_size: Override chunk size.  Defaults to ``MARKDOWN_CHUNK_SIZE``
            for Markdown, ``CHUNK_SIZE`` otherwise.
        chunk_overlap: Override chunk overlap.  Defaults to ``CHUNK_OVERLAP``.

    Returns:
        List of LlamaIndex Node objects.
    """
    resolved = resolve_effective_settings(settings)
    effective_chunk_size = (
        chunk_size
        if chunk_size is not None
        else (
            resolved.chunking.markdown_chunk_size if is_markdown else resolved.chunking.chunk_size
        )
    )
    effective_overlap = (
        chunk_overlap if chunk_overlap is not None else resolved.chunking.chunk_overlap
    )

    nodes = await asyncio.to_thread(
        _split_documents_sync,
        documents,
        is_markdown,
        effective_chunk_size,
        effective_overlap,
    )

    if is_markdown:
        ensure_heading_metadata(nodes)
        apply_heading_prepend(nodes)
        nodes = drop_small_markdown_chunks(nodes, effective_chunk_size)

    return nodes
