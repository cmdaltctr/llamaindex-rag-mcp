"""MRTR machinery for ``answer_documents`` — split from ``answer.py``.

Holds the multi-round-trip request (MRTR) resolver chain, the
per-request retrieval cache, and the completion seams.  The tool and
completion-source selection stay in :mod:`omrg.transports.mcp.answer`.

Why a stable cache identity (review F2): the MCP SDK assigns a NEW
request id to every MRTR retry (the client re-issues ``tools/call``
with ``input_responses``/``request_state`` and resolver bodies re-run),
so keying on ``ctx.request_id`` missed every round — a one-round answer
searched twice, stale entries lingered.  The cache is keyed by the
session's lifespan-context identity (stable across one connection's
rounds, distinct between connections — verified against the pinned
SDK) plus ``(query, collection)``; the tool body evicts its entry when
it completes.

Collision semantics: concurrent answers on one session with the same
``(query, collection)`` but different retrieval arguments share an
entry — the rows come from the first caller's arguments.  Rows are
deterministic for a fixed argument set and the body's pop is
idempotent, so a race loser simply re-retrieves.  Residual risk (a
dead connection's lifespan id being reused with the same query) is
bounded by the process-wide FIFO (32 entries).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Annotated, Any

from mcp.server.mcpserver import Context, Resolve, Sample
from mcp.types import CreateMessageResult, SamplingMessage, TextContent

from ...core.answer.pipeline import ResolvedRetrieval, evidence_rows, labelled_nodes
from ...core.answer.synthesis import plan_next_prompt
from ...core.retrieval import search as _core_search
from . import _get_profile_resolver, _get_reranker

#: Depth of the MRTR resolver chain: at most this many client completion
#: rounds per tool call.  Load-bearing (review F5): the client path
#: caps its effective planning/synthesis rounds at
#: ``min(answer.max_rounds, _MAX_MRTR_ROUNDS)`` so diagnostics never
#: claim rounds the chain cannot serve.
_MAX_MRTR_ROUNDS = 4

#: Bound on in-flight cached answers process-wide (oldest evicts
#: first).  The session identity is part of every key, so entries from
#: different connections never collide however they are evicted.
_REQUEST_CACHE_LIMIT = 32


@dataclass
class _RequestPayload:
    """One in-flight answer's shared state across MRTR rounds."""

    rows: list[dict] | None = None
    evidence: list[dict] | None = None
    retrieval_ms: float = 0.0
    # First failure wins; later rounds and the body consult it (F3).
    failure: BaseException | None = None
    failure_stage: str | None = None
    # Round number -> wall-clock time its Sample was first issued; the
    # next round (or the body) converts the elapsed time into
    # ``sampling_ms`` exactly once (F11).
    issue_times: dict[int, float] = field(default_factory=dict)
    sampling_ms: float = 0.0


#: In-flight payloads keyed by (session identity, query, collection).
_PAYLOADS: dict[tuple, _RequestPayload] = {}
_PAYLOAD_ORDER: deque[tuple] = deque()


def _store_payload(key: tuple, payload: _RequestPayload) -> None:
    """Insert a payload, evicting the oldest beyond the bound."""
    if key not in _PAYLOADS:
        _PAYLOAD_ORDER.append(key)
    _PAYLOADS[key] = payload
    while len(_PAYLOAD_ORDER) > _REQUEST_CACHE_LIMIT:
        oldest = _PAYLOAD_ORDER.popleft()
        _PAYLOADS.pop(oldest, None)


def _outstanding_payloads() -> int:
    """Count cached entries (test/eviction sanity hook)."""
    return len(_PAYLOADS)


def _result_text(result: CreateMessageResult | None) -> str:
    """Extract the text from a client completion result."""
    if result is None:
        return ""
    content = result.content
    return getattr(content, "text", None) or str(content)


def _answer_settings() -> Any:
    """Read the answer block from the composition-root default settings."""
    from ...core.settings import get_default_effective_settings

    settings = get_default_effective_settings()
    return getattr(settings, "answer", None)


def _session_facts(ctx: Context | None) -> tuple[str | None, object | None]:
    """Safely read (protocol_version, sampling_capability) from *ctx*."""
    if ctx is None:
        return None, None
    try:
        version = ctx.protocol_version
    except Exception:
        version = None
    capability = None
    try:
        caps = ctx.client_capabilities
        capability = getattr(caps, "sampling", None) if caps is not None else None
    except Exception:
        capability = None
    return version, capability


def _session_identity(ctx: Context | None) -> int | None:
    """Return a cache identity stable across one connection's MRTR rounds.

    ``request_context.lifespan_context`` is created once per connection
    and shared by every round's context, so its ``id()`` identifies the
    session across retries (unlike ``request_id``, which changes per
    wire request).  ``None`` when no lifespan or no request is bound.
    """
    if ctx is None:
        return None
    try:
        handle = ctx.request_context.lifespan_context
    except Exception:
        return None
    return id(handle) if handle is not None else None


