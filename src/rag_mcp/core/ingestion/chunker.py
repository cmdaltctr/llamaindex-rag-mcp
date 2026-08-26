"""Content-type → chunking strategy dispatch.

Reads files via the registry-backed document backends
(``core/ingestion/backends/``), extracts metadata, and dispatches to the
appropriate chunking strategy based on Magika content-type detection.
Content-type takes precedence over file extension when available.
Extracted from the original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from llama_index.core.node_parser import SentenceSplitter

from ..chunking.registry import get as _chunking_get
from ..codebase.ast_extract import MAGIKA_LABEL_TO_TREESITTER
from ..settings import resolve_effective_settings
from .backends import read_document

logger = logging.getLogger(__name__)


class _ChunkResult(list):
    """List of chunked nodes that also carries a metadata-degradation flag."""

    def __init__(self, nodes=(), *, metadata_degraded: bool = False) -> None:
        super().__init__(nodes)
        self.metadata_degraded = metadata_degraded


async def read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    content_type: str | None = None,
    fallback_strategy: str | None = None,
    taxonomy_mode: str | None = None,
    settings: Any = None,
) -> list:
    """Read and chunk a file, dispatching strategy based on content_type.

    ``chunk_size`` and ``chunk_overlap`` are SentenceSplitter token units.
    AST-aware code splitting uses the independent line/character settings in
    ``resolved.chunking``; these token settings are used only by its fallback.
    """
    resolved = resolve_effective_settings(settings)
    if chunk_size is None:
        chunk_size = resolved.chunking.chunk_size
    if chunk_overlap is None:
        chunk_overlap = resolved.chunking.chunk_overlap
    markdown_chunk_size = resolved.chunking.markdown_chunk_size

    if content_type:
        group, _, label = content_type.partition("/")
    else:
        group, label = "", ""

    if not content_type and fallback_strategy == "code":
        ext = file_path.suffix.lower().lstrip(".")
        ts_lang = MAGIKA_LABEL_TO_TREESITTER.get(ext)
        if ts_lang:
            chunk_code_file_async = _chunking_get("code")
            return await chunk_code_file_async(
                file_path,
                ts_lang,
                chunk_size,
                chunk_overlap,
                None,
                code_chunk_lines=resolved.chunking.code_chunk_lines,
                code_chunk_lines_overlap=resolved.chunking.code_chunk_lines_overlap,
                code_max_chars=resolved.chunking.code_max_chars,
            )

    if group == "code":
        ts_lang = MAGIKA_LABEL_TO_TREESITTER.get(label)
        if ts_lang:
            chunk_code_file_async = _chunking_get("code")
            return await chunk_code_file_async(
                file_path,
                ts_lang,
                chunk_size,
                chunk_overlap,
                content_type,
                code_chunk_lines=resolved.chunking.code_chunk_lines,
                code_chunk_lines_overlap=resolved.chunking.code_chunk_lines_overlap,
                code_max_chars=resolved.chunking.code_max_chars,
            )
        logger.debug("No CodeSplitter mapping for code language %r", label)

    if group == "config":
        chunk_config_file = _chunking_get("config")
        return chunk_config_file(file_path, content_type)

    # Document-backend dispatch: the orchestrator applies the configured
    # backend, its registered suffix gate, the retry budget, and the
    # local-first fallback (spec document-backend-strategies).  The
    # chunker keeps only the post-processing choice, driven by the
    # structured flag: cloud parsers return pre-structured documents
    # (paragraphs/tables) that split directly, while the local chain
    # feeds file-level metadata extraction below.
    backend_read = await read_document(file_path, settings=resolved)
    if backend_read.structured:
        documents = backend_read.documents
        if content_type:
            for doc in documents:
                doc.metadata.setdefault("content_type", content_type)
        effective_chunk_size = (
            markdown_chunk_size if file_path.suffix.lower() == ".md" else chunk_size
        )
        splitter = SentenceSplitter(
            chunk_size=effective_chunk_size,
            chunk_overlap=chunk_overlap,
        )
        nodes = await asyncio.to_thread(lambda: splitter.get_nodes_from_documents(documents))
        if content_type:
            for node in nodes:
                node.metadata.setdefault("content_type", content_type)
        return nodes

    documents = backend_read.documents

    from ..metadata.extractor import extract_metadata_with_status_async

    if documents:
        file_text = "\n".join(d.get_content() for d in documents if hasattr(d, "get_content"))
        doc_metadata, metadata_degraded = await extract_metadata_with_status_async(
            file_text, file_path.name, resolved
        )
    else:
        doc_metadata = {}
        metadata_degraded = False
        logger.debug(
            "No documents loaded from %s — skipping metadata extraction",
            file_path.name,
        )

    if taxonomy_mode == "file_type" and content_type:
        _label = content_type.partition("/")[2] or content_type
        doc_metadata["category"] = _label

    is_markdown = file_path.suffix.lower() == ".md"
    effective_chunk_size = markdown_chunk_size if is_markdown else chunk_size

    from ..chunking.sentence import _split_documents_sync

    nodes = await asyncio.to_thread(
        _split_documents_sync,
        documents,
        is_markdown,
        effective_chunk_size,
        chunk_overlap,
    )

    if is_markdown:
        from ..chunking.markdown import (
            apply_heading_prepend,
            drop_small_markdown_chunks,
            ensure_heading_metadata,
        )

        ensure_heading_metadata(nodes)
        apply_heading_prepend(nodes, resolved.chunking.markdown_heading_prepend)
        nodes = drop_small_markdown_chunks(
            nodes,
            effective_chunk_size,
            resolved.chunking.markdown_min_chunk_fraction,
        )

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

    return _ChunkResult(nodes, metadata_degraded=metadata_degraded)
