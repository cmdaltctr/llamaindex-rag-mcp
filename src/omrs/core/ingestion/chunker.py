"""Content-type → chunking strategy dispatch.

Reads files via the registry-backed document backends
(``core/ingestion/backends/``), extracts metadata, and dispatches to the
appropriate chunking strategy based on Magika content-type detection.
Content-type takes precedence over file extension when available.
Extracted from the original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..chunking.registry import get as _chunking_get
from ..codebase.ast_extract import MAGIKA_LABEL_TO_TREESITTER
from ..settings import resolve_effective_settings
from .backends import read_document
from .backends.orchestrator import BackendRead
from .normalise import normalise_reader_text

logger = logging.getLogger(__name__)


class _ChunkResult(list):
    """List of chunked nodes that also carries a metadata-degradation flag."""

    def __init__(self, nodes=(), *, metadata_degraded: bool = False) -> None:
        super().__init__(nodes)
        self.metadata_degraded = metadata_degraded


async def _chunk_documents(
    documents: list,
    file_path: Path,
    is_markdown: bool,
    chunk_size: int,
    chunk_overlap: int,
    settings: Any,
    markdown_chunking: Any,
) -> list:
    """Resolve the ``sentence`` strategy through the registry and await it.

    The registered callable performs splitting and, for Markdown, the
    shared post-processing exactly once. The chunker does not call the
    private sentence helpers.
    """
    chunk_sentence = _chunking_get("sentence")
    return await chunk_sentence(
        documents,
        str(file_path),
        is_markdown,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        settings=settings,
        markdown_chunking=markdown_chunking if is_markdown else None,
    )


def _split_content_type(content_type: str | None) -> tuple[str, str]:
    """Return the ``(group, label)`` pair of a Magika content type."""
    if content_type:
        group, _, label = content_type.partition("/")
        return group, label
    return "", ""


async def chunk_specialised_source(
    file_path: Path,
    *,
    content_type: str | None,
    fallback_strategy: str | None,
    chunk_size: int,
    chunk_overlap: int,
    settings: Any,
) -> list | None:
    """Chunk code or configuration sources through their registered strategy.

    This is the content-type dispatch seam: ``content_type`` takes
    precedence over the file extension, and the extension is used only when
    detection produced nothing and the fallback strategy is ``code``.

    Args:
        file_path: Source file to chunk.
        content_type: Magika ``group/label`` or ``None``.
        fallback_strategy: ``settings.chunking.strategy_fallback``.
        chunk_size: Token chunk size for the AST splitter's fallback.
        chunk_overlap: Token overlap for the AST splitter's fallback.
        settings: Injected effective settings.

    Returns:
        The chunked nodes, or ``None`` when the source must go through the
        document reader instead.
    """
    group, label = _split_content_type(content_type)
    chunking = settings.chunking
    ts_lang = None
    detected_type: str | None = None
    if not content_type and fallback_strategy == "code":
        ts_lang = MAGIKA_LABEL_TO_TREESITTER.get(file_path.suffix.lower().lstrip("."))
    elif group == "code":
        ts_lang = MAGIKA_LABEL_TO_TREESITTER.get(label)
        detected_type = content_type
        if not ts_lang:
            logger.debug("No CodeSplitter mapping for code language %r", label)
    if ts_lang:
        chunk_code_file_async = _chunking_get("code")
        return await chunk_code_file_async(
            file_path,
            ts_lang,
            chunk_size,
            chunk_overlap,
            detected_type,
            code_chunk_lines=chunking.code_chunk_lines,
            code_chunk_lines_overlap=chunking.code_chunk_lines_overlap,
            code_max_chars=chunking.code_max_chars,
        )
    if group == "config":
        chunk_config_file = _chunking_get("config")
        return chunk_config_file(file_path, content_type)
    return None


def normalise_backend_read(
    backend_read: BackendRead,
    file_path: Path,
    *,
    content_type: str | None,
    settings: Any,
) -> BackendRead:
    """Apply reader-output normalisation to PDF reads when it is enabled.

    The documents are normalised in place and the same ``BackendRead`` is
    returned, so its ``structured`` and ``text_format`` declarations reach
    the splitter unchanged.
    """
    _group, label = _split_content_type(content_type)
    if settings.ingestion.normalise_reader_output and (
        file_path.suffix.lower() == ".pdf" or label == "pdf"
    ):
        for document in backend_read.documents:
            if document.text_resource is not None and document.text_resource.text is not None:
                document.text_resource.text = normalise_reader_text(document.text)
    return backend_read


def declares_markdown(file_path: Path, backend_read: BackendRead) -> bool:
    """Return whether the read text is Markdown.

    Text counts as Markdown when the source file has extension ``.md``, or
    when the reader that produced it declares its emitted text format as
    ``markdown`` (spec markdown-aware-chunking; design D3). Routing follows
    the declaration, never the source extension alone, so reader-produced
    Markdown keeps its heading structure.
    """
    return file_path.suffix.lower() == ".md" or backend_read.text_format == "markdown"


async def enrich_documents(
    documents: list,
    file_path: Path,
    *,
    content_type: str | None,
    taxonomy_mode: str | None,
    settings: Any,
    store: Any,
) -> tuple[dict, bool]:
    """Extract file-level metadata for unstructured reads.

    ``settings`` and ``store`` are required keywords: omitting them would
    silently fall back to process defaults or seed categories only.

    Args:
        documents: Documents from one source read.
        file_path: Source file, used for the file name.
        content_type: Magika ``group/label`` or ``None``.
        taxonomy_mode: ``settings.metadata.taxonomy_mode`` or an override.
        settings: Injected effective settings.
        store: Owning vector store forwarded to category lookup, or
            ``None`` for seed categories only.

    Returns:
        ``(metadata, degraded)`` where ``degraded`` records a fallback tier.
    """
    from ..metadata.extractor import extract_metadata_with_status_async

    if documents:
        file_text = "\n".join(d.get_content() for d in documents if hasattr(d, "get_content"))
        doc_metadata, metadata_degraded = await extract_metadata_with_status_async(
            file_text, file_path.name, settings, store=store
        )
    else:
        doc_metadata = {}
        metadata_degraded = False
        logger.debug("No documents loaded from %s — skipping metadata extraction", file_path.name)

    if taxonomy_mode == "file_type" and content_type:
        doc_metadata["category"] = content_type.partition("/")[2] or content_type
    return doc_metadata, metadata_degraded


async def split_documents(
    documents: list,
    file_path: Path,
    *,
    structured: bool,
    is_markdown: bool,
    chunk_size: int,
    chunk_overlap: int,
    content_type: str | None,
    settings: Any,
    markdown_chunking: Any = None,
    doc_metadata: dict | None = None,
) -> list:
    """Split one source's documents and stamp shared node metadata.

    Pre-structured reads stamp ``content_type`` on the documents before
    splitting; every read stamps it on the nodes. File-level metadata is
    flattened (lists become comma-separated strings) onto every node.
    """
    if is_markdown and markdown_chunking is None:
        from ..chunking.model_token import resolve_markdown_chunking

        markdown_chunking = resolve_markdown_chunking(settings)
    if structured and content_type:
        for doc in documents:
            doc.metadata.setdefault("content_type", content_type)
    effective_chunk_size = settings.chunking.markdown_chunk_size if is_markdown else chunk_size
    nodes = await _chunk_documents(
        documents,
        file_path,
        is_markdown,
        effective_chunk_size,
        chunk_overlap,
        settings,
        markdown_chunking,
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
    return nodes


async def read_and_chunk_file_async(
    file_path: Path,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    content_type: str | None = None,
    fallback_strategy: str | None = None,
    taxonomy_mode: str | None = None,
    settings: Any = None,
    ocr_client: Any = None,
    markdown_chunking: Any = None,
    *,
    store: Any = None,
) -> list:
    """Read and chunk a file, dispatching strategy based on content_type.

    ``chunk_size`` and ``chunk_overlap`` are SentenceSplitter token units.
    AST-aware code splitting uses the independent line/character settings in
    ``resolved.chunking``; these token settings are used only by its fallback.

    The function composes the per-source seams in order: specialised
    code/config dispatch, ``read_document``, :func:`normalise_backend_read`,
    :func:`enrich_documents` (unstructured reads only) and
    :func:`split_documents`. Both document branches resolve the
    ``sentence`` strategy through the chunking registry, so a registered
    replacement takes effect in production ingestion.

    Args:
        store: Optional owning vector store, forwarded by keyword to
            metadata extraction so category lookup reads the collections
            of the store that ingestion writes to. ``None`` means no stored
            categories (seed categories only).
    """
    resolved = resolve_effective_settings(settings)
    if chunk_size is None:
        chunk_size = resolved.chunking.chunk_size
    if chunk_overlap is None:
        chunk_overlap = resolved.chunking.chunk_overlap

    specialised = await chunk_specialised_source(
        file_path,
        content_type=content_type,
        fallback_strategy=fallback_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        settings=resolved,
    )
    if specialised is not None:
        return specialised

    # Document-backend dispatch: the orchestrator applies the configured
    # backend, its registered suffix gate, the retry budget, and the
    # local-first fallback (spec document-backend-strategies). Cloud
    # parsers return pre-structured documents (paragraphs/tables) that
    # split directly, while the local chain feeds file-level metadata
    # extraction first.
    backend_read = await read_document(file_path, settings=resolved, ocr_client=ocr_client)
    backend_read = normalise_backend_read(
        backend_read, file_path, content_type=content_type, settings=resolved
    )
    split_options = {
        "structured": backend_read.structured,
        "is_markdown": declares_markdown(file_path, backend_read),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "content_type": content_type,
        "settings": resolved,
        "markdown_chunking": markdown_chunking,
    }
    if backend_read.structured:
        return await split_documents(backend_read.documents, file_path, **split_options)

    doc_metadata, metadata_degraded = await enrich_documents(
        backend_read.documents,
        file_path,
        content_type=content_type,
        taxonomy_mode=taxonomy_mode,
        settings=resolved,
        store=store,
    )
    nodes = await split_documents(
        backend_read.documents, file_path, doc_metadata=doc_metadata, **split_options
    )
    return _ChunkResult(nodes, metadata_degraded=metadata_degraded)
