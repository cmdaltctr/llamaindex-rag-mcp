"""Port values and port types for the retrieval graph adapters.

The graph runner moves these frozen values between retrieval nodes. They
carry what the port contracts promise: the collection, the score kind of
a ranked list, the embedding identity of dense evidence, and the chunk
lineage fields each row already holds. Rows are plain dicts in the same
shape ``search()`` uses. An adapter copies rows before it changes them, so
a value shared by two branches never changes under either branch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ..pipelines import (
    SCORE_KIND_DENSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    SCORE_KIND_SPARSE_RANK,
    NodeContext,
    PayloadProvenance,
    PipelineCancelledError,
    PortKind,
    PortType,
    Provenance,
)

_LINEAGE = frozenset({Provenance.COLLECTION, Provenance.CHUNK_LINEAGE})

QUERY_IN = PortType(kind=PortKind.QUERY)
PREPARED_QUERY_OUT = PortType(kind=PortKind.QUERY, provenance=frozenset({Provenance.COLLECTION}))
DENSE_OUT = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=_LINEAGE,
    score_kinds=frozenset({SCORE_KIND_DENSE}),
    embedding_identity=True,
)
SPARSE_OUT = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=_LINEAGE,
    score_kinds=frozenset({SCORE_KIND_SPARSE_RANK}),
)
ANY_EVIDENCE_IN = PortType(kind=PortKind.RANKED_EVIDENCE, provenance=_LINEAGE)
FUSED_OUT = PortType(
    kind=PortKind.RANKED_EVIDENCE, provenance=_LINEAGE, score_kinds=frozenset({SCORE_KIND_RRF})
)
#: Scored evidence: what the reranker accepts and what selection reads.
SCORED_EVIDENCE = PortType(
    kind=PortKind.RANKED_EVIDENCE,
    provenance=_LINEAGE,
    score_kinds=frozenset({SCORE_KIND_DENSE, SCORE_KIND_RRF, SCORE_KIND_RERANK}),
)
CONTEXT_OUT = PortType(kind=PortKind.CONTEXT, provenance=_LINEAGE)


@dataclass(frozen=True)
class PreparedQuery:
    """A query with its levers, rerank decision and candidate pool resolved.

    Attributes:
        text: Raw query text. Dense retrieval adds any query instruction.
        collection: Collection the query runs against.
        top_k: Rows kept by selection.
        fetch_k: First-stage candidate pool size.
        hybrid: Resolved hybrid preference. Adapters follow the graph
            shape; a template chooser can read this value.
        rerank: Effective rerank decision. It sizes the pool and decides
            whether the dense threshold gates fusion.
        rerank_reason: Why ``rerank`` has its value.
        similarity_threshold: Caller threshold on the dense scale.
        collection_count: Chunks in the collection when prepared.
        metadata_filter: Optional store ``where`` clause.
    """

    text: str
    collection: str
    top_k: int
    fetch_k: int
    hybrid: bool
    rerank: bool
    rerank_reason: str
    similarity_threshold: float
    collection_count: int
    metadata_filter: Mapping[str, Any] | None = None

    def filter_copy(self) -> dict | None:
        """Return a fresh copy of the metadata filter for a store call."""
        return None if self.metadata_filter is None else dict(self.metadata_filter)


@dataclass(frozen=True)
class RankedEvidence:
    """A ranked list of retrieval rows and its guarantees.

    Attributes:
        rows: Rows in rank order, in the ``search()`` row shape.
        query: The prepared query that produced the rows.
        provenance: Collection, source ids, score kind and embedding.
        fused: Whether RRF produced the order. Fused scores never meet a
            dense threshold after fusion.
        reranked: Whether a reranker re-scored every row.
        rerank_reason: Rerank decision or the reranker failure reason.
        rerank_backend: Backend name the reranker reported, if it ran.
        sparse_backend: Sparse backend that served the rows, if any.
        dense_branch: Dense input of a fusion, kept for the fallback.
        sparse_branch: Other input of a fusion, kept for the fallback.
        rrf_k: RRF constant used by the fusion.
    """

    rows: tuple[dict[str, Any], ...]
    query: PreparedQuery
    provenance: PayloadProvenance
    fused: bool = False
    reranked: bool = False
    rerank_reason: str = ""
    rerank_backend: str | None = None
    sparse_backend: str | None = None
    dense_branch: RankedEvidence | None = None
    sparse_branch: RankedEvidence | None = None
    rrf_k: int | None = None

    @property
    def score_kind(self) -> str | None:
        """Return the score kind every row carries."""
        return self.provenance.score_kind

    def row_copies(self) -> list[dict[str, Any]]:
        """Return shallow row copies an adapter may change."""
        return [dict(row) for row in self.rows]

    def with_rows(self, rows: Iterable[dict[str, Any]], **changes: Any) -> RankedEvidence:
        """Return a copy with new rows, refreshed source ids and ``changes``."""
        rows = tuple(rows)
        score_kind = changes.pop("score_kind", self.provenance.score_kind)
        provenance = replace(self.provenance, source_ids=source_ids(rows), score_kind=score_kind)
        return replace(self, rows=rows, provenance=provenance, **changes)


@dataclass(frozen=True)
class ContextBundle:
    """Assembled context rows ready for answering.

    Attributes:
        rows: Assembled rows with ranking and assembly diagnostics.
        provenance: Collection, source ids and the evidence score kind.
        assembly: Per-row assembly markers (merged, chunk count, expanded).
    """

    rows: tuple[dict[str, Any], ...]
    provenance: PayloadProvenance
    assembly: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def public_rows(self) -> list[dict[str, Any]]:
        """Return the rows in the public ``search()`` result shape."""
        from .pipeline import _strip_internal_result_fields

        return [_strip_internal_result_fields(row) for row in self.rows]


def source_ids(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return unique ``source_id`` lineage values in first-seen order."""
    seen: dict[str, None] = {}
    for row in rows:
        value = row.get("source_id")
        if value is not None:
            seen.setdefault(str(value), None)
    return tuple(seen)


def raise_if_cancelled(context: NodeContext) -> None:
    """Stop at a safe boundary when the run was cancelled.

    Raises:
        PipelineCancelledError: If cancellation was requested. The runner
            reports the node as cancelled, not failed.
    """
    if context.cancellation.cancelled:
        raise PipelineCancelledError(f"Run cancelled before node {context.node_id!r} finished.")


def required_resource(context: NodeContext, name: str) -> Any:
    """Return a host resource, refusing a ``None`` placeholder.

    Raises:
        LookupError: If the host did not supply the resource.
    """
    value = context.resource(name)
    if value is None:
        raise LookupError(f"Node {context.node_id!r} needs resource {name!r}, but it is None.")
    return value
