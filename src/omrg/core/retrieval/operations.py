"""Shared retrieval operations: sizing, policy, filtering and fallback.

The standard :func:`~omrg.core.retrieval.pipeline.search` facade and the
graph adapters both call these functions, so each retrieval rule has one
implementation (``add-local-web-pipeline-workspace`` task 3.1, design D4).

Every function takes its settings, rows and reranker as arguments. None
reads a process default, and importing this module loads no concrete
strategy module: the reranker builder is imported only when a call needs
it. The calibrated ÷30 rerank threshold transform and the candidate-pool
formula stay in :mod:`omrg.core.retrieval.policy`; this module applies
them and adds no second copy.
"""

from __future__ import annotations

import threading
import time
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..vectordb.score import DENSE_SCORE_KIND
from .policy import _effective_threshold, _resolve_fetch_k, _resolve_rerank_policy

if TYPE_CHECKING:
    from ..settings import EffectiveSettings

#: Score kind of a row the cross-encoder re-scored successfully.
RERANK_SCORE_KIND = "reranker_sigmoid_v1"

# A reranker keeps its last failure reason on the instance. Runs that read at the
# same time share one reranker, so "rerank, then read the reason" must be one step.
_RERANK_LOCKS: weakref.WeakKeyDictionary[Any, threading.Lock] = weakref.WeakKeyDictionary()
_RERANK_LOCKS_GUARD = threading.Lock()


def _rerank_lock(reranker: Any) -> threading.Lock:
    """Return the lock that covers one reranker instance."""
    try:
        with _RERANK_LOCKS_GUARD:
            return _RERANK_LOCKS.setdefault(reranker, threading.Lock())
    except TypeError:  # an object that cannot be weakly referenced
        return _RERANK_LOCKS_GUARD


@dataclass(frozen=True)
class SearchLevers:
    """Operation levers after omitted values take the settings defaults.

    Attributes:
        top_k: Number of rows to return.
        hybrid: Whether dense and sparse rankings are fused.
        similarity_threshold: Caller threshold on the dense scale.
    """

    top_k: int
    hybrid: bool
    similarity_threshold: float


@dataclass(frozen=True)
class RerankOutcome:
    """Result of one reranker call.

    Attributes:
        rows: Rows returned by the reranker, with public ``reranked`` flags.
        backend: Backend name the reranker reports, if any.
        failure_reason: The reranker's own failure reason, if it failed.
    """

    rows: list[dict]
    backend: str | None
    failure_reason: str | None


def resolve_search_levers(
    settings: EffectiveSettings,
    *,
    top_k: int | None = None,
    hybrid: bool | None = None,
    similarity_threshold: float | None = None,
) -> SearchLevers:
    """Fill omitted levers from the injected settings.

    Only ``None`` means omitted; explicit falsy values (``hybrid=False``,
    ``similarity_threshold=0.0``) are kept.

    Args:
        settings: Resolved settings for this operation.
        top_k: Explicit result count, or ``None``.
        hybrid: Explicit hybrid choice, or ``None``.
        similarity_threshold: Explicit threshold, or ``None``.

    Returns:
        The effective levers.
    """
    retrieval = settings.retrieval
    return SearchLevers(
        top_k=retrieval.top_k if top_k is None else top_k,
        hybrid=retrieval.hybrid_enabled if hybrid is None else hybrid,
        similarity_threshold=(
            retrieval.similarity_threshold if similarity_threshold is None else similarity_threshold
        ),
    )


def resolve_rerank_decision(
    rerank: bool | None,
    query: str,
    settings: EffectiveSettings,
    *,
    caller_settings: EffectiveSettings | None = None,
    technical_fraction: float | None = None,
) -> tuple[bool, str]:
    """Resolve whether to rerank and why.

    A caller-supplied settings instance carries a profile's reranker
    decision, which wins over the semantic policy. Without one, the
    server default expresses no profile opinion and the policy resolver
    applies. An explicit ``rerank`` flag always wins.

    Args:
        rerank: Explicit tri-state rerank flag.
        query: Query text, used by the technical classifier.
        settings: Resolved settings for this operation.
        caller_settings: The settings instance the caller passed, or
            ``None`` when the operation uses the composition default.
        technical_fraction: Optional precomputed technical fraction.

    Returns:
        ``(effective_rerank, reason)``.
    """
    profile_reranker = caller_settings.reranker_enabled if caller_settings is not None else None
    return _resolve_rerank_policy(
        rerank,
        query,
        settings,
        technical_fraction=technical_fraction,
        profile_reranker_enabled=profile_reranker,
    )


def size_candidate_pool(
    top_k: int,
    rerank: bool,
    collection_count: int,
    settings: EffectiveSettings,
    *,
    fetch_k_override: int | None = None,
) -> int:
    """Return the first-stage candidate pool size (ADR-016 Decision 2).

    Args:
        top_k: Final result count.
        rerank: Whether reranking is active.
        collection_count: Number of chunks in the collection.
        settings: Resolved settings for this operation.
        fetch_k_override: Experiment override that bypasses the formula.

    Returns:
        The pool size, clamped to the collection and at least one.
    """
    return _resolve_fetch_k(
        top_k, rerank, collection_count, settings, fetch_k_override=fetch_k_override
    )


def first_stage_dense_threshold(similarity_threshold: float, *, rerank: bool) -> float:
    """Return the dense threshold applied before fusion.

    Without reranking, the caller threshold gates dense eligibility
    before RRF. With reranking, the reranker sees the full pool and the
    threshold applies to its scores afterwards.

    Args:
        similarity_threshold: Caller threshold on the dense scale.
        rerank: Whether reranking is active.

    Returns:
        The pre-fusion dense threshold.
    """
    return similarity_threshold if not rerank else 0.0


