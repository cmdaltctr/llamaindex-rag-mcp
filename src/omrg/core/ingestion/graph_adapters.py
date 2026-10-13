"""Graph adapters for the Sources, Read, Prepare text and Embed / commit families.

Task 3.4 of ``add-local-web-pipeline-workspace`` (design D2, D3, D4, D5).
Each adapter wraps one existing seam of ``ingest_path_async``; no adapter
holds a second copy of an identity, chunking or replacement rule:

* ``source.discover`` - ``gather_supported_files``, ``detect_content_types``
  and ``iter_source_units``. Its ``sources`` output is a list of
  :class:`SourceUnit`. The host runs the later nodes once per unit with
  :func:`ingestion_unit_split`, so a directory's chunks and vectors are
  never held at the same time.
* ``source.identify`` - ``prepare_source`` and ``check_source_state``:
  canonical identity, the legacy-lineage guard, and the complete-version
  reuse check. An unchanged source passes through the later nodes.
* ``read.document`` - ``chunk_specialised_source`` (code/config) or
  ``read_document``; the ``BackendRead`` declarations are kept.
* ``prepare.normalise`` / ``prepare.enrich`` / ``prepare.chunk`` -
  ``normalise_backend_read``, ``enrich_documents`` (explicit ``store``
  and ``settings``) and ``split_documents`` (registered strategies only).
* ``embed.chunks`` - ``prepare_source_embeddings`` (lineage, vectors, norm
  guard), outside the write lock.
* ``commit.source`` - ``commit_prepared_source``: lineage re-check, then
  write, verification and stale cleanup under the write lock. It is the
  only adapter that mutates the store.

Resources come only from :meth:`NodeContext.resource`: ``store``,
``embedder``, ``ingestion_shape`` (see :mod:`.graph_fingerprint`) and the
optional ``ocr`` client. Settings come only from ``context.settings``.
Blocking seams run in worker threads.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..chunking.model_token import resolve_markdown_chunking
from ..pipelines import NodeContext, NodeOutput, OperationCatalogue, UnitSplit
from .backends import read_document
from .chunker import (
    chunk_specialised_source,
    declares_markdown,
    enrich_documents,
    normalise_backend_read,
    split_documents,
)
from .commit import IngestionStageError, commit_prepared_source
from .graph_adapters_catalogue import (
    CHUNK,
    COMMIT,
    DISCOVER,
    EMBED,
    ENRICH,
    IDENTIFY,
    INGESTION_DESCRIPTORS,
    NORMALISE,
    READ,
    UNIT_NODE,
    UNIT_PORT,
    canonical_ingestion_definition,
)
from .graph_adapters_values import (
    BINARY,
    EMBEDDER_RESOURCE,
    OCR_RESOURCE,
    PENDING,
    STORE_RESOURCE,
    UNCHANGED,
    SourceWork,
    optional,
    required,
    run_protected,
    single_unit,
    stop_if_cancelled,
    target_collection,
    work_value,
)
from .graph_fingerprint import INGESTION_SHAPE_RESOURCE, IngestionShape
from .loader import gather_supported_files, make_file_detail
from .replacement import prepare_source_embeddings
from .source_state import new_source_attempt
from .sources import (
    SourceUnit,
    build_ingestion_context,
    check_source_state,
    detect_content_types,
    iter_source_units,
    prepare_source,
)
from .writer import remove_source_rows_or_error

__all__ = [
    "CHUNK",
    "INGESTION_DESCRIPTORS",
    "INGESTION_SHAPE_RESOURCE",
    "SourceWork",
    "canonical_ingestion_definition",
    "ingestion_unit_split",
    "register_ingestion_operations",
    "source_unit_id",
]


def source_unit_id(unit: SourceUnit) -> str:
    """Return the unit identifier for events: the path relative to the root."""
    return unit.rel_path


def ingestion_unit_split() -> UnitSplit:
    """Return the per-source unit split of the canonical ingestion graph."""
    return UnitSplit(node=UNIT_NODE, port=UNIT_PORT, unit_id=source_unit_id)


def _out(port: str, work: SourceWork, **summary: Any) -> NodeOutput:
    return NodeOutput(
        values={port: work},
        summary={"source": work.unit.rel_path, "status": work.status, **summary},
    )


# ── Sources ──────────────────────────────────────────────────────────────


async def discover_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """List the eligible source units under the input path."""
    settings = context.settings
    raw = inputs["sources"]
    path = Path(str(raw)).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {raw}")
    extensions = set(settings.ingestion.ingest_extensions)
    if path.is_file() and path.suffix.lower() not in extensions:
        raise ValueError(
            f"Unsupported file extension: {path.suffix}. Supported: {', '.join(sorted(extensions))}"
        )
    files, skipped = await asyncio.to_thread(gather_supported_files, path, extensions=extensions)
    content_types = (
        await asyncio.to_thread(detect_content_types, path, settings=settings) if files else {}
    )
    units = list(iter_source_units(path, files, content_types))
    return NodeOutput(
        values={"sources": units},
        summary={"sources": len(units), "skipped_unsupported": len(skipped)},
    )


async def identify_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Identify one source and run the legacy-lineage and reuse checks."""
    unit = single_unit(inputs["sources"])
    collection = target_collection(context, params)
    store = required(context, STORE_RESOURCE)
    embedder = required(context, EMBEDDER_RESOURCE)
    shape = required(context, INGESTION_SHAPE_RESOURCE)
    if not isinstance(shape, IngestionShape):
        raise TypeError(f"Resource {INGESTION_SHAPE_RESOURCE!r} must be an IngestionShape.")
    if unit.content_type and unit.content_type.startswith("binary"):
        return _out("sources", SourceWork(unit, collection, status=BINARY))
    ingestion = await asyncio.to_thread(
        build_ingestion_context,
        context.settings,
        embed_model=embedder,
        ocr_client=optional(context, OCR_RESOURCE),
        graph_shape=shape.identity_block(),
    )
    identity = await prepare_source(
        unit.file_path, content_type=unit.content_type, context=ingestion
    )
    reuse = await check_source_state(identity, store=store, collection_name=collection)
    work = SourceWork(
        unit,
        collection,
        status=UNCHANGED if reuse.unchanged else PENDING,
        identity=identity,
        existing_chunks=reuse.existing_chunks,
    )
    return _out("sources", work, source_version=identity.source_version)


