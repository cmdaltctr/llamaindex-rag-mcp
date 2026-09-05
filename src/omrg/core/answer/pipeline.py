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
from .citations import build_citations, parse_citation_ordinals
from .evidence import _evidence_rows, _labelled_nodes  # noqa: F401 (re-exported below)
from .retriever import SearchRetriever
from .settings import AnswerSettings
from .synthesis import CompletionSeam, run_synthesis
from .verify import VerificationFields, run_verification_stage

#: Shared no-op outcome for the disabled verification path.
_NO_VERIFICATION = VerificationFields()

#: Actionable message for the no-provider case (spec scenario).  Names
#: the settings AND the MCP-client alternative so both options surface.
_NO_PROVIDER_MESSAGE = (
    "No answer model is configured for grounded answering. Set "
    "ANSWER__PROVIDER (and ANSWER__MODEL) to configure a server-side "
    "model, or use an MCP client that supports sampling so the client's "
    "model can complete the answer."
)

#: Actionable message when the master switch is off.  Every transport
#: (MCP, CLI, HTTP) inherits this through ``answer()``; the MCP
#: transport also returns it before issuing any client sample.
_DISABLED_MESSAGE = (
    "Grounded answering is disabled. Set ANSWER__ENABLED=true to enable "
    "it, or use search_documents for ranked chunks without a "
    "language-model call."
)

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


# Lineage fields and the evidence/node assembly helpers live in
# ``evidence.py`` (the ADR-059 head-room split); imported above.


def _safe_error_detail(exc: BaseException, settings: Any) -> str:
    """Format an exception for the result without leaking credentials.

    Provider and connection errors can echo key material (an OpenRouter
    key inside a URL, Chroma Cloud connection values); the same redaction
    helpers the MCP transport applies to tool errors are applied here so
    the error strings embedded in core results cannot bypass them.
    """
    from ..vectordb.identity import redact_cloud_secrets, redact_secret

    detail = str(exc)
    detail = redact_cloud_secrets(
        detail,
        getattr(settings, "chroma_cloud_api_key", ""),
        getattr(settings, "chroma_cloud_tenant", ""),
        getattr(settings, "chroma_cloud_database", ""),
    )
    return redact_secret(detail, getattr(settings, "openrouter_api_key", ""))


