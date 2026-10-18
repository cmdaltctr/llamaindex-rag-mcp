"""Per-source ingestion seams shared by ``ingest_path_async`` and graph runs.

Each function handles one stage for one source unit. The standard pipeline
and a graph runner compose the same functions, so source identity, reuse
checks, chunking arguments, and protected replacement cannot drift apart:

1. :func:`detect_content_types` and :func:`iter_source_units` - discovery
   output turned into one bounded unit at a time.
2. :func:`build_ingestion_context` - the operation-wide index-shaping
   inputs, resolved once.
3. :func:`prepare_source` - canonical identity, content hash, declared
   reader text format, index identity, and source version.
4. :func:`check_source_state` - the pre-lineage compatibility guard, then
   the complete-current-version reuse check.
5. :func:`chunk_source` - read, normalise, enrich, and split.
6. :func:`commit_source` - embedding preparation, then protected
   replacement.

Every seam takes ``settings`` (through the context) and ``store``
explicitly. None of them reads a process-wide default.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from .backends.orchestrator import resolve_declared_text_format
from .chunker import read_and_chunk_file_async
from .hashing import sha256_file
from .ocr_identity import resolved_routing_payload, route_fingerprints
from .replacement import ReplaceSourceOutcome, replace_source_nodes_async
from .source_state import (
    assert_source_lineage_compatible,
    build_index_identity,
    build_source_id,
    build_source_version,
    canonical_source_path,
    is_complete_current_version,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceUnit:
    """One discovered source, processed alone from read to commit."""

    index: int
    file_path: Path
    rel_path: str
    content_type: str | None


@dataclass(frozen=True)
class IngestionContext:
    """Index-shaping inputs resolved once per ingestion operation.

    Attributes:
        settings: Injected effective settings.
        chunk_size: Effective token chunk size (override or settings).
        chunk_overlap: Effective token overlap (override or settings).
        markdown_chunking: Resolved Markdown tokenizer/splitter identity.
        embed_model: Optional injected embedding model.
        ocr_routing: Resolved OCR routing payload for the identity.
        ocr_worker_fingerprint: Fingerprint of the OCR worker route.
        ocr_fallback_fingerprint: Fingerprint of the OCR fallback route.
        graph_shape: Identity block of a non-standard ingestion graph, or
            ``None`` for the standard shape.
        embedding_identity: Provider and model that made the vectors, or
            ``None`` for the store's composed identity (ADR-081).
    """

    settings: Any
    chunk_size: int
    chunk_overlap: int
    markdown_chunking: Any
    embed_model: Any
    ocr_routing: dict[str, Any]
    ocr_worker_fingerprint: Any
    ocr_fallback_fingerprint: Any
    graph_shape: dict[str, Any] | None = None
    embedding_identity: Any = None


@dataclass(frozen=True)
class SourceIdentity:
    """Identity of one source version under one index-shaping context."""

    file_path: Path
    canonical_file_path: str
    source_id: str
    content_hash: str
    content_type: str | None
    text_format: str
    index_identity: str
    source_version: str


class SourceReuse(NamedTuple):
    """Result of the complete-current-version check."""

    unchanged: bool
    existing_chunks: int


def detect_content_types(root: Path, *, settings: Any) -> dict[str, str]:
    """Map relative paths under *root* to Magika ``group/label`` types.

    Detection failure degrades to an empty map, so routing falls back to
    file extensions exactly as before. The operation's settings travel into
    the detector, so a direct-Engine process needs no process default.
    """
    from ..codebase.codebase_map import detect_file_types

    content_types: dict[str, str] = {}
    try:
        inventory = detect_file_types(str(root), settings=settings)
        for entry in inventory.entries:
            content_types[entry.path] = f"{entry.group}/{entry.label}"
    except Exception as exc:
        logger.warning("Magika detection failed, using extension-based routing: %s", exc)
    return content_types


def iter_source_units(
    root: Path,
    files: Sequence[Path],
    content_types: Mapping[str, str],
) -> Iterator[SourceUnit]:
    """Yield one source unit at a time, in discovery order.

    Args:
        root: The path that was ingested (file or directory).
        files: Supported files from ``loader.gather_supported_files``.
        content_types: Output of :func:`detect_content_types`.
    """
    for index, file_path in enumerate(files):
        try:
            rel_path = str(file_path.relative_to(root))
        except ValueError:
            rel_path = str(file_path)
        yield SourceUnit(index, file_path, rel_path, content_types.get(rel_path))


def build_ingestion_context(
    settings: Any,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    markdown_chunking: Any = None,
    embed_model: Any = None,
    ocr_client: Any = None,
    graph_shape: dict[str, Any] | None = None,
    embedding_identity: Any = None,
) -> IngestionContext:
    """Resolve the operation-wide index-shaping inputs once.

    Args:
        settings: Injected effective settings (required).
        chunk_size: Optional chunk-size override.
        chunk_overlap: Optional chunk-overlap override.
        markdown_chunking: Resolved Markdown chunking; resolved from
            *settings* when omitted.
        embed_model: Optional injected embedding model.
        ocr_client: The injected-or-composed OCR client. Its fingerprints
            are read once here, never per file; ``None`` resolves to the
            stable unavailable fingerprint.
        graph_shape: Identity block of a non-standard ingestion graph.
        embedding_identity: Provider and model that made the vectors.
    """
    if markdown_chunking is None:
        from ..chunking.model_token import resolve_markdown_chunking

        markdown_chunking = resolve_markdown_chunking(settings)
    worker_fingerprint, fallback_fingerprint = route_fingerprints(ocr_client)
    return IngestionContext(
        settings=settings,
        chunk_size=chunk_size if chunk_size is not None else settings.chunking.chunk_size,
        chunk_overlap=(
            chunk_overlap if chunk_overlap is not None else settings.chunking.chunk_overlap
        ),
        markdown_chunking=markdown_chunking,
        embed_model=embed_model,
        ocr_routing=resolved_routing_payload(settings),
        ocr_worker_fingerprint=worker_fingerprint,
        ocr_fallback_fingerprint=fallback_fingerprint,
        graph_shape=graph_shape,
        embedding_identity=embedding_identity,
    )


async def prepare_source(
    file_path: Path,
    *,
    content_type: str | None,
    context: IngestionContext,
    text_format_resolver: Callable[..., str] = resolve_declared_text_format,
) -> SourceIdentity:
    """Compute the canonical identity and source version of one file.

    The declared reader text format is resolved before the reuse check
    (design D3): it decides Markdown routing, so it belongs in the index
    identity. ``read_document`` later verifies the same declaration.

    Args:
        file_path: Source file to identify.
        content_type: Magika ``group/label`` or ``None``.
        context: The operation's ingestion context.
        text_format_resolver: Pre-read text-format resolver; the standard
            pipeline passes its own module binding so its existing test
            seams stay valid.
    """
    canonical_file_path = canonical_source_path(file_path)
    content_hash = await asyncio.to_thread(sha256_file, file_path)
    text_format = text_format_resolver(file_path, settings=context.settings)
    index_identity = build_index_identity(
        context.settings,
        content_type=content_type,
        chunk_size=context.chunk_size,
        chunk_overlap=context.chunk_overlap,
        text_format=text_format,
        embed_model=context.embed_model,
        ocr_routing=context.ocr_routing,
        ocr_worker_fingerprint=context.ocr_worker_fingerprint,
        ocr_fallback_fingerprint=context.ocr_fallback_fingerprint,
        tokenizer=context.markdown_chunking.tokenizer_identity,
        resolved_splitter=context.markdown_chunking.resolved_splitter,
        graph_shape=context.graph_shape,
    )
    return SourceIdentity(
        file_path=file_path,
        canonical_file_path=canonical_file_path,
        source_id=build_source_id(canonical_file_path),
        content_hash=content_hash,
        content_type=content_type,
        text_format=text_format,
        index_identity=index_identity,
        source_version=build_source_version(content_hash, index_identity),
    )


async def check_source_state(
    identity: SourceIdentity,
    *,
    store: Any,
    collection_name: str,
    lineage_guard: Callable[..., None] = assert_source_lineage_compatible,
    completeness_check: Callable[..., tuple[bool, int]] = is_complete_current_version,
) -> SourceReuse:
    """Reject pre-lineage rows, then report whether the version is complete.

    The guard runs before any parse, embedding, or store mutation so
    schemas never mix silently.

    Args:
        identity: Output of :func:`prepare_source`.
        store: The owning vector store (required).
        collection_name: Target collection.
        lineage_guard: Compatibility guard; the standard pipeline passes
            its own module binding so its existing test seams stay valid.
        completeness_check: Complete-version check; passed the same way.

    Raises:
        IncompatibleSourceLineageError: When rows for the path predate
            stable lineage.
    """
    await asyncio.to_thread(
        lineage_guard,
        store,
        collection_name,
        file_path=identity.canonical_file_path,
        source_id=identity.source_id,
    )
    unchanged, existing_chunks = await asyncio.to_thread(
        completeness_check,
        store,
        collection_name,
        source_id=identity.source_id,
        content_hash=identity.content_hash,
        index_identity=identity.index_identity,
        source_version=identity.source_version,
    )
    return SourceReuse(unchanged, existing_chunks)


async def chunk_source(
    identity: SourceIdentity,
    *,
    context: IngestionContext,
    store: Any,
    ocr_client: Any = None,
    chunker: Callable[..., Any] = read_and_chunk_file_async,
) -> list:
    """Read, normalise, enrich, and split one source.

    Args:
        identity: Output of :func:`prepare_source`.
        context: The operation's ingestion context.
        store: Owning vector store, forwarded to metadata extraction.
        ocr_client: Optional injected OCR client for the reader.
        chunker: Chunking entry point; the standard pipeline passes its
            own module binding so its existing test seams stay valid.
    """
    settings = context.settings
    return await chunker(
        identity.file_path,
        chunk_size=context.chunk_size,
        chunk_overlap=context.chunk_overlap,
        content_type=identity.content_type,
        fallback_strategy=settings.chunking.strategy_fallback,
        taxonomy_mode=settings.metadata.taxonomy_mode,
        settings=settings,
        ocr_client=ocr_client,
        markdown_chunking=context.markdown_chunking,
        store=store,
    )


async def commit_source(
    nodes: list,
    identity: SourceIdentity,
    *,
    context: IngestionContext,
    store: Any,
    collection_name: str,
    progress_callback: Callable | None = None,
    replacer: Callable[..., Any] = replace_source_nodes_async,
) -> ReplaceSourceOutcome:
    """Embed and protectively replace one source version.

    Args:
        nodes: Chunked nodes for exactly this source.
        identity: Output of :func:`prepare_source`.
        context: The operation's ingestion context.
        store: The owning vector store (required).
        collection_name: Target collection.
        progress_callback: Optional ``(phase, current, total)`` callback.
        replacer: Replacement entry point; the standard pipeline passes its
            own module binding so its existing test seams stay valid.
    """
    settings = context.settings
    identity_kwargs = (
        {"embedding_identity": context.embedding_identity} if context.embedding_identity else {}
    )
    return await replacer(
        nodes,
        file_path=identity.canonical_file_path,
        source_id=identity.source_id,
        content_hash=identity.content_hash,
        index_identity=identity.index_identity,
        source_version=identity.source_version,
        progress_callback=progress_callback,
        collection_name=collection_name,
        store=store,
        embed_model=context.embed_model,
        embed_concurrency=settings.ingestion.embed_concurrency,
        norm_guard_enabled=settings.embedding.norm_guard_enabled,
        norm_tolerance=settings.embedding.norm_tolerance,
        **identity_kwargs,
    )
