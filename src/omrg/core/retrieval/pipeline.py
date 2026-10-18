"""Retrieval pipeline orchestrator.

The main ``search()`` entry point that ties together dense vector search,
sparse BM25/native retrieval, Reciprocal Rank Fusion, and cross-encoder
reranking.  Also hosts ``list_collections()`` and the hybrid query
machinery.  Extracted from the original ``retrieval.py`` monolith as
part of Phase 1; rewired through the vector store ABC in Phase 3.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..settings import resolve_effective_settings
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from ..vectordb.identity import EmbeddingIdentity
from . import operations as ops
from .assembly import ASSEMBLY_INTERNAL_FIELDS, assemble, promote_assembly_diagnostics
from .operations import RERANK_SCORE_KIND  # noqa: F401 (re-exported for callers/tests)
from .registry import get as _retrieval_get
from .sparse_dispatch import (  # noqa: F401  (re-exported for callers/tests)
    _native_sparse_query,
    _sparse_bm25_query,
    _warned_collections,
    _warned_native_fallback_collections,
    sparse_policy_runner,
)

logger = logging.getLogger(__name__)


def _resolve_store(store: VectorStore | None) -> VectorStore:
    """Return the given store or the process-wide default."""
    return store if store is not None else get_default_store()


def _selected_sparse_backend(settings: Any) -> str:
    """Return the sparse backend from the injected settings.

    The ``auto`` capability probe runs once in the composition root, which
    bakes the concrete backend into ``EffectiveSettings`` — so this is a
    plain read, not a probe.
    """
    return settings.retrieval.hybrid_sparse_backend


def _hybrid_query_rows(
    store: VectorStore,
    collection_name: str,
    query: str,
    fetch_k: int,
    rrf_k: int,
    settings: Any,
    metadata_filter: dict | None = None,
    dense_threshold: float = 0.0,
    include_norm_diagnostic: bool = False,
    sparse_report: dict | None = None,
    *,
    timing_report: dict | None = None,
    embed_model: Any = None,
    cache: Any = None,
    embedding_identity: EmbeddingIdentity | None = None,
) -> list[dict]:
    backend = _selected_sparse_backend(settings)
    identity_kwargs = {"embedding_identity": embedding_identity} if embedding_identity else {}
    _dense_query_rows = _retrieval_get("dense")
    # Registry-routed sparse dispatch (task 3.3): both runners execute
    # through the sparse-backend registry; only the native policy adds
    # the coverage warning and the BM25 fallback net, inside its runner.
    sparse_runner = sparse_policy_runner(
        backend, native=_native_sparse_query, bm25=_sparse_bm25_query
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(
            _dense_query_rows,
            store,
            collection_name,
            query,
            fetch_k,
            metadata_filter,
            norm_guard_enabled=settings.embedding.norm_guard_enabled,
            norm_tolerance=settings.embedding.norm_tolerance,
            attach_norm_diagnostic=include_norm_diagnostic,
            timing_report=timing_report,
            embed_model=embed_model,
            cache=cache,
            query_instruction=settings.embedding.query_instruction,
            **identity_kwargs,
        )
        sparse_future = executor.submit(
            sparse_runner,
            collection_name,
            store,
            query,
            fetch_k,
            metadata_filter,
            sparse_report,
            timing_report=timing_report,
            **identity_kwargs,
        )
        dense_rows = dense_future.result()
        sparse_rows = sparse_future.result()

    # Dense eligibility (shared seam): the threshold gates canonical dense
    # evidence before fusion, never RRF utility.
    dense_rows, sparse_rows = ops.apply_dense_eligibility(dense_rows, sparse_rows, dense_threshold)

    t0 = time.perf_counter()
    fused = _retrieval_get("fusion")(dense_rows, sparse_rows, k=rrf_k)
    t1 = time.perf_counter()
    if timing_report is not None:
        timing_report["fusion_seconds"] = timing_report.get("fusion_seconds", 0.0) + (t1 - t0)
    return fused[:fetch_k]


def _strip_internal_result_fields(result: dict) -> dict:
    """Remove retrieval diagnostics that are not public API by default."""
    public = dict(result)
    for key in (
        "id",
        "fused_score",
        "dense_score",
        "dense_score_kind",
        "dense_rank",
        "sparse_rank",
        "fused_rank",
        # Assembly-internal markers (task 5.9): merged/expansion state is
        # diagnostics-only, so the public result shape stays stable.
        *ASSEMBLY_INTERNAL_FIELDS,
    ):
        public.pop(key, None)
    return public


def search(
    query: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    expand_window: int = 0,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
    include_diagnostics: bool = False,
    technical_fraction: float | None = None,
    fetch_k: int | None = None,
    reranker: Any = None,
    store: VectorStore | None = None,
    effective_settings: Any = None,
    embed_model: Any = None,
    query_cache: Any | None = None,
    embedding_identity: EmbeddingIdentity | None = None,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return.  When ``None``, the
            resolved default applies: the profile's ``top_k`` when
            ``effective_settings`` is provided, else ``settings.top_k``.
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).  When ``rerank``
            is True the threshold is scaled down by 30x because
            cross-encoder sigmoid scores occupy a lower range than
            cosine similarity.  For example, 0.3 becomes 0.01.
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
            When ``effective_settings`` is provided, the profile's
            ``reranker_enabled`` takes precedence over the global default.
            Explicit ``rerank`` flags always bypass both.
        hybrid: If True, fuse dense vector results with sparse BM25/native
            sparse rankings via Reciprocal Rank Fusion before reranking.
            When ``None``, the profile's ``hybrid_enabled`` applies if
            ``effective_settings`` is provided, else ``settings.hybrid_enabled``.
        expand_window: Neighbours added per side of each retrieved chunk
            during context assembly (default 0 = no expansion).  Expansion
            is opt-in because it adds evidence the ranker did not select;
            expanded neighbours merge into the retrieved chunk under the
            assembly merging rules and never displace retrieved rows.
        collection_name: Name of the collection to search
            (default ``"documents"`` for backward compatibility).
        metadata_filter: Optional store ``where`` clause to filter
            results by metadata fields (e.g. ``{"category": "AI"}``).
            When provided, the filter is applied server-side — only
            matching chunks are returned from the vector store.
        include_diagnostics: If True, preserve hybrid rank diagnostic
            fields (``id``, ``fused_score``, ``dense_rank``, ``sparse_rank``,
            ``fused_rank``) and policy resolution reason for experiments.
            Public MCP/CLI callers leave this False so result shape stays stable.
        technical_fraction: Optional workload-level identifier-heavy fraction
            (0.0-1.0). When provided, it overrides the single-query classifier
            for policy resolution.
        fetch_k: Optional override for the candidate pool size.  When set,
            bypasses the ``max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)``
            formula so experiment runners can test genuinely distinct pool
            sizes.  Production callers leave this as None.  The value is
            still clamped to the collection size.
        reranker: Optional pre-constructed ``CrossEncoderReranker``
            (dependency injection — the composition root builds one via
            ``omrg.compose.build_reranker``).  When ``None``, a fresh
            instance is constructed; the underlying ONNX session is still
            cached process-wide keyed by model ID, so the model is loaded
            at most once per process regardless of how many instances are
            created.
        store: Optional injected :class:`VectorStore` (defaults to the
            process-wide store constructed by ``compose``).
        embedding_identity: Provider and model that embed this query
            (ADR-081). The stores check it against the collection stamp.
            ``None`` keeps the composed store identity.
        effective_settings: Optional :class:`EffectiveSettings` resolved
            by :class:`ProfileResolver` for this collection (Phase 4).
            When provided, its Tier 2 levers (``top_k``, ``reranker_enabled``,
            ``hybrid_enabled``) supply the defaults for omitted parameters,
            taking precedence over the global ``settings`` singleton.

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      - float interpreted according to ``score_kind``
            score_kind - dense similarity, RRF utility, or reranker score
            source     - source file path
            page_label - page number (or None)
            text       - the chunk text
            reranked   - bool (True if cross-encoder re-scored the result)

        When ``include_diagnostics=True``, each result also includes:
            rerank_reason       - string explaining the policy decision
            threshold_score_kind - semantics used for threshold evaluation

    Raises:
        ValueError: If ``metadata_filter`` is rejected by the store
            (unsupported operator, type mismatch, etc.).  Other
            store-side failures propagate as their original exception
            types so the MCP layer can classify them.
    """
    # Resolve the settings ONCE at the entry-point boundary. An explicitly
    # passed instance always wins; otherwise the composition root's default
    # is used. Nothing below this line consults any other source.
    resolved_settings = resolve_effective_settings(effective_settings)

    # Sizing, policy, filtering and fallback rules live in the shared
    # ``operations`` seams (task 3.1) so graph adapters reuse them.
    # Phase 4: profile-resolved levers take precedence over global defaults.
    levers = ops.resolve_search_levers(
        resolved_settings,
        top_k=top_k,
        hybrid=hybrid,
        similarity_threshold=similarity_threshold,
    )
    top_k = levers.top_k
    hybrid = levers.hybrid
    similarity_threshold = levers.similarity_threshold

    # A caller-passed instance carries the profile's reranker decision;
    # the server default does not express a profile opinion.
    effective_rerank, rerank_reason = ops.resolve_rerank_decision(
        rerank,
        query,
        resolved_settings,
        caller_settings=effective_settings,
        technical_fraction=technical_fraction,
    )

    resolved_store = _resolve_store(store)

    chunk_count = resolved_store.count(collection_name)
    if chunk_count == 0:
        return []

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.  See ADR-016 Decision 2.
    # When fetch_k is explicitly provided (experiment runners), it
    # bypasses the formula to allow genuinely distinct pool sizes.
    resolved_fetch_k = ops.size_candidate_pool(
        top_k,
        effective_rerank,
        chunk_count,
        resolved_settings,
        fetch_k_override=fetch_k,
    )

    # Per-stage timing dict (complete-observable-surface Thread B).
    # Created unconditionally so the measured path is the same path
    # production runs; only attached to result rows when diagnostics
    # are enabled (design: measurement-only, report under the flag).
    # Durations accumulate per stage across every execution (design D5),
    # so the failed-rerank re-query path sums both hybrid executions.
    timing_report: dict = {}

    _dense_query_rows = _retrieval_get("dense")
    identity_kwargs = {"embedding_identity": embedding_identity} if embedding_identity else {}
    sparse_report: dict = {}
    if hybrid:
        dense_threshold = ops.first_stage_dense_threshold(
            similarity_threshold, rerank=effective_rerank
        )
        results = _hybrid_query_rows(
            resolved_store,
            collection_name,
            query,
            resolved_fetch_k,
            resolved_settings.retrieval.hybrid_rrf_k,
            resolved_settings,
            metadata_filter,
            dense_threshold,
            include_norm_diagnostic=include_diagnostics,
            sparse_report=sparse_report,
            timing_report=timing_report,
            embed_model=embed_model,
            cache=query_cache,
            **identity_kwargs,
        )
    else:
        results = _dense_query_rows(
            resolved_store,
            collection_name,
            query,
            resolved_fetch_k,
            metadata_filter,
            norm_guard_enabled=resolved_settings.embedding.norm_guard_enabled,
            norm_tolerance=resolved_settings.embedding.norm_tolerance,
            attach_norm_diagnostic=include_diagnostics,
            timing_report=timing_report,
            embed_model=embed_model,
            cache=query_cache,
            query_instruction=resolved_settings.embedding.query_instruction,
            **identity_kwargs,
        )

    # Optional: re-score with cross-encoder reranker.
    active_backend: str | None = None
    if effective_rerank and results:
        outcome = ops.run_reranker(
            query,
            results,
            top_k=top_k,
            settings=resolved_settings,
            reranker=reranker,
            timing_report=timing_report,
        )
        results = outcome.rows
        # Record which backend actually ran (may differ from the settings
        # value when the torch extra is missing and the helper fell back
        # to ONNX).
        active_backend = outcome.backend
        # The reranker's own failure reason (if any) is more specific than
        # the policy string computed before reranking ran, so surface it.
        if outcome.failure_reason:
            rerank_reason = outcome.failure_reason

    # Filter by similarity threshold (applies after reranking).
    #
    # Reranker scores are sigmoid-normalised and occupy a different range
    # than canonical dense similarity.  A dense threshold of 0.3 is a weak match,
    # but the reranker may assign a valid result only 0.015 (sigmoid).
    # Scale the threshold down by 30x when reranking to avoid over-filtering.
    # Uses whether reranking actually succeeded (the "reranked" flag), not
    # merely whether it was requested — a failed reranker leaves dense
    # scores in place, which the ÷30-scaled threshold would over-admit.
    rerank_succeeded = ops.rerank_succeeded(effective_rerank, results)
    # A failed hybrid reranker must return to the pre-rerank dense-threshold
    # rule. Re-run the cheap first-stage query with the threshold applied
    # before fusion; reranker failure is rare, and correctness is preferable
    # to retaining full-pool RRF ranks with incompatible semantics.
    if ops.needs_dense_fallback(
        rerank=effective_rerank,
        hybrid=hybrid,
        succeeded=rerank_succeeded,
        similarity_threshold=similarity_threshold,
    ):
        results = _hybrid_query_rows(
            resolved_store,
            collection_name,
            query,
            resolved_fetch_k,
            resolved_settings.retrieval.hybrid_rrf_k,
            resolved_settings,
            metadata_filter,
            similarity_threshold,
            sparse_report=sparse_report,
            timing_report=timing_report,
            embed_model=embed_model,
            cache=query_cache,
            **identity_kwargs,
        )

    results, threshold_score_kind = ops.apply_score_threshold(
        results,
        similarity_threshold,
        succeeded=rerank_succeeded,
        hybrid=hybrid,
    )
    results = ops.rank_and_truncate(results, top_k)

    # Context assembly (task 5.6): the single stage that reshapes returned
    # evidence — overlap merging plus opt-in neighbour expansion — runs
    # exactly once, after truncation so retrieved rows are never dropped to
    # honour ``top_k``, and before diagnostics attachment. It never
    # re-ranks or re-scores.
    t0 = time.perf_counter()
    results = assemble(
        results,
        chunk_overlap=resolved_settings.chunking.chunk_overlap,
        expand_window=expand_window,
        store=resolved_store,
        collection=collection_name,
    )
    t1 = time.perf_counter()
    timing_report["assembly_seconds"] = timing_report.get("assembly_seconds", 0.0) + (t1 - t0)

    # Attach policy diagnostics when requested.
    if include_diagnostics:
        # Assembly markers (task 5.8): report what the assembly stage did —
        # merges, constituent counts and expansion — under the flag only.
        promote_assembly_diagnostics(results)
        for r in results:
            r["rerank_reason"] = rerank_reason
            r["threshold_score_kind"] = threshold_score_kind
            # Attach the active backend name alongside the failure reason
            # so a torch-fallback or a failed backend is distinguishable
            # from reranking being switched off (ADR-029 §3 deferred
            # item 2, now landed).
            if active_backend is not None:
                r["rerank_backend"] = active_backend
            # Per-stage timing (complete-observable-surface Thread B).
            # A copy is attached to each row so callers cannot mutate the
            # shared report. Stages that did not run are absent from the
            # dict (design D3); no total is emitted (design D2).
            r["timings"] = dict(timing_report)
        # Report the sparse backend that actually ran for hybrid queries
        # (task 3.4): a native request that fell back reports ``bm25``,
        # never native (spec: "SHALL NOT label the resulting sparse
        # ranking as native").
        if hybrid and sparse_report:
            backend_ran = sparse_report.get("sparse_backend")
            if backend_ran is not None:
                for r in results:
                    r["sparse_backend"] = backend_ran

    if not include_diagnostics:
        results = [_strip_internal_result_fields(r) for r in results]
    return results


def list_collections(
    store: VectorStore | None = None,
) -> list[dict]:
    """List all collections with document and chunk counts.

    Args:
        store: Optional injected :class:`VectorStore`.

    Returns:
        A list of dicts, each with:
        - ``name`` — collection name
        - ``document_count`` — approximate number of unique source files
        - ``chunk_count`` — total number of chunks in the collection
    """
    resolved_store = _resolve_store(store)

    collections: list[dict] = []
    for name in resolved_store.list_collections():
        try:
            chunk_count = resolved_store.count(name)
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in resolved_store.iter_metadatas(name):
                    if meta is None:
                        continue
                    source = meta.get("file_path") or meta.get("file_name") or "unknown"
                    doc_sources.add(source)

            collections.append(
                {
                    "name": name,
                    "document_count": len(doc_sources),
                    "chunk_count": chunk_count,
                }
            )
        except Exception:  # noqa: S112
            # Skip collections that can't be accessed
            continue
    return collections