def _cache_key(ctx: Context | None, query: str, collection: str) -> tuple:
    """Build the per-request cache key: session identity plus request."""
    return (_session_identity(ctx), query, collection)


def _peek_payload(ctx: Context | None, query: str, collection: str) -> _RequestPayload | None:
    """Return the in-flight payload for this request, if any (no pop)."""
    return _PAYLOADS.get(_cache_key(ctx, query, collection))


def _evict_payload(ctx: Context | None, query: str, collection: str) -> None:
    """Drop this request's payload once the tool body completes (F2)."""
    key = _cache_key(ctx, query, collection)
    if key in _PAYLOAD_ORDER:
        _PAYLOAD_ORDER.remove(key)
    _PAYLOADS.pop(key, None)


def _record_failure(
    ctx: Context | None,
    query: str,
    collection: str,
    exc: BaseException,
    stage: str,
) -> None:
    """Record a resolver-era failure for the body to convert (F3)."""
    key = _cache_key(ctx, query, collection)
    existing = _PAYLOADS.get(key)
    if existing is not None and existing.failure is not None:
        return  # First failure wins.
    if existing is None:
        _store_payload(key, _RequestPayload(failure=exc, failure_stage=stage))
        return
    existing.failure = exc
    existing.failure_stage = stage


def _flush_round_latency(payload: _RequestPayload, round_number: int) -> None:
    """Convert a served round's issue-to-reply time into ``sampling_ms``."""
    issued_at = payload.issue_times.pop(round_number, None)
    if issued_at is not None:
        payload.sampling_ms += (time.perf_counter() - issued_at) * 1000.0


async def _retrieve(
    query: str,
    collection: str,
    ctx: Context | None,
    **retrieval_kwargs: Any,
) -> _RequestPayload:
    """Retrieve once per request, cache the rows for the whole chain."""
    key = _cache_key(ctx, query, collection)
    existing = _PAYLOADS.get(key)
    if existing is not None and existing.rows is not None:
        return existing

    effective = _get_profile_resolver().resolve(collection)
    answer_block = _answer_settings()
    merged = effective.model_copy(
        update={"answer": answer_block} if answer_block is not None else {}
    )
    # search() is synchronous; off the event loop like search_documents.
    start = time.perf_counter()
    rows = await asyncio.to_thread(
        _core_search,
        query,
        top_k=retrieval_kwargs.get("top_k"),
        similarity_threshold=retrieval_kwargs.get("similarity_threshold"),
        rerank=retrieval_kwargs.get("rerank"),
        hybrid=retrieval_kwargs.get("hybrid"),
        expand_window=retrieval_kwargs.get("expand_window", 0),
        collection_name=collection,
        metadata_filter=retrieval_kwargs.get("metadata_filter"),
        reranker=_get_reranker(),
        effective_settings=merged,
    )
    retrieval_ms = (time.perf_counter() - start) * 1000.0
    payload = _RequestPayload(rows=rows, evidence=evidence_rows(rows), retrieval_ms=retrieval_ms)
    _store_payload(key, payload)
    return payload


def consume_preflight(
    ctx: Context | None,
    query: str,
    collection: str,
    *,
    sampling_calls: int,
) -> ResolvedRetrieval | None:
    """Build the honest preflight stats for the tool body (review F11).

    Flushes the final client round's sampling latency into the payload
    and converts it into the :class:`ResolvedRetrieval` core expects.
    ``None`` when no payload exists (degenerate cache miss — the body
    then retrieves through the normal path).
    """
    payload = _peek_payload(ctx, query, collection)
    if payload is None or payload.rows is None:
        return None
    _flush_round_latency(payload, sampling_calls)
    return ResolvedRetrieval(
        rows=list(payload.rows),
        retrieval_ms=payload.retrieval_ms,
        sampling_ms=payload.sampling_ms,
        sampling_calls=sampling_calls,
    )


def _client_round_cap(block: Any) -> int:
    """Effective rounds on the client path: settings or chain depth (F5)."""
    return min(int(block.max_rounds), _MAX_MRTR_ROUNDS)