def apply_dense_eligibility(
    dense_rows: list[dict],
    sparse_rows: list[dict],
    dense_threshold: float,
) -> tuple[list[dict], list[dict]]:
    """Keep only rows with qualifying canonical dense evidence.

    The threshold applies to dense similarity, never to RRF utility.
    Sparse rows without a qualifying dense row are ineligible.

    Args:
        dense_rows: Dense rows in rank order.
        sparse_rows: Sparse rows in rank order.
        dense_threshold: Minimum dense score; ``0.0`` or less is a no-op.

    Returns:
        ``(dense_rows, sparse_rows)`` after the eligibility rule.
    """
    if dense_threshold <= 0.0:
        return dense_rows, sparse_rows
    kept_dense = [row for row in dense_rows if row["score"] >= dense_threshold]
    eligible_ids = {str(row["id"]) for row in kept_dense}
    kept_sparse = [row for row in sparse_rows if str(row["id"]) in eligible_ids]
    return kept_dense, kept_sparse


def run_reranker(
    query: str,
    rows: list[dict],
    *,
    top_k: int,
    settings: EffectiveSettings,
    reranker: Any = None,
    timing_report: dict | None = None,
) -> RerankOutcome:
    """Re-score rows with a reranker and normalise its flags.

    When no reranker is injected, one is built from ``settings`` through
    the backend registry. Rows the reranker marks get the public
    ``reranked`` flag and the reranker score kind; a failed reranker
    leaves the incoming score kind in place.

    Args:
        query: Raw query text.
        rows: Candidate rows (non-empty).
        top_k: Result count passed to the reranker.
        settings: Resolved settings for this operation.
        reranker: Optional injected reranker.
        timing_report: Optional dict that accumulates ``rerank_seconds``.

    Returns:
        The reranked rows, the active backend and any failure reason.
    """
    if reranker is None:
        from . import backend

        reranker = backend.build_reranker_from_settings(settings)
    t0 = time.perf_counter()
    with _rerank_lock(reranker):
        result = reranker.rerank(query, rows, top_k=top_k)
        failure_reason = getattr(reranker, "last_failure_reason", None) or None
    t1 = time.perf_counter()
    if timing_report is not None:
        timing_report["rerank_seconds"] = timing_report.get("rerank_seconds", 0.0) + (t1 - t0)
    for row in result:
        row["reranked"] = row.pop("_reranked", False)
        if row["reranked"]:
            row["score_kind"] = RERANK_SCORE_KIND
    return RerankOutcome(
        rows=result,
        backend=getattr(reranker, "backend_name", None),
        failure_reason=failure_reason,
    )


def rerank_succeeded(rerank: bool, rows: list[dict]) -> bool:
    """Return whether reranking ran and re-scored every row.

    A failed reranker leaves dense or RRF scores in place, which the
    ÷30-scaled threshold would over-admit, so success needs every row.

    Args:
        rerank: Whether reranking was requested.
        rows: Rows after the reranker stage.

    Returns:
        ``True`` only when every row carries ``reranked=True``.
    """
    return rerank and bool(rows) and all(row.get("reranked", False) for row in rows)


def needs_dense_fallback(
    *,
    rerank: bool,
    hybrid: bool,
    succeeded: bool,
    similarity_threshold: float,
) -> bool:
    """Return whether a failed hybrid rerank must re-run the first stage.

    The re-run applies the dense threshold before fusion, restoring the
    non-reranked hybrid rule instead of keeping full-pool RRF ranks.

    Args:
        rerank: Whether reranking was requested.
        hybrid: Whether hybrid retrieval ran.
        succeeded: Result of :func:`rerank_succeeded`.
        similarity_threshold: Caller threshold on the dense scale.

    Returns:
        ``True`` when the first stage must re-run with the dense threshold.
    """
    return rerank and hybrid and not succeeded and similarity_threshold > 0.0


def apply_score_threshold(
    rows: list[dict],
    similarity_threshold: float,
    *,
    succeeded: bool,
    hybrid: bool,
) -> tuple[list[dict], str]:
    """Filter rows by the threshold on the scale their scores use.

    Successfully reranked rows use the calibrated ÷30 transform on
    reranker scores. Non-reranked dense rows use the threshold as given.
    Non-reranked hybrid rows were gated before fusion, so RRF utility is
    never thresholded.

    Args:
        rows: Rows after reranking (or after the fallback re-run).
        similarity_threshold: Caller threshold on the dense scale.
        succeeded: Result of :func:`rerank_succeeded`.
        hybrid: Whether hybrid retrieval ran.

    Returns:
        ``(rows, threshold_score_kind)``.
    """
    threshold_score_kind = RERANK_SCORE_KIND if succeeded else DENSE_SCORE_KIND
    effective_threshold = _effective_threshold(similarity_threshold, succeeded)
    if effective_threshold > 0.0 and (succeeded or not hybrid):
        rows = [row for row in rows if row["score"] >= effective_threshold]
    return rows, threshold_score_kind


def rank_and_truncate(rows: list[dict], top_k: int) -> list[dict]:
    """Order rows by descending score (stable on ties) and keep ``top_k``.

    Args:
        rows: Rows to order.
        top_k: Number of rows to keep.

    Returns:
        A new list of at most ``top_k`` rows.
    """
    return sorted(rows, key=lambda row: row["score"], reverse=True)[:top_k]
