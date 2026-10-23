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
* Otherwise: the Engine's lazy server-side model — or, when none is
  configured, core's actionable error naming both options.

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

from ...core.answer.pipeline import disabled_result
from ...engine import ClientCompletion
from .answer_mrtr import (
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
    _session_facts,
    consume_preflight,
    follows_user_profile,
)
from .context import McpContext, mcp_context
from .errors import error_message, log_tool_error

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


async def _legacy_complete(ctx: Any, prompt: str, max_output_tokens: int) -> str:
    """Complete one round through the deprecated sampling back-channel.

    Compatibility path ONLY for a negotiated pre-2026-07-28 session
    (spec scenario: legacy sampling is explicitly negotiated).  The
    transport selection logic guarantees this is never reached on a
    modern session.
    """
    result: CreateMessageResult = await ctx.session.create_message(
        [SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
        max_tokens=max_output_tokens,
    )
    return _result_text(result)


def _payload_failure_result(mcp: McpContext, query: str, payload: Any) -> dict:
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
        "error": f"{verb}: {error_message(mcp, exc)}",
        "completion_source": "none",
    }


DESCRIPTION = (
    "Answer a question from the indexed documents using retrieved "
    "evidence, returning the answer together with deterministic, "
    "verifiable citations (every cited chunk_id re-fetches exactly "
    "one stored chunk). Performs ONE OR MORE language-model "
    "completion calls — use search_documents instead when you only "
    "need ranked chunks without that cost. When ANSWER__VERIFY_CLAIMS "
    "is enabled, each cited claim additionally costs one cloud-judge "
    "call (~3.3 s P95 each, ADR-059). When the server's own model "
    "answers, the result carries usage (tokens, cost in US dollars "
    "and call count; null when the provider did not report a figure). "
    "Set include_reasoning=true to also get the model's reasoning text."
)
ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False)


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
    include_reasoning: bool = False,
    *,
    ctx: Context,
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
        include_reasoning: Keep the model's ``reasoning`` text in the result.
            ``usage`` is returned either way.
        ctx: MCP request context (framework-injected; never part of the tool schema).
        client_round_1..4: Client completions resolved by the MRTR chain
            (framework-injected; never part of the tool schema).

    Returns:
        The answer result dict; errors are returned, never raised.
    """
    mcp = mcp_context(ctx)
    try:
        # D17: a user-profile collection answers through its Answer
        # pipeline with the server model. The binding is checked first, so
        # no client completion or pre-fetched row can reach the pipeline.
        server_model_only = follows_user_profile(mcp.engine, collection)
        effective = mcp.engine.resolve_settings(collection)
        # The resolved answer block already carries the profile/env
        # overlay of the three ADR-059 ``verify_*`` fields.
        answer_block = effective.answer

        # Master switch (review F4): the actionable disabled response is
        # returned BEFORE consuming client replies or selecting a source
        # — the resolvers already refused to issue any Sample.
        if not answer_block.enabled:
            return disabled_result(query, "none")

        # Resolver-era failures (review F3) surface as structured errors.
        payload = _peek_payload(ctx, query, collection)
        if payload is not None and payload.failure is not None:
            return _payload_failure_result(mcp, query, payload)

        replies = (
            []
            if server_model_only
            else _resolved_replies(client_round_1, client_round_2, client_round_3, client_round_4)
        )
        version, capability = _session_facts(ctx)
        source = (
            "server"
            if server_model_only
            else select_completion_source(
                protocol_version=version,
                sampling_capability=capability,
                prefer_client=answer_block.prefer_client_sampling,
                allow_legacy=answer_block.allow_legacy_sampling,
            )
        )

        client_completion: ClientCompletion | None = None
        preflight = None
        if replies:
            # Resolvers fired: the client's model already answered the
            # planned rounds.  Effective rounds are capped at the chain
            # depth (review F5) so planning and synthesis agree.
            client_completion = ClientCompletion(
                complete=_client_seam(replies),
                source="client_mrtr",
                max_rounds=_client_round_cap(answer_block),
            )
            preflight = consume_preflight(ctx, query, collection, sampling_calls=len(replies))
        elif source == "client_legacy":
            max_output_tokens = answer_block.max_output_tokens
            client_completion = ClientCompletion(
                complete=lambda prompt: _legacy_complete(ctx, prompt, max_output_tokens),
                source="client_legacy",
                max_rounds=answer_block.max_rounds,
            )

        # Claim verification (ADR-059) stays Engine-owned and server-side:
        # a client completion never replaces the judge.
        async with mcp.admit():
            result = await mcp.engine.answer(
                query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                rerank=rerank,
                hybrid=hybrid,
                expand_window=expand_window,
                collection_name=collection,
                metadata_filter=metadata_filter,
                include_diagnostics=diagnostics,
                client_completion=client_completion,
                rows=preflight,
            )
        if not include_reasoning and isinstance(result, dict):
            result = {k: v for k, v in result.items() if k != "reasoning"}
        return result
    except Exception as exc:  # Never raise from a tool handler (gotcha #1).
        log_tool_error(mcp, "answer_documents", exc)
        return {
            "status": "error",
            "query": query,
            "answer": None,
            "citations": [],
            "evidence": [],
            "failure_stage": None,
            "error": error_message(mcp, exc),
            "completion_source": "none",
        }
    finally:
        # Evict this request's cache entry when the body completes (F2).
        _evict_payload(ctx, query, collection)