# ── Read and prepare text ────────────────────────────────────────────────


async def read_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Read one source, or split it with its code/config strategy."""
    work = work_value(inputs["sources"])
    if not work.pending:
        return _out("documents", work)
    settings, unit = context.settings, work.unit
    specialised = await chunk_specialised_source(
        unit.file_path,
        content_type=unit.content_type,
        fallback_strategy=settings.chunking.strategy_fallback,
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
        settings=settings,
    )
    if specialised is not None:
        strategy = getattr(specialised, "chunk_strategy_effective", None)
        work = replace(work, nodes=specialised, specialised=True, effective_strategy=strategy)
        return _out("documents", work, specialised=True)
    backend_read = await read_document(
        unit.file_path, settings=settings, ocr_client=optional(context, OCR_RESOURCE)
    )
    return _out(
        "documents",
        replace(work, backend_read=backend_read),
        documents=len(backend_read.documents),
        text_format=backend_read.text_format,
        structured=backend_read.structured,
    )


async def normalise_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Normalise PDF reader output when the settings enable it."""
    work = work_value(inputs["documents"])
    if not work.pending or work.backend_read is None:
        return _out("documents", work)
    backend_read = await asyncio.to_thread(
        normalise_backend_read,
        work.backend_read,
        work.unit.file_path,
        content_type=work.unit.content_type,
        settings=context.settings,
    )
    return _out("documents", replace(work, backend_read=backend_read))


async def enrich_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Extract file-level metadata for an unstructured read."""
    work = work_value(inputs["documents"])
    read = work.backend_read
    if not work.pending or read is None or read.structured:
        return _out("documents", work)
    settings = context.settings
    metadata, degraded = await enrich_documents(
        read.documents,
        work.unit.file_path,
        content_type=work.unit.content_type,
        taxonomy_mode=settings.metadata.taxonomy_mode,
        settings=settings,
        store=required(context, STORE_RESOURCE),
    )
    work = replace(work, doc_metadata=metadata, metadata_degraded=degraded)
    return _out("documents", work, metadata_degraded=degraded)


async def chunk_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Split one source's documents with the registered strategy."""
    work = work_value(inputs["documents"])
    if not work.pending:
        return _out("chunks", work)
    file_path, nodes = work.unit.file_path, work.nodes
    if not work.specialised:
        read = work.backend_read
        if read is None:
            raise ValueError(f"Source {work.unit.rel_path!r} was not read. Connect read.document.")
        settings = context.settings
        is_markdown = declares_markdown(file_path, read)
        markdown_chunking = (
            await asyncio.to_thread(resolve_markdown_chunking, settings) if is_markdown else None
        )
        nodes = await split_documents(
            read.documents,
            file_path,
            structured=read.structured,
            is_markdown=is_markdown,
            chunk_size=settings.chunking.chunk_size,
            chunk_overlap=settings.chunking.chunk_overlap,
            content_type=work.unit.content_type,
            settings=settings,
            markdown_chunking=markdown_chunking,
            doc_metadata=None if read.structured else work.doc_metadata,
        )
    if not nodes:
        raise IngestionStageError("parse_chunk", f"No chunks were produced for '{file_path}'.")
    return _out("chunks", replace(work, nodes=nodes), chunks=len(nodes))


# ── Embed and commit ─────────────────────────────────────────────────────


