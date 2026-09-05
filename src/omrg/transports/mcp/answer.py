"""MCP tool: answer_documents — grounded answering over the indexed store.

The tool performs one or more language-model completion calls (it is the
project's first query-time generation path) and names ``search_documents``
as the cheaper chunk-returning alternative in its description.

Completion source selection (design D6, spec: modern client model
requests use multi-round trips where available):

* Modern session (protocol >= 2026-07-28) with sampling capability and
  ``answer.prefer_client_sampling``: the bounded MRTR resolver chain in
  :mod:`.answer_mrtr` asks the client's model through ``Sample``
  requests; the deprecated ``ctx.session.create_message()`` is NEVER
  called.  ``ANSWER__ENABLED=false`` gates this path before any Sample
  is issued.
* Negotiated legacy session (older protocol) with sampling capability
  and ``answer.allow_legacy_sampling``: the labelled compatibility seam
  ``_legacy_complete`` uses the deprecated back-channel.
* Otherwise: the lazy server-side model from ``compose.build_answer_llm``
  — or, when none is configured, core's actionable error naming both
  options.

The resolver chain re-runs deterministically each MRTR round: core's
``plan_next_prompt`` replay produces exactly the prompt the pipeline
will consume, so the client answers the real question (design D6: core
owns retrieval, evidence numbering and prompt construction).
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, Resolve
from mcp.types import (
    CreateMessageResult,
    SamplingMessage,
    TextContent,
    ToolAnnotations,
)

from ... import compose
from ...core.answer import answer
from ...core.answer.pipeline import disabled_result
from . import (
    _error_message,
    _get_profile_resolver,
    _get_reranker,
    _log_tool_error,
    mcp,
)
from .answer_mrtr import (
    _answer_settings,
    _client_round_cap,
    _client_seam,
    _evict_payload,
    _mrtr_round_1,
    _mrtr_round_2,
    _mrtr_round_3,
    _mrtr_round_4,
    _peek_payload,
    _resolved_replies,
    _result_text,
    _server_seam,
    _session_facts,
    consume_preflight,
)

#: First protocol revision whose ``tools/call`` carries elicitation and
#: sampling inside ``InputRequiredResult`` (MRTR).  Sessions negotiated
#: at or above this version must never touch the deprecated
#: ``create_message`` back-channel.
MODERN_PROTOCOL_VERSION = "2026-07-28"


def select_completion_source(
    *,
    protocol_version: str | None,
    sampling_capability: object | None,
    prefer_client: bool,
    allow_legacy: bool,
) -> str:
    """Decide the completion source from the session's protocol era.

    Args:
        protocol_version: Negotiated protocol version (``None`` for a
            direct call with no session).
        sampling_capability: The client's advertised sampling capability
            (``None`` when absent).
        prefer_client: ``answer.prefer_client_sampling``.
        allow_legacy: ``answer.allow_legacy_sampling``.

    Returns:
        ``"client_mrtr"`` (modern session + capability + preference),
        ``"client_legacy"`` (older session + capability + preference +
        explicit allowance — the labelled compatibility mode, never
        selected merely because MRTR is unavailable), else ``"server"``.
    """
    if sampling_capability is None or not prefer_client:
        return "server"
    if protocol_version is None:
        # No session (direct call): no client path exists.
        return "server"
    if protocol_version >= MODERN_PROTOCOL_VERSION:
        return "client_mrtr"
    if allow_legacy:
        return "client_legacy"
    return "server"


async def _legacy_complete(ctx: Any, prompt: str) -> str:
    """Complete one round through the deprecated sampling back-channel.

    Compatibility path ONLY for a negotiated pre-2026-07-28 session
    (spec scenario: legacy sampling is explicitly negotiated).  The
    transport selection logic guarantees this is never reached on a
    modern session.
    """
    result: CreateMessageResult = await ctx.session.create_message(
        [SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
        max_tokens=_answer_settings().max_output_tokens,
    )
    return _result_text(result)


def _payload_failure_result(query: str, payload: Any) -> dict:
    """Convert a resolver-era failure sentinel into the standard error.

    Resolvers run before the tool body's try block, so their failures
    are recorded as sentinels (review F3); the body converts them here,
    preserving the structured-result contract with the stage the
    resolver attributed (``retrieval`` or ``generation``).
    """
    stage = payload.failure_stage or "generation"
    exc = payload.failure
    verb = "Retrieval failed" if stage == "retrieval" else "Generation failed"
    return {
        "status": "error",
        "query": query,
        "answer": None,
        "citations": [],
        "evidence": (payload.evidence or []) if stage != "retrieval" else [],
        "failure_stage": stage,
        "error": f"{verb}: {type(exc).__name__}: {_error_message(exc)}",
        "completion_source": "none",
    }


@mcp.tool(
    description=(
        "Answer a question from the indexed documents using retrieved "
        "evidence, returning the answer together with deterministic, "
        "verifiable citations (every cited chunk_id re-fetches exactly "
        "one stored chunk). Performs ONE OR MORE language-model "
        "completion calls — use search_documents instead when you only "
        "need ranked chunks without that cost. When ANSWER__VERIFY_CLAIMS "
        "is enabled, each cited claim additionally costs one cloud-judge "
        "call (~3.3 s P95 each, ADR-059)."
    ),
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
)
async def answer_documents(
    query: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    expand_window: int = 0,
    diagnostics: bool = False,
    collection: str = "documents",
    metadata_filter: dict | None = None,
    ctx: Context | None = None,
    client_round_1: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_1)] = None,
    client_round_2: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_2)] = None,
    client_round_3: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_3)] = None,
    client_round_4: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_4)] = None,
) -> dict:
    """Answer a query with citations over the indexed documents.

    Retrieval runs through the same profile-resolved path as
    ``search_documents``; the answer is synthesised only from the
    retrieved evidence and every citation is built from chunk lineage,
    never from model-invented identifiers.

    Args:
        query: Natural language question.
        top_k: Maximum chunks to use as evidence (profile default).
        similarity_threshold: Minimum evidence score.
        rerank: Tri-state rerank control.
        hybrid: Tri-state hybrid retrieval control.
        expand_window: Neighbours merged into each evidence chunk.
        diagnostics: Include per-stage timings and completion counts.
        collection: Collection to answer over.
        metadata_filter: Store filter restricting evidence.
        ctx: MCP request context (injected; absent on direct calls).
        client_round_1..4: Client completions resolved by the MRTR chain
            (framework-injected; never part of the tool schema).

    Returns:
        The answer result dict; errors are returned, never raised.
    """
    try:
        effective = _get_profile_resolver().resolve(collection)
        # Answering is server-level configuration: take the answer block
        # from the composition-root default, not the profile base — with
        # the ADR-059 carve-out: the three verify_* fields survive the
        # profile resolution (profile/env precedence already applied by
        # the resolver), so a profile-enabled judge reaches the build.
        answer_block = _answer_settings()
        if answer_block is not None:
            merged_block = answer_block.model_copy(
                update={
                    "verify_claims": effective.answer.verify_claims,
                    "verify_model": effective.answer.verify_model,
                    "verify_provider": effective.answer.verify_provider,
                }
            )
            effective = effective.model_copy(update={"answer": merged_block})

        # Master switch (review F4): the actionable disabled response is
        # returned BEFORE consuming client replies or selecting a source
        # — the resolvers already refused to issue any Sample.
        if answer_block is not None and not answer_block.enabled:
            return disabled_result(query, "none")

        # Resolver-era failures (review F3) surface as structured errors.
        payload = _peek_payload(ctx, query, collection)
        if payload is not None and payload.failure is not None:
            return _payload_failure_result(query, payload)

        replies = _resolved_replies(client_round_1, client_round_2, client_round_3, client_round_4)
        version, capability = _session_facts(ctx)
        prefer = bool(getattr(answer_block, "prefer_client_sampling", False))
        allow_legacy = bool(getattr(answer_block, "allow_legacy_sampling", False))
        source = select_completion_source(
            protocol_version=version,
            sampling_capability=capability,
            prefer_client=prefer,
            allow_legacy=allow_legacy,
        )

        complete: Any = None
        preflight: Any = None
        label = "none"
        if replies:
            # Resolvers fired: the client's model already answered the
            # planned rounds.  Effective rounds are capped at the chain
            # depth (review F5) so planning and synthesis agree.
            if answer_block is not None:
                capped = answer_block.model_copy(
                    update={"max_rounds": _client_round_cap(answer_block)}
                )
                effective = effective.model_copy(update={"answer": capped})
            complete = _client_seam(replies)
            preflight = consume_preflight(ctx, query, collection, sampling_calls=len(replies))
            label = "client_mrtr"
        elif source == "client_legacy" and ctx is not None:
            complete = lambda prompt: _legacy_complete(ctx, prompt)  # noqa: E731
            label = "client_legacy"
        else:
            llm = compose.build_answer_llm()
            if llm is not None:
                complete = _server_seam(llm)
                label = "server"

        # Claim verification (ADR-059): the judge is ALWAYS the
        # server-side model — never the client's model, whose replies
        # it may be judging.  A build failure degrades to
        # verification_skipped, never a tool error.
        verify_complete: Any = None
        verify_unavailable_reason: str | None = None
        if getattr(effective.answer, "verify_claims", False):
            try:
                verify_llm = compose.build_verify_llm(answer_block=effective.answer)
            except Exception as exc:
                verify_unavailable_reason = (
                    "verification provider unavailable: "
                    f"{type(exc).__name__}: {_error_message(exc)}"
                )
            else:
                if verify_llm is not None:
                    verify_complete = _server_seam(verify_llm)
                else:
                    verify_unavailable_reason = (
                        "verification provider unavailable (no judge configured)"
                    )

        return await answer(
            query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            expand_window=expand_window,
            collection_name=collection,
            metadata_filter=metadata_filter,
            include_diagnostics=diagnostics,
            complete=complete,
            verify_complete=verify_complete,
            verify_unavailable_reason=verify_unavailable_reason,
            completion_source=label,
            rows=preflight,
            reranker=_get_reranker(),
            effective_settings=effective,
        )
    except Exception as exc:  # Never raise from a tool handler (gotcha #1).
        _log_tool_error("answer_documents", exc)
        return {
            "status": "error",
            "query": query,
            "answer": None,
            "citations": [],
            "evidence": [],
            "failure_stage": None,
            "error": _error_message(exc),
            "completion_source": "none",
        }
    finally:
        # Evict this request's cache entry when the body completes (F2).
        _evict_payload(ctx, query, collection)
