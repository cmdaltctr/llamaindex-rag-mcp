"""Graph adapters for the Retrieve, Combine/select and Context families.

This module holds the Combine/select and Context adapters and the single
registration entry point. The Retrieve adapters live in
:mod:`~omrs.core.retrieval.graph_adapters_retrieve`, the descriptors in
:mod:`~omrs.core.retrieval.graph_adapters_catalogue`, and the port values
in :mod:`~omrs.core.retrieval.graph_adapters_values`.

Each adapter wraps the existing retrieval algorithm through the shared
seams in :mod:`omrs.core.retrieval.operations` and the strategy
registries. No ranking, RRF, ÷30 transform or filtering rule is written
twice: ``search()`` and these adapters call the same functions
(``add-local-web-pipeline-workspace`` task 3.2, design D2 and D4).

Adapters take resources only from ``context.resource`` (``store``,
``embedder``, ``reranker``) and settings only from ``context.settings``.
They never read a process default. Blocking calls run in a worker thread,
and each adapter checks cancellation before its expensive step. Empty
rankings are valid data and flow on. A reranker failure is a
``NodeOutput.fallback`` outcome, not an exception.

Importing this module loads no concrete strategy module: dense
retrieval and fusion resolve through ``registry.get``, sparse backends
through the sparse registry, and the reranker is a host resource.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ..pipelines import (
    SCORE_KIND_DENSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    NodeContext,
    NodeOutput,
    PayloadProvenance,
)
from . import operations as ops
from .assembly import assemble, promote_assembly_diagnostics
from .graph_adapters_catalogue import register_descriptors
from .graph_adapters_retrieve import (
    dense_adapter,
    new_evidence,
    prepare_query_adapter,
    ranked_summary,
    sparse_adapter,
)
from .graph_adapters_values import (
    SCORE_KIND_SPARSE_RANK,
    ContextBundle,
    PreparedQuery,
    RankedEvidence,
    raise_if_cancelled,
    required_resource,
    source_ids,
)
from .registry import get as _retrieval_get

__all__ = [
    "SCORE_KIND_SPARSE_RANK",
    "ContextBundle",
    "PreparedQuery",
    "RankedEvidence",
    "register_retrieval_operations",
]


# ── Combine / select ──────────────────────────────────────────────────


def _fuse(
    dense: RankedEvidence | None,
    other: RankedEvidence | None,
    *,
    dense_threshold: float,
    rrf_k: int,
    fetch_k: int,
) -> list[dict]:
    """Apply dense eligibility, then registered RRF, then the pool cut."""
    dense_rows = dense.row_copies() if dense is not None else []
    other_rows = other.row_copies() if other is not None else []
    dense_rows, other_rows = ops.apply_dense_eligibility(dense_rows, other_rows, dense_threshold)
    return _retrieval_get("fusion")(dense_rows, other_rows, k=rrf_k)[:fetch_k]


def _split_roles(ranked: tuple[RankedEvidence, ...]) -> tuple[RankedEvidence | None, ...]:
    dense = [ev for ev in ranked if ev.score_kind == SCORE_KIND_DENSE]
    other = [ev for ev in ranked if ev.score_kind != SCORE_KIND_DENSE]
    if len(dense) > 1 or len(other) > 1:
        raise ValueError(
            "RRF fusion takes one dense ranking and one other ranking; connect one dense "
            f"and one sparse branch (got {len(dense)} dense and {len(other)} other)."
        )
    queries = {(ev.query.text, ev.query.collection) for ev in ranked}
    if len(queries) != 1:
        raise ValueError("RRF fusion inputs come from different queries or collections.")
    return (dense[0] if dense else None, other[0] if other else None)


async def rrf_adapter(context: NodeContext, inputs: Mapping[str, Any], params: Any) -> NodeOutput:
    """Fuse a dense and a sparse ranking with the registered RRF."""
    ranked = tuple(inputs["ranked"])
    dense, other = _split_roles(ranked)
    query = (dense or other).query
    rrf_k = params.rrf_k or context.settings.retrieval.hybrid_rrf_k
    first_stage = ops.first_stage_dense_threshold(query.similarity_threshold, rerank=query.rerank)
    raise_if_cancelled(context)
    rows = _fuse(dense, other, dense_threshold=first_stage, rrf_k=rrf_k, fetch_k=query.fetch_k)
    evidence = new_evidence(
        rows,
        query,
        SCORE_KIND_RRF,
        embedding=dense.provenance.embedding if dense is not None else None,
        fused=True,
        sparse_backend=other.sparse_backend if other is not None else None,
        dense_branch=dense,
        sparse_branch=other,
        rrf_k=rrf_k,
    )
    summary = {**ranked_summary(evidence, {}), "dense_eligibility_threshold": first_stage}
    return NodeOutput(values={"evidence": evidence}, summary=summary)


async def rerank_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: Any
) -> NodeOutput:
    """Re-score evidence with the host reranker, or pass it through."""
    evidence: RankedEvidence = inputs["evidence"]
    enabled = evidence.query.rerank if params.enabled is None else params.enabled
    if not enabled or not evidence.rows:
        reason = "disabled by node parameter" if params.enabled is False else evidence.rerank_reason
        summary = {"reranked": False, "reason": reason, "rows": len(evidence.rows)}
        return NodeOutput(values={"evidence": evidence}, summary=summary)
    reranker = required_resource(context, "reranker")
    timings: dict[str, float] = {}
    raise_if_cancelled(context)
    outcome = await asyncio.to_thread(
        ops.run_reranker,
        evidence.query.text,
        evidence.row_copies(),
        top_k=evidence.query.top_k,
        settings=context.settings,
        reranker=reranker,
        timing_report=timings,
    )
    succeeded = ops.rerank_succeeded(True, outcome.rows)
    fallback = None
    if not succeeded:
        fallback = outcome.failure_reason or "The reranker did not re-score every row."
    result = evidence.with_rows(
        outcome.rows,
        score_kind=SCORE_KIND_RERANK if succeeded else evidence.score_kind,
        reranked=succeeded,
        rerank_reason=outcome.failure_reason or evidence.rerank_reason,
        rerank_backend=outcome.backend,
    )
    summary = {
        **ranked_summary(result, timings),
        "reranked": succeeded,
        "rerank_backend": outcome.backend,
    }
    return NodeOutput(values={"evidence": result}, fallback=fallback, summary=summary)


async def threshold_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: Any
) -> NodeOutput:
    """Apply the score-kind-aware threshold, then rank and keep ``top_k``."""
    evidence: RankedEvidence = inputs["evidence"]
    query = evidence.query
    if not (evidence.reranked or evidence.fused or evidence.score_kind == SCORE_KIND_DENSE):
        raise ValueError(
            f"A dense similarity threshold cannot apply to score kind {evidence.score_kind!r}. "
            "Connect dense, fused or reranked evidence."
        )
    raise_if_cancelled(context)
    rows = evidence.row_copies()
    fallback = None
    if ops.needs_dense_fallback(
        rerank=query.rerank,
        hybrid=evidence.fused,
        succeeded=evidence.reranked,
        similarity_threshold=query.similarity_threshold,
    ):
        # Same rule as search(): an unsuccessful hybrid rerank returns to the
        # dense-threshold-before-fusion rule over the same branch rankings.
        rows = _fuse(
            evidence.dense_branch,
            evidence.sparse_branch,
            dense_threshold=query.similarity_threshold,
            rrf_k=evidence.rrf_k or context.settings.retrieval.hybrid_rrf_k,
            fetch_k=query.fetch_k,
        )
        fallback = "Reranking did not succeed; the dense threshold gated fusion instead."
    rows, threshold_kind = ops.apply_score_threshold(
        rows, query.similarity_threshold, succeeded=evidence.reranked, hybrid=evidence.fused
    )
    rows = ops.rank_and_truncate(rows, query.top_k)
    result = evidence.with_rows(rows, dense_branch=None, sparse_branch=None)
    summary = {
        **ranked_summary(result, {}),
        "threshold_score_kind": threshold_kind,
        "rerank_reason": result.rerank_reason,
        "rerank_backend": result.rerank_backend,
    }
    return NodeOutput(values={"evidence": result}, fallback=fallback, summary=summary)


# ── Context ───────────────────────────────────────────────────────────


async def context_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: Any
) -> NodeOutput:
    """Expand lineage neighbours, merge overlap and assemble the context."""
    evidence: RankedEvidence = inputs["evidence"]
    store = required_resource(context, "store")
    raise_if_cancelled(context)
    rows = await asyncio.to_thread(
        assemble,
        evidence.row_copies(),
        chunk_overlap=context.settings.chunking.chunk_overlap,
        expand_window=params.expand_window,
        store=store,
        collection=evidence.query.collection,
    )
    markers = [dict(row) for row in rows]
    promote_assembly_diagnostics(markers)
    assembly = tuple(
        {k: m[k] for k in ("assembly_merged", "assembly_chunk_count", "assembly_expanded")}
        for m in markers
    )
    provenance = PayloadProvenance(
        collection=evidence.query.collection,
        source_ids=source_ids(rows),
        score_kind=evidence.score_kind,
        embedding=evidence.provenance.embedding,
    )
    bundle = ContextBundle(rows=tuple(rows), provenance=provenance, assembly=assembly)
    summary = {
        "rows": len(rows),
        "merged": sum(1 for m in assembly if m["assembly_merged"]),
        "expanded": sum(1 for m in assembly if m["assembly_expanded"]),
        "collection": evidence.query.collection,
    }
    return NodeOutput(values={"context": bundle}, summary=summary)


# ── Registration ──────────────────────────────────────────────────────


def register_retrieval_operations(catalogue: Any) -> None:
    """Register every retrieval operation on ``catalogue``.

    Args:
        catalogue: The composition root's
            :class:`~omrs.core.pipelines.OperationCatalogue`.
    """
    register_descriptors(
        catalogue,
        prepare=prepare_query_adapter,
        dense=dense_adapter,
        sparse=sparse_adapter,
        rrf=rrf_adapter,
        rerank=rerank_adapter,
        threshold=threshold_adapter,
        context=context_adapter,
    )
