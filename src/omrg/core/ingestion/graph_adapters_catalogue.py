"""Operation descriptors and the canonical ingestion graph (tasks 3.4, 3.5).

This module holds the published contracts of the Sources, Read, Prepare
text, and Embed / commit families, and the canonical ingestion template.
It holds no adapter code, so :mod:`.graph_fingerprint` can read the
descriptors without a cycle. :mod:`.graph_adapters` pairs each descriptor
with its adapter.

Canonical order (one source unit per pass after ``source.discover``)::

    source.discover -> source.identify -> read.document -> prepare.normalise
      -> prepare.enrich -> prepare.chunk -> embed.chunks -> commit.source
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..pipelines import (
    READER_STRUCTURED,
    READER_TEXT_FORMAT,
    BypassSpec,
    EffectClass,
    OperationDescriptor,
    PipelineDefinition,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
    parse_definition,
)

_SOURCE = frozenset({Provenance.SOURCE})
_RAW_PATH = PortType(PortKind.SOURCES)
_UNITS = PortType(PortKind.SOURCES, provenance=_SOURCE)
_DOCUMENTS = PortType(
    PortKind.DOCUMENTS,
    provenance=_SOURCE,
    reader_declarations=frozenset({READER_TEXT_FORMAT, READER_STRUCTURED}),
)
_CHUNKS = PortType(PortKind.CHUNKS, provenance=_SOURCE)
_EMBEDDED = PortType(
    PortKind.EMBEDDED_CHUNKS,
    provenance=frozenset({Provenance.SOURCE, Provenance.CHUNK_LINEAGE}),
    embedding_identity=True,
)
_SUMMARY = PortType(PortKind.COMMIT_SUMMARY, provenance=frozenset({Provenance.COLLECTION}))

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class NoParams(BaseModel):
    """Operation without parameters."""

    model_config = _FROZEN


class CollectionParams(BaseModel):
    """Parameters of collection-bound operations.

    Attributes:
        collection: Target collection. ``None`` uses the graph collection,
            then the host default.
    """

    model_config = _FROZEN

    collection: str | None = Field(default=None, min_length=1, max_length=128)


class ReadParams(BaseModel):
    """Node overrides for ``read.document`` (``None`` inherits).

    Code and configuration sources are split by their registered strategy
    in this node, before any document read (content type has precedence).

    Attributes:
        strategy_fallback: ``chunking.strategy_fallback`` lever.
        code_chunk_lines: ``chunking.code_chunk_lines`` lever.
    """

    model_config = _FROZEN

    strategy_fallback: Literal["markdown", "code", "sentence"] | None = None
    code_chunk_lines: int | None = Field(default=None, ge=1)


class EnrichParams(BaseModel):
    """Node override for ``prepare.enrich`` (``None`` inherits).

    Attributes:
        taxonomy_mode: ``metadata.taxonomy_mode`` lever.
    """

    model_config = _FROZEN

    taxonomy_mode: Literal["category", "file_type"] | None = None


class ChunkParams(BaseModel):
    """Node overrides for ``prepare.chunk`` (``None`` inherits).

    Attributes:
        chunk_size: ``chunking.chunk_size`` lever.
        chunk_overlap: ``chunking.chunk_overlap`` lever.
        markdown_chunk_size: ``chunking.markdown_chunk_size`` lever.
    """

    model_config = _FROZEN

    chunk_size: int | None = Field(default=None, ge=1)
    chunk_overlap: int | None = Field(default=None, ge=0)
    markdown_chunk_size: int | None = Field(default=None, ge=1)


def _port(name: str, port_type: PortType, description: str) -> PortSpec:
    return PortSpec(name=name, type=port_type, description=description)


DISCOVER = OperationDescriptor(
    operation_id="source.discover",
    version=1,
    title="Discover sources",
    family="sources",
    description=(
        "List the eligible files under a path with their detected content types. "
        "Run the downstream nodes once per listed source."
    ),
    parameters=NoParams,
    inputs=(_port("sources", _RAW_PATH, "File or directory path."),),
    outputs=(_port("sources", _UNITS, "Source units in discovery order."),),
    effect=EffectClass.READ_ONLY,
)

IDENTIFY = OperationDescriptor(
    operation_id="source.identify",
    version=1,
    title="Identify source",
    family="sources",
    description=(
        "Compute the canonical source identity and index identity. Reject legacy "
        "lineage. Mark a complete current version as unchanged, so later nodes skip it."
    ),
    parameters=CollectionParams,
    inputs=(_port("sources", _UNITS, "Exactly one source unit."),),
    outputs=(_port("sources", _UNITS, "The identified source."),),
    capabilities=("store", "embedder"),
    effect=EffectClass.READ_ONLY,
    collection_param="collection",
)

READ = OperationDescriptor(
    operation_id="read.document",
    version=1,
    title="Read document",
    family="read",
    description=(
        "Read the source with the configured backend and keep its reader declarations. "
        "Code and configuration sources use their registered strategy instead."
    ),
    parameters=ReadParams,
    inputs=(_port("sources", _UNITS, "The identified source."),),
    outputs=(_port("documents", _DOCUMENTS, "Documents with reader declarations."),),
    effect=EffectClass.READ_ONLY,
    lever_params={
        "strategy_fallback": "chunking.strategy_fallback",
        "code_chunk_lines": "chunking.code_chunk_lines",
    },
    index_shaping=True,
)

NORMALISE = OperationDescriptor(
    operation_id="prepare.normalise",
    version=1,
    title="Normalise text",
    family="prepare",
    description="Apply reader-output normalisation to PDF reads when it is enabled.",
    parameters=NoParams,
    inputs=(_port("documents", _DOCUMENTS, "Documents from the read."),),
    outputs=(_port("documents", _DOCUMENTS, "Normalised documents."),),
    effect=EffectClass.PURE,
    bypass=BypassSpec(input_port="documents", output_port="documents"),
    index_shaping=True,
)

ENRICH = OperationDescriptor(
    operation_id="prepare.enrich",
    version=1,
    title="Extract metadata",
    family="prepare",
    description="Extract file-level metadata for unstructured reads with the owning store.",
    parameters=EnrichParams,
    inputs=(_port("documents", _DOCUMENTS, "Documents to enrich."),),
    outputs=(_port("documents", _DOCUMENTS, "Documents with file-level metadata."),),
    capabilities=("store",),
    effect=EffectClass.MODEL_CALL,
    bypass=BypassSpec(input_port="documents", output_port="documents"),
    lever_params={"taxonomy_mode": "metadata.taxonomy_mode"},
    index_shaping=True,
)

CHUNK = OperationDescriptor(
    operation_id="prepare.chunk",
    version=1,
    title="Split into chunks",
    family="prepare",
    description=(
        "Split documents with the registered strategy. Reader-declared Markdown uses "
        "the Markdown splitter."
    ),
    parameters=ChunkParams,
    inputs=(_port("documents", _DOCUMENTS, "Documents to split."),),
    outputs=(_port("chunks", _CHUNKS, "Chunks of one source."),),
    effect=EffectClass.PURE,
    lever_params={
        "chunk_size": "chunking.chunk_size",
        "chunk_overlap": "chunking.chunk_overlap",
        "markdown_chunk_size": "chunking.markdown_chunk_size",
    },
    index_shaping=True,
)

EMBED = OperationDescriptor(
    operation_id="embed.chunks",
    version=1,
    title="Embed chunks",
    family="embed",
    description=(
        "Stamp chunk lineage and embed with the host embedder. Malformed vectors fail "
        "here, before any write."
    ),
    parameters=NoParams,
    inputs=(_port("chunks", _CHUNKS, "Chunks of one source."),),
    outputs=(_port("chunks", _EMBEDDED, "Chunks with lineage and vectors."),),
    capabilities=("embedder",),
    effect=EffectClass.MODEL_CALL,
    index_shaping=True,
)

COMMIT = OperationDescriptor(
    operation_id="commit.source",
    version=1,
    title="Commit source",
    family="commit",
    description=(
        "Write, verify and clean stale rows of one source as one protected operation. "
        "Cancellation stops it only before it starts."
    ),
    parameters=CollectionParams,
    inputs=(_port("chunks", _EMBEDDED, "Embedded chunks of one source."),),
    outputs=(_port("summary", _SUMMARY, "Per-source outcome."),),
    capabilities=("store",),
    effect=EffectClass.SOURCE_COMMIT,
    collection_param="collection",
)

#: Every ingestion descriptor, in canonical order.
INGESTION_DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    DISCOVER,
    IDENTIFY,
    READ,
    NORMALISE,
    ENRICH,
    CHUNK,
    EMBED,
    COMMIT,
)

_CANONICAL_CHAIN = (
    ("discover", DISCOVER, "sources"),
    ("identify", IDENTIFY, "sources"),
    ("read", READ, "documents"),
    ("normalise", NORMALISE, "documents"),
    ("enrich", ENRICH, "documents"),
    ("chunk", CHUNK, "chunks"),
    ("embed", EMBED, "chunks"),
    ("commit", COMMIT, "summary"),
)

#: Unit split of the canonical graph: one pass per ``discover.sources`` item.
UNIT_NODE, UNIT_PORT = "discover", "sources"


def canonical_ingestion_definition(collection: str | None = None) -> PipelineDefinition:
    """Return the canonical ingestion graph (standard ``ingest_path_async``).

    Args:
        collection: Graph collection. ``None`` uses the host default.

    Returns:
        A definition with one graph input ``path`` and one output ``summary``.
    """
    nodes = [{"id": node_id, "operation": d.operation_id} for node_id, d, _ in _CANONICAL_CHAIN]
    edges = []
    for (src, _d, out_port), (dst, descriptor, _o) in zip(
        _CANONICAL_CHAIN, _CANONICAL_CHAIN[1:], strict=False
    ):
        edges.append(
            {
                "source": {"node": src, "port": out_port},
                "target": {"node": dst, "port": descriptor.inputs[0].name},
            }
        )
    graph = {
        "schema_version": 1,
        "collection": collection,
        "nodes": nodes,
        "edges": edges,
        "inputs": [
            {
                "name": "path",
                "kind": "sources",
                "targets": [{"node": "discover", "port": "sources"}],
            }
        ],
        "outputs": [{"name": "summary", "source": {"node": "commit", "port": "summary"}}],
    }
    return parse_definition({"graph": graph})
