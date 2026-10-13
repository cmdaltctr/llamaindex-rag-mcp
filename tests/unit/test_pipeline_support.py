"""Shared fixture catalogue for pipeline contract tests.

The descriptors below mirror the first-release operation families with
provisional identifiers. They carry no domain implementation: adapters are
no-op coroutines. Other pipeline tests and the guide example test import
these helpers. The two tests at the end keep the fixture itself honest.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from omrg.core.pipelines import (
    READER_STRUCTURED,
    READER_TEXT_FORMAT,
    SCORE_KIND_DENSE,
    SCORE_KIND_NATIVE_SPARSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    BypassSpec,
    Cardinality,
    EffectClass,
    EmbeddingRef,
    HostContext,
    NodeOutput,
    OperationCatalogue,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
)

# ── Parameter models ──────────────────────────────────────────────────


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoParams(_Params):
    """Operation without parameters."""


class CollectionParams(_Params):
    collection: str | None = None


class DenseParams(CollectionParams):
    top_k: int | None = Field(default=None, ge=1)


class RerankParams(_Params):
    enabled: bool | None = None


class ThresholdParams(_Params):
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)


class ChunkParams(_Params):
    chunk_size: int | None = Field(default=None, ge=16)
    separator: str = "\n\n"


class AnswerParams(_Params):
    instructions: str = ""


# ── Port types ────────────────────────────────────────────────────────

LINEAGE = frozenset({Provenance.COLLECTION, Provenance.CHUNK_LINEAGE})
QUERY = PortType(kind=PortKind.QUERY)
DENSE_EVIDENCE = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=LINEAGE,
    score_kinds=frozenset({SCORE_KIND_DENSE}),
    embedding_identity=True,
)
SPARSE_EVIDENCE = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=LINEAGE,
    score_kinds=frozenset({SCORE_KIND_NATIVE_SPARSE}),
)
FUSED_EVIDENCE = PortType(
    kind=PortKind.RANKED_EVIDENCE, provenance=LINEAGE, score_kinds=frozenset({SCORE_KIND_RRF})
)
ANY_EVIDENCE = PortType(kind=PortKind.RANKED_EVIDENCE, provenance=LINEAGE)
RERANKED_EVIDENCE = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=LINEAGE,
    score_kinds=frozenset(
        {SCORE_KIND_RERANK, SCORE_KIND_DENSE, SCORE_KIND_RRF, SCORE_KIND_NATIVE_SPARSE}
    ),
)
CONTEXT = PortType(kind=PortKind.CONTEXT, provenance=LINEAGE)
ANSWER = PortType(kind=PortKind.ANSWER, provenance=LINEAGE)
RAW_SOURCES = PortType(kind=PortKind.SOURCES)
SOURCES = PortType(kind=PortKind.SOURCES, provenance=frozenset({Provenance.SOURCE}))
DOCUMENTS = PortType(
    kind=PortKind.DOCUMENTS,
    provenance=frozenset({Provenance.SOURCE}),
    reader_declarations=frozenset({READER_TEXT_FORMAT, READER_STRUCTURED}),
)
DOCUMENTS_NEEDING_FORMAT = PortType(
    kind=PortKind.DOCUMENTS,
    provenance=frozenset({Provenance.SOURCE}),
    reader_declarations=frozenset({READER_TEXT_FORMAT}),
)
CHUNKS = PortType(
    kind=PortKind.CHUNKS, provenance=frozenset({Provenance.SOURCE, Provenance.CHUNK_LINEAGE})
)
EMBEDDED = PortType(
    kind=PortKind.EMBEDDED_CHUNKS,
    provenance=frozenset({Provenance.SOURCE, Provenance.CHUNK_LINEAGE}),
    embedding_identity=True,
)
SUMMARY = PortType(kind=PortKind.COMMIT_SUMMARY, provenance=frozenset({Provenance.COLLECTION}))


async def noop_adapter(context: Any, inputs: Mapping[str, Any], params: BaseModel) -> NodeOutput:
    """Return no values; fixtures never execute."""
    return NodeOutput(values={})


def _port(name: str, port_type: PortType, card: Cardinality = Cardinality.ONE) -> PortSpec:
    return PortSpec(name=name, type=port_type, cardinality=card)


def fixture_descriptors() -> list[OperationDescriptor]:
    """Return the provisional first-release descriptors."""
    return [
        OperationDescriptor(
            operation_id="retrieve.dense",
            version=1,
            title="Dense retrieval",
            family="retrieve",
            parameters=DenseParams,
            inputs=(_port("query", QUERY),),
            outputs=(_port("evidence", DENSE_EVIDENCE),),
            capabilities=("embedder", "store"),
            effect=EffectClass.READ_ONLY,
            collection_param="collection",
            lever_params={"top_k": "retrieval.top_k"},
        ),
        OperationDescriptor(
            operation_id="retrieve.sparse",
            version=1,
            title="Sparse retrieval",
            family="retrieve",
            parameters=CollectionParams,
            inputs=(_port("query", QUERY),),
            outputs=(_port("evidence", SPARSE_EVIDENCE),),
            capabilities=("store", "sparse_backend"),
            effect=EffectClass.READ_ONLY,
            collection_param="collection",
        ),
        OperationDescriptor(
            operation_id="combine.rrf",
            version=1,
            title="Reciprocal rank fusion",
            family="combine",
            parameters=NoParams,
            inputs=(_port("ranked", ANY_EVIDENCE, Cardinality.MANY),),
            outputs=(_port("evidence", FUSED_EVIDENCE),),
            effect=EffectClass.PURE,
        ),
        OperationDescriptor(
            operation_id="select.rerank",
            version=1,
            title="Cross-encoder rerank",
            family="select",
            parameters=RerankParams,
            inputs=(_port("evidence", ANY_EVIDENCE),),
            outputs=(_port("evidence", RERANKED_EVIDENCE),),
            capabilities=("reranker",),
            effect=EffectClass.MODEL_CALL,
            bypass=BypassSpec(input_port="evidence", output_port="evidence"),
            lever_params={"enabled": "retrieval.rerank_enabled"},
        ),
        OperationDescriptor(
            operation_id="select.dense_threshold",
            version=1,
            title="Dense similarity threshold",
            family="select",
            parameters=ThresholdParams,
            inputs=(_port("evidence", DENSE_EVIDENCE),),
            outputs=(_port("evidence", DENSE_EVIDENCE),),
            effect=EffectClass.PURE,
            bypass=BypassSpec(input_port="evidence", output_port="evidence"),
        ),
        OperationDescriptor(
            operation_id="context.assemble",
            version=1,
            title="Assemble context",
            family="context",
            parameters=NoParams,
            inputs=(_port("evidence", ANY_EVIDENCE),),
            outputs=(_port("context", CONTEXT),),
            effect=EffectClass.READ_ONLY,
        ),
        OperationDescriptor(
            operation_id="answer.synthesise",
            version=1,
            title="Synthesise answer",
            family="answer",
            parameters=AnswerParams,
            inputs=(_port("query", QUERY), _port("context", CONTEXT)),
            outputs=(_port("answer", ANSWER),),
            capabilities=("completion",),
            effect=EffectClass.MODEL_CALL,
            free_text_params=frozenset({"instructions"}),
        ),
        OperationDescriptor(
            operation_id="source.discover",
            version=1,
            title="Discover sources",
            family="sources",
            parameters=NoParams,
            inputs=(_port("sources", RAW_SOURCES),),
            outputs=(_port("sources", SOURCES),),
            effect=EffectClass.READ_ONLY,
        ),
        OperationDescriptor(
            operation_id="read.document",
            version=1,
            title="Read document",
            family="read",
            parameters=NoParams,
            inputs=(_port("sources", SOURCES),),
            outputs=(_port("documents", DOCUMENTS),),
            effect=EffectClass.READ_ONLY,
        ),
        OperationDescriptor(
            operation_id="prepare.chunk",
            version=1,
            title="Chunk documents",
            family="prepare",
            parameters=ChunkParams,
            inputs=(_port("documents", DOCUMENTS_NEEDING_FORMAT),),
            outputs=(_port("chunks", CHUNKS),),
            effect=EffectClass.PURE,
            index_shaping=True,
            lever_params={"chunk_size": "chunking.chunk_size"},
        ),
        OperationDescriptor(
            operation_id="embed.chunks",
            version=1,
            title="Embed chunks",
            family="embed",
            parameters=NoParams,
            inputs=(_port("chunks", CHUNKS),),
            outputs=(_port("chunks", EMBEDDED),),
            capabilities=("embedder",),
            effect=EffectClass.MODEL_CALL,
            index_shaping=True,
        ),
        OperationDescriptor(
            operation_id="commit.source",
            version=1,
            title="Commit source",
            family="commit",
            parameters=CollectionParams,
            inputs=(_port("chunks", EMBEDDED),),
            outputs=(_port("summary", SUMMARY),),
            capabilities=("store",),
            effect=EffectClass.SOURCE_COMMIT,
            collection_param="collection",
        ),
    ]


def fixture_catalogue() -> OperationCatalogue:
    """Return a catalogue with every fixture descriptor registered."""
    catalogue = OperationCatalogue()
    for descriptor in fixture_descriptors():
        catalogue.register(descriptor, noop_adapter)
    return catalogue


HOST_EMBEDDING = EmbeddingRef(provider="llamacpp", model="qwen3-embedding", dimensions=1024)
ALL_CAPABILITIES: dict[str, str | None] = {
    "embedder": None,
    "store": None,
    "sparse_backend": None,
    "reranker": None,
    "completion": None,
}


class FakeCollections:
    """In-memory collection view returning stored embedding identities."""

    def __init__(self, identities: Mapping[str, EmbeddingRef | None] | None = None) -> None:
        self._identities = dict(identities or {})

    def embedding_identity(self, collection: str) -> EmbeddingRef | None:
        return self._identities.get(collection)


def fixture_host(
    *,
    capabilities: Mapping[str, str | None] | None = None,
    identities: Mapping[str, EmbeddingRef | None] | None = None,
) -> HostContext:
    """Return a host context with every fixture capability available."""
    return HostContext(
        capabilities=dict(ALL_CAPABILITIES if capabilities is None else capabilities),
        embedding=HOST_EMBEDDING,
        collections=FakeCollections(identities),
        default_collection="documents",
    )


def search_graph() -> dict[str, Any]:
    """Return a hybrid search-and-answer graph document as plain data."""
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "dense", "operation": "retrieve.dense"},
            {"id": "sparse", "operation": "retrieve.sparse"},
            {"id": "fuse", "operation": "combine.rrf"},
            {"id": "rerank", "operation": "select.rerank"},
            {"id": "context", "operation": "context.assemble"},
            {"id": "answer", "operation": "answer.synthesise"},
        ],
        "edges": [
            {
                "source": {"node": "dense", "port": "evidence"},
                "target": {"node": "fuse", "port": "ranked"},
            },
            {
                "source": {"node": "sparse", "port": "evidence"},
                "target": {"node": "fuse", "port": "ranked"},
            },
            {
                "source": {"node": "fuse", "port": "evidence"},
                "target": {"node": "rerank", "port": "evidence"},
            },
            {
                "source": {"node": "rerank", "port": "evidence"},
                "target": {"node": "context", "port": "evidence"},
            },
            {
                "source": {"node": "context", "port": "context"},
                "target": {"node": "answer", "port": "context"},
            },
        ],
        "inputs": [
            {
                "name": "query",
                "kind": "query",
                "targets": [
                    {"node": "dense", "port": "query"},
                    {"node": "sparse", "port": "query"},
                    {"node": "answer", "port": "query"},
                ],
            }
        ],
        "outputs": [{"name": "answer", "source": {"node": "answer", "port": "answer"}}],
    }


def ingest_graph() -> dict[str, Any]:
    """Return a single-destination ingestion graph document as plain data."""
    return {
        "schema_version": 1,
        "collection": "documents",
        "nodes": [
            {"id": "discover", "operation": "source.discover"},
            {"id": "read", "operation": "read.document"},
            {"id": "chunk", "operation": "prepare.chunk"},
            {"id": "embed", "operation": "embed.chunks"},
            {"id": "commit", "operation": "commit.source"},
        ],
        "edges": [
            {
                "source": {"node": "discover", "port": "sources"},
                "target": {"node": "read", "port": "sources"},
            },
            {
                "source": {"node": "read", "port": "documents"},
                "target": {"node": "chunk", "port": "documents"},
            },
            {
                "source": {"node": "chunk", "port": "chunks"},
                "target": {"node": "embed", "port": "chunks"},
            },
            {
                "source": {"node": "embed", "port": "chunks"},
                "target": {"node": "commit", "port": "chunks"},
            },
        ],
        "inputs": [
            {
                "name": "path",
                "kind": "sources",
                "targets": [{"node": "discover", "port": "sources"}],
            }
        ],
        "outputs": [{"name": "summary", "source": {"node": "commit", "port": "summary"}}],
    }


def test_fixture_catalogue_registers_every_descriptor() -> None:
    """Every fixture descriptor registers without a contract error."""
    catalogue = fixture_catalogue()
    assert len(catalogue.descriptors()) == len(fixture_descriptors())


def test_fixture_graphs_parse() -> None:
    """Both fixture graphs are valid graph documents."""
    from omrg.core.pipelines import GraphDocument

    assert GraphDocument.model_validate(search_graph()).schema_version == 1
    assert GraphDocument.model_validate(ingest_graph()).collection == "documents"