async def _ask_round(
    query: str,
    collection: str,
    ctx: Context | None,
    previous_replies: list[str],
    **retrieval_kwargs: Any,
) -> Sample | None:
    """Plan the next client round; ``None`` when no round is needed.

    Every failure is recorded as a sentinel and returns ``None`` (F3):
    resolvers run before the tool body's try block, so an escaping
    exception would surface as a raw tool error instead of the
    structured-result contract.
    """
    block = _answer_settings()
    if block is None or not getattr(block, "enabled", True):
        # Master switch (F4): no Sample issued when answering is off.
        return None
    from .answer import select_completion_source

    version, capability = _session_facts(ctx)
    if (
        select_completion_source(
            protocol_version=version,
            sampling_capability=capability,
            prefer_client=bool(block.prefer_client_sampling),
            allow_legacy=bool(block.allow_legacy_sampling),
        )
        != "client_mrtr"
    ):
        return None

    payload = _peek_payload(ctx, query, collection)
    if payload is not None and payload.failure is not None:
        return None  # A prior round already failed; end the chain.
    if payload is not None:
        _flush_round_latency(payload, len(previous_replies))
    try:
        if payload is None or payload.rows is None:
            payload = await _retrieve(query, collection, ctx, **retrieval_kwargs)
    except Exception as exc:  # Retrieval failed inside the resolver era.
        _record_failure(ctx, query, collection, exc, "retrieval")
        return None
    if not payload.rows:
        return None
    try:
        prompt = await plan_next_prompt(
            query,
            labelled_nodes(payload.evidence or []),
            previous_replies=previous_replies,
            context_window=block.context_window,
            max_output_tokens=block.max_output_tokens,
            max_rounds=_client_round_cap(block),
        )
    except Exception as exc:  # Planning failed inside the resolver era.
        _record_failure(ctx, query, collection, exc, "generation")
        return None
    if prompt is None:
        return None
    payload.issue_times.setdefault(len(previous_replies) + 1, time.perf_counter())
    return Sample(
        messages=[SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
        max_tokens=block.max_output_tokens,
    )


# ── Bounded MRTR resolver chain ────────────────────────────────────────────
# Each resolver re-runs each protocol round; a recorded outcome is
# consulted without re-asking when the planned prompt (deterministic)
# matches.  A resolver returning ``None`` ends the chain.  The cache
# key is (session identity, query, collection), so later rounds and the
# body agree by construction.


async def _mrtr_round_1(
    query: str,
    collection: str = "documents",
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    expand_window: int = 0,
    metadata_filter: dict | None = None,
    ctx: Context | None = None,
) -> Sample | None:
    """Ask the client's model for the first completion round."""
    return await _ask_round(
        query,
        collection,
        ctx,
        [],
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        rerank=rerank,
        hybrid=hybrid,
        expand_window=expand_window,
        metadata_filter=metadata_filter,
    )


async def _mrtr_round_2(
    query: str,
    collection: str = "documents",
    ctx: Context | None = None,
    prior_round_1: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_1)] = None,
) -> Sample | None:
    """Ask the client's model for the second round, if COMPACT refines."""
    if prior_round_1 is None:
        return None
    return await _ask_round(query, collection, ctx, [_result_text(prior_round_1)])


async def _mrtr_round_3(
    query: str,
    collection: str = "documents",
    ctx: Context | None = None,
    prior_round_1: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_1)] = None,
    prior_round_2: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_2)] = None,
) -> Sample | None:
    """Ask the client's model for the third round, if COMPACT refines."""
    if prior_round_1 is None or prior_round_2 is None:
        return None
    replies = [_result_text(prior_round_1), _result_text(prior_round_2)]
    return await _ask_round(query, collection, ctx, replies)


async def _mrtr_round_4(
    query: str,
    collection: str = "documents",
    ctx: Context | None = None,
    prior_round_1: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_1)] = None,
    prior_round_2: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_2)] = None,
    prior_round_3: Annotated[CreateMessageResult | None, Resolve(_mrtr_round_3)] = None,
) -> Sample | None:
    """Ask the client's model for the final bounded round."""
    if prior_round_1 is None or prior_round_2 is None or prior_round_3 is None:
        return None
    replies = [
        _result_text(prior_round_1),
        _result_text(prior_round_2),
        _result_text(prior_round_3),
    ]
    return await _ask_round(query, collection, ctx, replies)


# ── Seam builders ──────────────────────────────────────────────────────────


def _client_seam(replies: list[str]) -> Any:
    """Serve the resolver-resolved client completions positionally.

    An exhausted seam raises rather than replaying the last reply
    (review F5): a synthesis that outlives the rounds the client
    actually served is an honest generation failure, never a silently
    duplicated completion.
    """

    state = {"served": 0}

    async def seam(prompt: str) -> str:
        index = state["served"]
        state["served"] += 1
        if index < len(replies):
            return replies[index]
        raise RuntimeError(
            f"client completion rounds exhausted ({len(replies)} served; "
            f"the synthesis requested round {index + 1})"
        )

    return seam


def _server_seam(llm: Any) -> Any:
    """Adapt the composition-root LLM to the core async completion seam."""

    async def seam(prompt: str) -> str:
        completion = await llm.acomplete(prompt)
        return completion.text

    return seam


def _resolved_replies(*rounds: CreateMessageResult | None) -> list[str]:
    """Collect the client's replies until the chain first broke."""
    replies: list[str] = []
    for result in rounds:
        if result is None:
            break
        replies.append(_result_text(result))
    return replies
