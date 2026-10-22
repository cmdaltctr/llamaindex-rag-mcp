"""Operation descriptors for the retrieval graph adapters.

Each descriptor publishes one retrieval operation: its parameter schema,
typed ports, capabilities, effect and, for the reranker, the bypass that
passes ranked evidence through when the node is disabled. The adapters
live in :mod:`omrs.core.retrieval.graph_adapters`; this module holds only
the contracts, so the adapter module stays small.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..pipelines import (
    BypassSpec,
    Cardinality,
    EffectClass,
    OperationAdapter,
    OperationDescriptor,
    PortSpec,
    PortType,
)
from .graph_adapters_values import (
    ANY_EVIDENCE_IN,
    CONTEXT_OUT,
    DENSE_OUT,
    FUSED_OUT,
    PREPARED_QUERY_OUT,
    QUERY_IN,
    SCORED_EVIDENCE,
    SPARSE_OUT,
)


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrepareQueryParams(_Params):
    """Levers for query preparation. ``None`` inherits the node settings."""

    collection: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: bool | None = None
    fetch_k: int | None = Field(default=None, ge=1)
    metadata_filter: dict[str, Any] | None = None


class CollectionParams(_Params):
    """Collection for a retrieval node that receives raw query text."""

    collection: str | None = None


class RrfParams(_Params):
    """RRF constant. ``None`` inherits ``retrieval.hybrid_rrf_k``."""

    rrf_k: int | None = Field(default=None, ge=1)


class RerankParams(_Params):
    """Rerank switch. ``None`` follows the prepared query decision."""

    enabled: bool | None = None


class NoParams(_Params):
    """Operation without parameters."""


class ContextParams(_Params):
    """Neighbour expansion per side of each retrieved chunk."""

    expand_window: int = Field(default=0, ge=0, le=10)


def _port(
    name: str, port_type: PortType, description: str, card: Cardinality = Cardinality.ONE
) -> PortSpec:
    return PortSpec(name=name, type=port_type, cardinality=card, description=description)


_QUERY = _port("query", QUERY_IN, "Query text or a prepared query.")
_EVIDENCE_IN = _port("evidence", SCORED_EVIDENCE, "Scored ranked evidence.")


def _descriptors() -> tuple[OperationDescriptor, ...]:
    return (
        OperationDescriptor(
            operation_id="retrieve.prepare_query",
            version=1,
            title="Prepare query",
            family="retrieve",
            description="Resolve top-k, threshold, rerank policy and the candidate pool once.",
            parameters=PrepareQueryParams,
            inputs=(_port("query", QUERY_IN, "Query text."),),
            outputs=(_port("query", PREPARED_QUERY_OUT, "Prepared query."),),
            capabilities=("store",),
            effect=EffectClass.READ_ONLY,
            collection_param="collection",
            lever_params={
                "top_k": "retrieval.top_k",
                "similarity_threshold": "retrieval.similarity_threshold",
                "rerank": "retrieval.rerank_enabled",
            },
        ),
        OperationDescriptor(
            operation_id="retrieve.dense",
            version=1,
            title="Dense retrieval",
            family="retrieve",
            description="Embed the query and read the nearest chunks.",
            parameters=CollectionParams,
            inputs=(_QUERY,),
            outputs=(_port("evidence", DENSE_OUT, "Dense similarity ranking."),),
            capabilities=("embedder", "store"),
            effect=EffectClass.MODEL_CALL,
            collection_param="collection",
        ),
        OperationDescriptor(
            operation_id="retrieve.sparse",
            version=1,
            title="Sparse retrieval",
            family="retrieve",
            description="Rank chunks by keywords with the configured sparse backend.",
            parameters=CollectionParams,
            inputs=(_QUERY,),
            outputs=(_port("evidence", SPARSE_OUT, "Rank-only sparse ranking."),),
            capabilities=("store",),
            effect=EffectClass.READ_ONLY,
            collection_param="collection",
        ),
        OperationDescriptor(
            operation_id="combine.rrf",
            version=1,
            title="Reciprocal rank fusion",
            family="combine",
            description="Fuse one dense and one sparse ranking.",
            parameters=RrfParams,
            inputs=(_port("ranked", ANY_EVIDENCE_IN, "Rankings to fuse.", Cardinality.MANY),),
            outputs=(_port("evidence", FUSED_OUT, "Fused ranking with rank provenance."),),
            effect=EffectClass.PURE,
            lever_params={"rrf_k": "retrieval.hybrid_rrf_k"},
        ),
        OperationDescriptor(
            operation_id="select.rerank",
            version=1,
            title="Cross-encoder rerank",
            family="select",
            description="Re-score evidence; a failure keeps the pre-rerank scores.",
            parameters=RerankParams,
            inputs=(_EVIDENCE_IN,),
            outputs=(_port("evidence", SCORED_EVIDENCE, "Reranked or unchanged evidence."),),
            capabilities=("reranker",),
            effect=EffectClass.MODEL_CALL,
            bypass=BypassSpec(input_port="evidence", output_port="evidence"),
            lever_params={"enabled": "retrieval.rerank_enabled"},
        ),
        OperationDescriptor(
            operation_id="select.threshold",
            version=1,
            title="Threshold and top-k",
            family="select",
            description="Apply the score-kind-aware threshold, then keep top-k.",
            parameters=NoParams,
            inputs=(_EVIDENCE_IN,),
            outputs=(_port("evidence", SCORED_EVIDENCE, "Selected evidence."),),
            effect=EffectClass.PURE,
        ),
        OperationDescriptor(
            operation_id="context.assemble",
            version=1,
            title="Assemble context",
            family="context",
            description="Expand lineage neighbours and merge overlapping chunks.",
            parameters=ContextParams,
            inputs=(_port("evidence", ANY_EVIDENCE_IN, "Selected evidence."),),
            outputs=(_port("context", CONTEXT_OUT, "Assembled context rows."),),
            capabilities=("store",),
            effect=EffectClass.READ_ONLY,
        ),
    )


def register_descriptors(catalogue: Any, **adapters: OperationAdapter) -> None:
    """Register each descriptor with its adapter.

    Args:
        catalogue: The operation catalogue.
        **adapters: ``prepare``, ``dense``, ``sparse``, ``rrf``, ``rerank``,
            ``threshold`` and ``context`` adapters.
    """
    prepare, dense, sparse, rrf, rerank, threshold, context = _descriptors()
    catalogue.register(prepare, adapters["prepare"])
    catalogue.register(dense, adapters["dense"])
    catalogue.register(sparse, adapters["sparse"])
    catalogue.register(rrf, adapters["rrf"])
    catalogue.register(rerank, adapters["rerank"])
    catalogue.register(threshold, adapters["threshold"])
    catalogue.register(context, adapters["context"])
