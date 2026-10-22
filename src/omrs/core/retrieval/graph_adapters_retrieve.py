"""Graph adapters for the Retrieve family: prepare, dense and sparse.

Query preparation resolves levers, the rerank decision and the candidate
pool once through the shared seams in :mod:`omrs.core.retrieval.operations`.
Dense retrieval resolves the registered ``dense`` strategy and sparse
retrieval the shared sparse policy runner, so the graph and ``search()``
run the same code. Resources come only from ``context.resource`` and
settings only from ``context.settings``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ..pipelines import (
    SCORE_KIND_DENSE,
    EmbeddingRef,
    NodeContext,
    NodeOutput,
    PayloadProvenance,
)
from . import operations as ops
from .graph_adapters_values import (
    SCORE_KIND_SPARSE_RANK,
    PreparedQuery,
    RankedEvidence,
    raise_if_cancelled,
    required_resource,
    source_ids,
)
from .registry import get as _retrieval_get
from .sparse_dispatch import sparse_policy_runner

# ── Query preparation ─────────────────────────────────────────────────


def _collection(context: NodeContext, explicit: str | None) -> str:
    return explicit or context.collection or context.settings.collection_name


async def _prepare(
    context: NodeContext,
    text: str,
    *,
    collection: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    fetch_k: int | None = None,
    metadata_filter: Mapping[str, Any] | None = None,
) -> PreparedQuery:
    settings = context.settings
    levers = ops.resolve_search_levers(
        settings, top_k=top_k, similarity_threshold=similarity_threshold
    )
    # Graph settings are always explicit, so the resolved profile carries
    # the reranker decision, as it does for Engine.search().
    effective_rerank, reason = ops.resolve_rerank_decision(
        rerank, text, settings, caller_settings=settings
    )
    store = required_resource(context, "store")
    raise_if_cancelled(context)
    count = await asyncio.to_thread(store.count, collection)
    fetch = ops.size_candidate_pool(
        levers.top_k, effective_rerank, count, settings, fetch_k_override=fetch_k
    )
    return PreparedQuery(
        text=text,
        collection=collection,
        top_k=levers.top_k,
        fetch_k=fetch,
        hybrid=levers.hybrid,
        rerank=effective_rerank,
        rerank_reason=reason,
        similarity_threshold=levers.similarity_threshold,
        collection_count=count,
        metadata_filter=None if metadata_filter is None else dict(metadata_filter),
    )


async def _ensure_prepared(
    context: NodeContext, value: Any, collection: str | None
) -> PreparedQuery:
    """Accept raw query text or a prepared query on a ``query`` port."""
    if isinstance(value, PreparedQuery):
        if collection is not None and collection != value.collection:
            raise ValueError(
                f"Node {context.node_id!r} names collection {collection!r}, but its query "
                f"was prepared for {value.collection!r}. Remove one of the two settings."
            )
        return value
    if isinstance(value, str):
        return await _prepare(context, value, collection=_collection(context, collection))
    raise TypeError(f"Node {context.node_id!r} needs query text or a prepared query.")


async def prepare_query_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: Any
) -> NodeOutput:
    """Resolve levers, rerank policy and the candidate pool once."""
    query = await _prepare(
        context,
        inputs["query"],
        collection=_collection(context, params.collection),
        top_k=params.top_k,
        similarity_threshold=params.similarity_threshold,
        rerank=params.rerank,
        fetch_k=params.fetch_k,
        metadata_filter=params.metadata_filter,
    )
    summary = {
        "collection": query.collection,
        "top_k": query.top_k,
        "fetch_k": query.fetch_k,
        "rerank": query.rerank,
        "rerank_reason": query.rerank_reason,
        "collection_count": query.collection_count,
    }
    return NodeOutput(values={"query": query}, summary=summary)


# ── Retrieve ──────────────────────────────────────────────────────────


def new_evidence(
    rows: list[dict], query: PreparedQuery, score_kind: str, **fields: Any
) -> RankedEvidence:
    """Return ranked evidence with collection, source and score-kind provenance."""
    embedding = fields.pop("embedding", None)
    provenance = PayloadProvenance(
        collection=query.collection,
        source_ids=source_ids(rows),
        score_kind=score_kind,
        embedding=embedding,
    )
    return RankedEvidence(
        rows=tuple(rows),
        query=query,
        provenance=provenance,
        rerank_reason=query.rerank_reason,
        **fields,
    )


def ranked_summary(evidence: RankedEvidence, timings: Mapping[str, float]) -> dict[str, Any]:
    """Return the small JSON-safe event summary of a ranked output."""
    return {
        "rows": len(evidence.rows),
        "score_kind": evidence.score_kind,
        "collection": evidence.provenance.collection,
        "timings": dict(timings),
    }


async def dense_adapter(context: NodeContext, inputs: Mapping[str, Any], params: Any) -> NodeOutput:
    """Embed the query and read dense matches through the dense strategy."""
    query = await _ensure_prepared(context, inputs["query"], params.collection)
    embedder = required_resource(context, "embedder")
    model = getattr(embedder, "model_name", None) or type(embedder).__name__
    chosen = context.resources.get("embedding_identity")
    embedding = EmbeddingRef(
        provider=chosen.provider if chosen else context.settings.embed_provider,
        model=chosen.model if chosen else str(model),
    )
    timings: dict[str, float] = {}
    rows: list[dict] = []
    if query.collection_count > 0:
        store = required_resource(context, "store")
        embedding_block = context.settings.embedding
        raise_if_cancelled(context)
        rows = await asyncio.to_thread(
            _retrieval_get("dense"),
            store,
            query.collection,
            query.text,
            query.fetch_k,
            query.filter_copy(),
            norm_guard_enabled=embedding_block.norm_guard_enabled,
            norm_tolerance=embedding_block.norm_tolerance,
            timing_report=timings,
            embed_model=embedder,
            query_instruction=embedding_block.query_instruction,
            **({"embedding_identity": chosen} if chosen else {}),
        )
    evidence = new_evidence(rows, query, SCORE_KIND_DENSE, embedding=embedding)
    return NodeOutput(values={"evidence": evidence}, summary=ranked_summary(evidence, timings))


async def sparse_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: Any
) -> NodeOutput:
    """Run the configured sparse backend, with the existing BM25 safety net."""
    query = await _ensure_prepared(context, inputs["query"], params.collection)
    requested = context.settings.retrieval.hybrid_sparse_backend
    timings: dict[str, float] = {}
    report: dict[str, str] = {}
    rows: list[dict] = []
    if query.collection_count > 0:
        store = required_resource(context, "store")
        chosen = context.resources.get("embedding_identity")
        raise_if_cancelled(context)
        rows = await asyncio.to_thread(
            sparse_policy_runner(requested),
            query.collection,
            store,
            query.text,
            query.fetch_k,
            query.filter_copy(),
            report,
            timing_report=timings,
            **({"embedding_identity": chosen} if chosen else {}),
        )
    ran = report.get("sparse_backend", requested)
    fallback = None
    if ran != requested:
        fallback = f"Sparse backend {requested!r} could not serve the query; {ran!r} ran instead."
    evidence = new_evidence(rows, query, SCORE_KIND_SPARSE_RANK, sparse_backend=ran)
    summary = {**ranked_summary(evidence, timings), "sparse_backend": ran}
    return NodeOutput(values={"evidence": evidence}, fallback=fallback, summary=summary)