async def embed_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Stamp lineage, embed and check vectors outside the write lock."""
    work = work_value(inputs["chunks"])
    if not work.pending:
        return _out("chunks", work)
    identity, nodes = work.require_identity(), work.nodes
    if not nodes:
        raise ValueError(f"Source {work.unit.rel_path!r} has no chunks. Connect prepare.chunk.")
    settings = context.settings
    context.progress("embed_start", {"chunks": len(nodes)})
    prepared = await asyncio.to_thread(
        prepare_source_embeddings,
        nodes,
        file_path=identity.canonical_file_path,
        source_id=identity.source_id,
        content_hash=identity.content_hash,
        index_identity=identity.index_identity,
        source_version=identity.source_version,
        source_attempt=new_source_attempt(),
        embed_model=required(context, EMBEDDER_RESOURCE),
        embed_concurrency=settings.ingestion.embed_concurrency,
        norm_guard_enabled=settings.embedding.norm_guard_enabled,
        norm_tolerance=settings.embedding.norm_tolerance,
    )
    return _out("chunks", replace(work, prepared=prepared), chunks=prepared.chunk_count)


def _skipped_unchanged(work: SourceWork) -> NodeOutput:
    detail = make_file_detail(
        file_name=work.unit.file_path.name, status="skipped_unchanged", chunks=0
    )
    detail["existing_chunks"] = work.existing_chunks
    detail["source_version"] = work.require_identity().source_version
    return NodeOutput(values={"summary": detail}, summary={"status": "skipped_unchanged"})


async def _commit_binary(work: SourceWork, collection: str, store: Any) -> NodeOutput:
    file_path = work.unit.file_path
    cleaned, message, removed = await run_protected(
        functools.partial(remove_source_rows_or_error, str(file_path), collection, store)
    )
    if not cleaned:
        raise IngestionStageError("store_write", f"binary-skip cleanup failed: {message}")
    detail = make_file_detail(file_name=file_path.name, status="skipped", chunks=0)
    detail["chunks_removed"] = removed
    effects = (f"removed:{work.unit.rel_path}",) if removed else ()
    return NodeOutput(values={"summary": detail}, effects=effects, summary={"status": "skipped"})


async def commit_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Write, verify and clean one source as one protected operation."""
    work = work_value(inputs["chunks"])
    collection = target_collection(context, params)
    if work.collection != collection:
        raise ValueError(
            f"The reuse check ran against collection {work.collection!r}, but this commit "
            f"writes to {collection!r}. Bind source.identify and commit.source to the same "
            "collection."
        )
    store = required(context, STORE_RESOURCE)
    if work.status == UNCHANGED:
        return _skipped_unchanged(work)
    stop_if_cancelled(context)
    if work.status == BINARY:
        return await _commit_binary(work, collection, store)
    identity, prepared = work.require_identity(), work.prepared
    if prepared is None or not work.nodes:
        raise ValueError(f"Source {work.unit.rel_path!r} was not embedded. Connect embed.chunks.")
    outcome = await run_protected(
        functools.partial(
            commit_prepared_source,
            work.nodes,
            prepared,
            collection_name=collection,
            store=store,
            embed_model=optional(context, EMBEDDER_RESOURCE),
        )
    )
    detail = make_file_detail(
        file_name=work.unit.file_path.name,
        status="indexed",
        chunks=outcome.chunks_written,
        metadata_degraded=work.metadata_degraded,
    )
    detail.update(
        source_version=identity.source_version,
        source_id=identity.source_id,
        chunks_removed=outcome.chunks_removed,
        timings=outcome.timings.as_dict(),
    )
    if work.effective_strategy is not None:
        detail["effective_strategy"] = work.effective_strategy
    if outcome.norm_band is not None:
        detail["embedding_norm_band"] = {"min": outcome.norm_band[0], "max": outcome.norm_band[1]}
    effects = (f"committed:{identity.source_id}",) if outcome.chunks_written else ()
    return NodeOutput(
        values={"summary": detail},
        effects=effects,
        summary={"status": "indexed", "chunks": outcome.chunks_written},
    )


_ADAPTERS = (
    (DISCOVER, discover_adapter),
    (IDENTIFY, identify_adapter),
    (READ, read_adapter),
    (NORMALISE, normalise_adapter),
    (ENRICH, enrich_adapter),
    (CHUNK, chunk_adapter),
    (EMBED, embed_adapter),
    (COMMIT, commit_adapter),
)


def register_ingestion_operations(catalogue: OperationCatalogue) -> None:
    """Register the Sources, Read, Prepare text and Embed / commit operations.

    Args:
        catalogue: The catalogue the composition root builds.

    Raises:
        ValueError: If an ingestion operation version is already registered.
    """
    for descriptor, adapter in _ADAPTERS:
        catalogue.register(descriptor, adapter)
