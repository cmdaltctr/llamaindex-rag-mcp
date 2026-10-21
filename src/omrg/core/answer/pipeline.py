"""Grounded answering pipeline — the ``answer()`` entry point.

Retrieves through the existing ``search()`` path (via
:class:`~omrg.core.answer.retriever.SearchRetriever`), synthesises a
grounded answer through an injected async completion seam, and returns
the answer together with the exact chunks supplied as context and
deterministic citations built from chunk lineage.

Contract (spec: grounded-answer-synthesis):

* Empty retrieval short-circuits to a no-evidence result BEFORE any
  model call (design D7).
* Failure attribution separates ``retrieval`` from ``generation``;
  retrieved evidence is always retained on a generation failure.
* A missing completion seam with evidence present is an actionable
  error naming the configuration, never a silent chunks-as-answer.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any

from ..settings import resolve_effective_settings
from .evidence import _evidence_rows, _labelled_nodes
from .progress import AnswerStage, report_stage
from .results import (
    answered_result,
    base_result,
    disabled_result,
    generation_diagnostics,
    no_evidence_result,
    no_provider_result,
    stage_failure_result,
    zero_generation_diagnostics,
)
from .retriever import SearchRetriever
from .settings import AnswerSettings
from .stages import (
    FAILURE_STAGE_RETRIEVAL,
    error_detail_for,
    prepare_evidence,
    resolve_citations,
    safe_error_detail,
    synthesise_answer,
    verify_answer,
)
from .synthesis import CompletionSeam, run_synthesis

# ``disabled_result`` is re-exported for the MCP transport's early gate.
__all__ = ["ResolvedRetrieval", "answer", "disabled_result", "evidence_rows", "labelled_nodes"]

#: Hard input limits enforced at the core entry so every transport
#: (MCP, CLI, HTTP) inherits them (review F7).  Frozen for the OpenAPI
#: mirror: query <= 4096 characters, top_k in 1..100, expand_window in
#: 0..10.
_QUERY_MAX_CHARS = 4096
_TOP_K_MAX = 100
_EXPAND_WINDOW_MAX = 10


class _RequestLimitError(ValueError):
    """An out-of-bounds request value, converted to a structured error."""


@dataclass(frozen=True)
class ResolvedRetrieval:
    """Pre-retrieved rows plus the honest preflight statistics.

    The MCP transport's MRTR resolvers run retrieval and client
    sampling before the tool body; this dataclass threads what they
    actually did into ``answer()`` so diagnostics stay honest (review
    F11).  Plain ``rows`` lists remain accepted for CLI/direct callers.

    Attributes:
        rows: The ``search()`` rows the resolver obtained.
        retrieval_ms: Wall-time the resolver's retrieval took.
        sampling_ms: Wall-time the client spent answering sampling
            rounds before the body ran.
        sampling_calls: Successful client completion rounds served.
    """

    rows: list[dict]
    retrieval_ms: float = 0.0
    sampling_ms: float = 0.0
    sampling_calls: int = 0


def _validate_request(
    query: str,
    top_k: int | None,
    expand_window: int,
    similarity_threshold: float | None,
) -> None:
    """Reject out-of-bounds request values (review F7, security F2).

    Bounds: ``query`` length, ``top_k`` 1..100, ``expand_window``
    0..10, and a finite ``similarity_threshold`` within 0.0..1.0
    (``None`` disables score filtering).

    Raises:
        _RequestLimitError: Naming the violated limit and the value.
    """
    if len(query) > _QUERY_MAX_CHARS:
        raise _RequestLimitError(
            f"query exceeds the {_QUERY_MAX_CHARS}-character limit (got {len(query)} characters)"
        )
    if top_k is not None and not 1 <= top_k <= _TOP_K_MAX:
        raise _RequestLimitError(f"top_k must be between 1 and {_TOP_K_MAX} (got {top_k})")
    if not 0 <= expand_window <= _EXPAND_WINDOW_MAX:
        raise _RequestLimitError(
            f"expand_window must be between 0 and {_EXPAND_WINDOW_MAX} (got {expand_window})"
        )
    if similarity_threshold is not None:
        ok_threshold = (
            isinstance(similarity_threshold, (int, float))
            and math.isfinite(similarity_threshold)
            and 0.0 <= similarity_threshold <= 1.0
        )
        if not ok_threshold:
            raise _RequestLimitError(
                "similarity_threshold must be a finite number between 0.0 "
                f"and 1.0 (got {similarity_threshold!r})"
            )


# Evidence assembly lives in ``evidence.py``; the stage seams live in
# ``stages.py`` and the result shapes in ``results.py`` (task 3.6), so
# graph adapters reuse the exact steps this operation runs.


async def answer(
    query: str,
    *,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    expand_window: int = 0,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
    include_diagnostics: bool = False,
    complete: CompletionSeam | None = None,
    verify_complete: CompletionSeam | None = None,
    verify_unavailable_reason: str | None = None,
    completion_source: str = "server",
    rows: list[dict] | ResolvedRetrieval | None = None,
    reranker: Any = None,
    store: Any = None,
    effective_settings: Any = None,
    embed_model: Any = None,
    query_cache: Any = None,
    embedding_identity: Any = None,
) -> dict[str, Any]:
    """Answer a query from retrieved evidence with verifiable citations.

    Args:
        query: Free-text question to answer (at most 4,096 characters).
        top_k: Maximum chunks to use as evidence (profile default when
            None; at most 100 when explicit).
        similarity_threshold: Minimum score for evidence rows.
        rerank: Tri-state rerank control for the retrieval stage.
        hybrid: Tri-state hybrid fusion control for the retrieval stage.
        expand_window: Neighbours merged into each chunk by context
            assembly (at most 10).
        collection_name: Collection to retrieve from.
        metadata_filter: Optional store ``where`` clause.
        include_diagnostics: Include per-stage timings and the
            completion-call count in the result.
        complete: Injected async completion seam (``prompt -> reply``).
            ``None`` means no model is available; with evidence present
            the operation returns an actionable error.
        verify_complete: Injected async judge seam for the optional
            claim-verification stage (ADR-059).  ``None`` with
            ``verify_claims`` enabled reports ``verification_skipped``.
        verify_unavailable_reason: Why no judge seam could be built
            (transport-resolved provider errors); reported verbatim in
            ``verification_skipped``.
        completion_source: Label echoed in the result (``"server"``,
            ``"client_mrtr"``, ``"client_legacy"``).
        rows: Pre-retrieved ``search()`` rows — a plain list, or a
            :class:`ResolvedRetrieval` carrying the resolver's honest
            preflight timings (review F11).  ``None`` retrieves through
            the normal path.  Rows always originate from ``search()`` —
            this is a cache hook, not a second retrieval strategy.
        reranker: Optional pre-constructed reranker.
        store: Optional injected vector store.
        effective_settings: Optional resolved profile settings.
        embed_model: Optional injected embedding model (the engine's
            embedder); ``None`` selects the legacy global path so
            ``engine.search()`` and ``engine.answer()`` share one model.
        query_cache: Optional engine-owned query embedding cache.
        embedding_identity: Provider and model that embed the query
            (ADR-081). Passed to retrieval only when set.

    Returns:
        The answer result dict; see the capability spec for the shape.
    """
    try:
        _validate_request(query, top_k, expand_window, similarity_threshold)
    except _RequestLimitError as exc:
        return base_result(
            query, completion_source, status="error", failure_stage=None, error=str(exc)
        )

    settings = resolve_effective_settings(effective_settings)
    # EffectiveSettings always carries the block after this change; the
    # fallback keeps hand-built instances (older tests, pickles) working.
    answer_block = getattr(settings, "answer", None) or AnswerSettings()

    # ── Master switch (review F4): actionable error before any
    # retrieval or model work, inherited by every transport.
    if not answer_block.enabled:
        return disabled_result(query, completion_source)

    report_stage(AnswerStage.SEARCHING)
    retrieval_start = time.perf_counter()
    preflight: ResolvedRetrieval | None = None
    if rows is not None:
        # Transport resolvers already retrieved this query; skip the
        # retrieval stage (the rows are authoritative search() output).
        if isinstance(rows, ResolvedRetrieval):
            preflight = rows
            result_rows = list(rows.rows)
            retrieval_ms = rows.retrieval_ms
        else:
            result_rows = list(rows)
            retrieval_ms = 0.0
    else:
        retriever = SearchRetriever(
            collection_name=collection_name,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            expand_window=expand_window,
            metadata_filter=metadata_filter,
            reranker=reranker,
            store=store,
            effective_settings=settings,
            embed_model=embed_model,
            query_cache=query_cache,
            embedding_identity=embedding_identity,
        )
        try:
            # search() is synchronous; off the event loop (review F10)
            # so concurrent answers are not serialised by retrieval.
            await asyncio.to_thread(retriever.retrieve, query)
        except Exception as exc:  # Retrieval failed before generation.
            return stage_failure_result(
                query,
                completion_source,
                failure_stage=FAILURE_STAGE_RETRIEVAL,
                error=f"Retrieval failed: {type(exc).__name__}: {safe_error_detail(exc, settings)}",
                diagnostics=(
                    zero_generation_diagnostics((time.perf_counter() - retrieval_start) * 1000.0)
                    if include_diagnostics
                    else None
                ),
            )
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0
        result_rows = retriever.rows

    # ── Evidence preparation.  An empty result set is valid data: never
    # call the model on an empty context (design D7) and never error on
    # the missing provider.
    evidence = prepare_evidence(result_rows)
    no_generation = zero_generation_diagnostics(retrieval_ms) if include_diagnostics else None
    if not evidence:
        return no_evidence_result(query, completion_source, diagnostics=no_generation)

    # ── Provider-absent: keep the evidence, name the configuration.
    if complete is None:
        return no_provider_result(query, completion_source, evidence, diagnostics=no_generation)

    # ── Generation through the injected seam.  ``runner`` is this
    # module's ``run_synthesis`` reference, read at call time, so the
    # existing patch target keeps working.
    detail = error_detail_for(settings)
    synthesis = await synthesise_answer(
        query,
        evidence,
        complete=complete,
        answer_block=answer_block,
        error_detail=detail,
        runner=run_synthesis,
    )
    # Client rounds are the real calls on the MRTR path (review F11).
    completion_calls = synthesis.completion_calls
    if preflight is not None and preflight.sampling_calls > 0:
        completion_calls = preflight.sampling_calls
    generation_ms = synthesis.ms + (preflight.sampling_ms if preflight else 0.0)
    diagnostics = (
        generation_diagnostics(retrieval_ms, generation_ms, completion_calls)
        if include_diagnostics
        else None
    )

    if synthesis.text is None:
        return stage_failure_result(
            query,
            completion_source,
            failure_stage=synthesis.failure_stage,
            error=synthesis.error or "Generation failed: no answer text",
            evidence=evidence,
            diagnostics=diagnostics,
        )

    # ── Deterministic citations from the supplied evidence.  Citation
    # assembly failure stays a generation failure (review F12).
    citations = resolve_citations(synthesis.text, evidence, error_detail=detail)
    if citations.error is not None:
        return stage_failure_result(
            query,
            completion_source,
            failure_stage=citations.failure_stage,
            error=citations.error,
            evidence=evidence,
            diagnostics=diagnostics,
        )

    # ── Claim verification (ADR-059): opt-in, never raises; a
    # non-grounded answer skips the judge entirely.
    verification = await verify_answer(
        synthesis.text,
        evidence,
        grounded=citations.grounded,
        answer_block=answer_block,
        verify_complete=verify_complete,
        unavailable_reason=verify_unavailable_reason,
        error_detail=detail,
    )
    return answered_result(
        query,
        completion_source,
        text=synthesis.text,
        citations=citations.citations,
        grounded=citations.grounded,
        evidence=evidence,
        verification=verification,
        diagnostics=diagnostics,
    )


# ── Transport-planning helpers ────────────────────────────────────────────
# The MCP transport's MRTR resolvers must predict the exact prompt each
# completion round will use (design D6: core owns prompt construction).
# They share these pure helpers with the pipeline so both paths agree by
# construction rather than by duplication.  The implementations live in
# ``evidence.py`` (the ADR-059 head-room split); re-exported here for the
# existing import surface.

#: Public aliases for transport resolvers (see ``evidence.py``).
evidence_rows = _evidence_rows
labelled_nodes = _labelled_nodes