def _base_result(
    query: str,
    completion_source: str,
    status: str = "error",
    answer: str | None = None,
    failure_stage: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the result skeleton shared by every status."""
    return {
        "status": status,
        "query": query,
        "answer": answer,
        "citations": [],
        "evidence": [],
        "failure_stage": failure_stage,
        "error": error,
        "completion_source": completion_source,
    }


def disabled_result(query: str, completion_source: str) -> dict[str, Any]:
    """Build the actionable master-switch-off response (review F4).

    Shared by every transport so the disabled shape is identical
    whether it is produced here or by the MCP transport's early gate.

    Args:
        query: The question that was asked.
        completion_source: Label for the result (``"none"`` when the
            transport gates before selecting a source).

    Returns:
        The standard error result naming ``ANSWER__ENABLED``.
    """
    return _base_result(
        query,
        completion_source,
        status="error",
        failure_stage=None,
        error=_DISABLED_MESSAGE,
    )


def _zero_generation_diagnostics(retrieval_ms: float) -> dict[str, Any]:
    """Diagnostics for paths where no generation round ran."""
    return {
        "retrieval_ms": retrieval_ms,
        "generation_ms": 0.0,
        "completion_calls": 0,
    }


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

    Returns:
        The answer result dict; see the capability spec for the shape.
    """
    try:
        _validate_request(query, top_k, expand_window, similarity_threshold)
    except _RequestLimitError as exc:
        return _base_result(
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
        )
        try:
            # search() is synchronous; off the event loop (review F10)
            # so concurrent answers are not serialised by retrieval.
            await asyncio.to_thread(retriever.retrieve, query)
        except Exception as exc:  # Retrieval failed before generation.
            result_dict = _base_result(
                query,
                completion_source,
                status="error",
                failure_stage="retrieval",
                error=(
                    f"Retrieval failed: {type(exc).__name__}: {_safe_error_detail(exc, settings)}"
                ),
            )
            if include_diagnostics:
                result_dict["diagnostics"] = _zero_generation_diagnostics(
                    (time.perf_counter() - retrieval_start) * 1000.0
                )
            return result_dict
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0
        result_rows = retriever.rows

    # ── No-evidence short-circuit: never call the model on an empty
    # context (design D7) — and never error on the missing provider.
    if not result_rows:
        result = _base_result(query, completion_source, status="no_evidence")
        if include_diagnostics:
            result["diagnostics"] = _zero_generation_diagnostics(retrieval_ms)
        return result

    evidence = _evidence_rows(result_rows)

    # ── Provider-absent: keep the evidence, name the configuration.
    if complete is None:
        result = _base_result(
            query,
            completion_source,
            status="error",
            failure_stage=None,
            error=_NO_PROVIDER_MESSAGE,
        )
        result["evidence"] = evidence
        if include_diagnostics:
            result["diagnostics"] = _zero_generation_diagnostics(retrieval_ms)
        return result

    # ── Generation through the injected seam.  The wrapper counts every
    # seam invocation so a failure can report the attempts made before
    # it (review F11) — the counting survives exceptions run_synthesis
    # raises, unlike the adapter's internal counter.
    nodes = _labelled_nodes(evidence)
    attempts = 0

    async def _counting_complete(prompt: str) -> str:
        nonlocal attempts
        attempts += 1
        return await complete(prompt)

    def _real_completion_calls(count: int) -> int:
        """Client rounds are the real calls on the MRTR path (F11)."""
        if preflight is not None and preflight.sampling_calls > 0:
            return preflight.sampling_calls
        return count

    generation_start = time.perf_counter()
    try:
        text, completion_calls = await run_synthesis(
            query,
            nodes,
            seam=_counting_complete,
            context_window=answer_block.context_window,
            max_output_tokens=answer_block.max_output_tokens,
            max_rounds=answer_block.max_rounds,
        )
    except Exception as exc:  # Generation failed after successful retrieval.
        # ``except Exception`` also catches asyncio ``ExceptionGroup``
        # wrapping (a plain-``Exception`` subgroup), so a client seam
        # that dies mid-flight still maps to a generation failure.
        sampling_ms = preflight.sampling_ms if preflight else 0.0
        result = _base_result(
            query,
            completion_source,
            status="error",
            failure_stage="generation",
            error=f"Generation failed: {type(exc).__name__}: {_safe_error_detail(exc, settings)}",
        )
        result["evidence"] = evidence
        if include_diagnostics:
            result["diagnostics"] = {
                "retrieval_ms": retrieval_ms,
                "generation_ms": (time.perf_counter() - generation_start) * 1000.0 + sampling_ms,
                "completion_calls": _real_completion_calls(attempts),
            }
        return result
    generation_ms = (time.perf_counter() - generation_start) * 1000.0 + (
        preflight.sampling_ms if preflight else 0.0
    )
    completion_calls = _real_completion_calls(completion_calls)

    # ── Deterministic citations from the supplied evidence.  Validation
    # stays inside the guarded generation stage (review F12): an absurd
    # model output — e.g. a 5,000-digit ordinal tripping CPython's
    # integer-conversion limit inside ``parse_citation_ordinals`` — is a
    # generation failure with evidence retained, never an exception
    # escaping the operation.
    try:
        ordinals = parse_citation_ordinals(text, len(evidence))
        citations = build_citations(evidence, ordinals)
    except Exception as exc:
        result = _base_result(
            query,
            completion_source,
            status="error",
            failure_stage="generation",
            error=(
                "Generation failed: citation assembly rejected the model "
                f"output: {type(exc).__name__}: {_safe_error_detail(exc, settings)}"
            ),
        )
        result["evidence"] = evidence
        if include_diagnostics:
            result["diagnostics"] = {
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "completion_calls": completion_calls,
            }
        return result
    grounded = bool(text.strip()) and bool(citations)

    # ── Claim verification (ADR-059): after citation assembly, before
    # the final status decision.  Opt-in; the stage never raises — a
    # non-grounded answer (no citations) skips the judge entirely.
    verification = _NO_VERIFICATION
    if grounded and getattr(answer_block, "verify_claims", False):
        verification = await run_verification_stage(
            text,
            evidence,
            verify_complete=verify_complete,
            unavailable_reason=verify_unavailable_reason,
            error_detail=lambda exc: _safe_error_detail(exc, settings),
        )

    status = (
        "unverified_claims"
        if verification.failing
        else ("ok" if grounded else "generation_unverified")
    )

    result = _base_result(query, completion_source, status=status, answer=text)
    result["citations"] = citations
    result["evidence"] = evidence
    if verification.verified:
        result["verified"] = True
    if verification.skipped_reason is not None:
        result["verification_skipped"] = verification.skipped_reason
    if verification.failing:
        result["unverified_claims"] = list(verification.failing)
    if include_diagnostics:
        result["diagnostics"] = {
            "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms,
            "completion_calls": completion_calls,
        }
        if verification.ran:
            # The judge's cost is reported separately from retrieval and
            # generation (spec: cost disclosure) — only when it ran.
            result["diagnostics"]["verification_ms"] = verification.ms
            result["diagnostics"]["verification_calls"] = verification.calls
    return result


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
