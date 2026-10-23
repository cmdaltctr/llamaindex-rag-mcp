"""Answer composition for :meth:`omrs.Engine.answer` (design D8).

Lives beside ``engine.py`` so the Engine stays under the 500-line ceiling.
The helpers choose the completion source (the Engine's server model or a
caller's client completion) and build the claim verifier. The verifier is
always the Engine's server-side model; a client completion never replaces it.

A per-request :class:`CompletionLedger` sits beside the seams (ADR-093,
design D1). The seams still return text only; after each call they read the
raw provider reply and record its reasoning text and usage figures, and the
Engine attaches the totals to the answer result (design D3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .core.providers.llm.reply import NO_FACTS, ReplyFacts

if TYPE_CHECKING:
    from .core.answer.synthesis import CompletionSeam
    from .core.settings import EffectiveSettings

logger = logging.getLogger(__name__)

#: Most UTF-8 bytes of reasoning text kept on one answer result, so one
#: runaway reply cannot bloat the saved chat turn (design D3).
REASONING_CAP_BYTES = 65536
_TRUNCATED = "\n\n[reasoning truncated]"
_FIGURES = ("input_tokens", "output_tokens", "reasoning_tokens", "cost_usd")


#: The ledger of the user-profile answer running in this task, if any. The
#: graph path cannot take a ledger argument without a core change, so its
#: resources read the active ledger from here (design D1).
_ACTIVE_LEDGER: ContextVar[CompletionLedger | None] = ContextVar("omrs_ledger", default=None)


def reply_reader(provider: str) -> Callable[[Any], ReplyFacts]:
    """Return the registry's reply reader for *provider* (patched in tests)."""
    from .core.providers.llm.registry import reply_reader as registry_reader

    return registry_reader(provider)


@dataclass
class CompletionLedger:
    """Reasoning text and usage figures of every completion call in one answer.

    Owned by one request. Answer calls add reasoning and usage; judge calls
    add usage only, so the reasoning box shows the answer model's thinking.
    """

    _facts: list[ReplyFacts] = field(default_factory=list)
    _reasoning: list[str] = field(default_factory=list)

    def record(self, facts: ReplyFacts, *, keep_reasoning: bool = True) -> None:
        """Add the facts of one completion call."""
        self._facts.append(facts)
        if keep_reasoning and facts.reasoning:
            self._reasoning.append(facts.reasoning)

    def reasoning(self) -> str | None:
        """Return the answer calls' reasoning joined in call order, capped, or ``None``."""
        if not self._reasoning:
            return None
        text = "\n\n".join(self._reasoning)
        data = text.encode("utf-8")
        if len(data) <= REASONING_CAP_BYTES:
            return text
        keep = REASONING_CAP_BYTES - len(_TRUNCATED.encode("utf-8"))
        return data[:keep].decode("utf-8", errors="ignore") + _TRUNCATED

    def usage(self) -> dict[str, Any]:
        """Return summed figures; a figure is ``None`` unless every call reported it."""
        totals: dict[str, Any] = {}
        for name in _FIGURES:
            values = [getattr(f, name) for f in self._facts]
            totals[name] = None if not values or None in values else sum(values)
        if totals["cost_usd"] is not None:
            # Float sums drift (0.001 + 0.0002 + 0.0002); providers report far fewer digits.
            totals["cost_usd"] = round(totals["cost_usd"], 12)
        return {**totals, "calls": len(self._facts)}

    def attach(self, result: dict[str, Any]) -> dict[str, Any]:
        """Return *result* with ``usage`` and ``reasoning`` when a model call ran."""
        if not self._facts:
            return result
        extra: dict[str, Any] = {"usage": self.usage()}
        reasoning = self.reasoning()
        if reasoning is not None:
            extra["reasoning"] = reasoning
        return {**result, **extra}


@dataclass(frozen=True)
class ClientCompletion:
    """A caller-supplied completion that replaces the server answer model.

    Attributes:
        complete: Async callable taking a prompt and returning completion text.
        source: Label reported as the result's ``completion_source``.
        max_rounds: Cap applied to ``effective.answer.max_rounds``. The
            caller sets it because only the caller knows the round depth
            its client can serve.
    """

    complete: CompletionSeam
    source: Literal["client_mrtr", "client_legacy"]
    max_rounds: int


def server_seam(
    llm: Any,
    ledger: CompletionLedger | None = None,
    read_reply: Callable[[Any], ReplyFacts] | None = None,
    *,
    keep_reasoning: bool = True,
) -> CompletionSeam:
    """Adapt a composition-root LLM to the core async completion seam.

    Args:
        llm: An LLM with ``async acomplete(prompt)``.
        ledger: Receives the facts of each call, or ``None`` to record nothing.
        read_reply: Reads one raw provider reply. ``None`` records empty facts.
        keep_reasoning: Whether the call's reasoning goes to the ledger's
            reasoning text (``False`` for the judge).
    """

    async def seam(prompt: str) -> str:
        completion = await llm.acomplete(prompt)
        if ledger is not None:
            ledger.record(_facts(completion, read_reply), keep_reasoning=keep_reasoning)
        return completion.text

    return seam


def _facts(completion: Any, read_reply: Callable[[Any], ReplyFacts] | None) -> ReplyFacts:
    """Read one reply; a reader failure counts the call with no figures."""
    if read_reply is None:
        return NO_FACTS
    try:
        return read_reply(getattr(completion, "raw", None))
    except Exception as exc:  # A changed reply shape must never fail the answer.
        logger.warning("Could not read the provider reply: %s", type(exc).__name__)
        return NO_FACTS


def select_completion(
    effective: EffectiveSettings,
    client_completion: ClientCompletion | None,
    get_server_llm: Callable[[], Any],
    ledger: CompletionLedger | None = None,
) -> tuple[CompletionSeam | None, EffectiveSettings, str]:
    """Choose the answer model for one request.

    Args:
        effective: Settings resolved for the collection.
        client_completion: The caller's completion, or ``None``.
        get_server_llm: Returns the Engine's lazily built answer LLM, or
            ``None`` when none is configured. Not called when a client
            completion is set.
        ledger: Records the server model's calls. Ignored for a client
            completion, whose model OMRS cannot see.

    Returns:
        ``(complete, settings, source)``. *settings* carries the capped
        answer block when a client completion is set, else it is *effective*.
    """
    if client_completion is not None:
        capped = effective.answer.model_copy(update={"max_rounds": client_completion.max_rounds})
        return (
            client_completion.complete,
            effective.model_copy(update={"answer": capped}),
            client_completion.source,
        )
    llm = get_server_llm()
    if llm is None:
        return None, effective, "server"
    read = reply_reader(effective.answer.provider.strip()) if ledger is not None else None
    return server_seam(llm, ledger, read), effective, "server"


def build_verifier(
    effective: EffectiveSettings,
    verify_llm_factory: Callable[[Any], Any] | None,
    redact: Callable[[str], str],
    ledger: CompletionLedger | None = None,
) -> tuple[CompletionSeam | None, str | None]:
    """Build the claim verifier when verification is enabled.

    A construction failure degrades to ``verification_skipped`` with the
    redacted provider diagnostic retained (ADR-059). A ``None`` judge keeps
    the plain no-judge reason.

    Args:
        effective: Settings resolved for the collection.
        verify_llm_factory: Builds the judge from the answer block, or ``None``.
        redact: Removes credential values from error text.
        ledger: Records the judge's usage (not its reasoning), or ``None``.

    Returns:
        ``(verify_complete, verify_unavailable_reason)``.
    """
    if not getattr(effective.answer, "verify_claims", False) or verify_llm_factory is None:
        return None, None
    try:
        verify_llm = verify_llm_factory(effective.answer)
    except Exception as exc:
        return None, (
            f"verification provider unavailable: {type(exc).__name__}: {redact(str(exc))}"
        )
    if verify_llm is None:
        return None, "verification provider unavailable (no judge configured)"
    read = reply_reader(_judge_provider(effective)) if ledger is not None else None
    return server_seam(verify_llm, ledger, read, keep_reasoning=False), None


def _judge_provider(effective: EffectiveSettings) -> str:
    """Return the registry name of the judge provider (same alias rule as compose)."""
    from .compose_answer import resolve_verify_provider

    return resolve_verify_provider(effective, getattr(effective.answer, "verify_provider", ""))  # type: ignore[arg-type]


# ── User-profile graph path ─────────────────────────────────────────────


@contextmanager
def collecting(ledger: CompletionLedger) -> Iterator[CompletionLedger]:
    """Make *ledger* the active ledger for graph resources in this task."""
    token = _ACTIVE_LEDGER.set(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE_LEDGER.reset(token)


class _RecordingLLM:
    """Wraps an LLM so each ``acomplete`` records into the active ledger."""

    def __init__(self, llm: Any, provider: str, *, keep_reasoning: bool) -> None:
        self._llm = llm
        self._provider = provider
        self._keep_reasoning = keep_reasoning

    def __getattr__(self, name: str) -> Any:
        # Every other public attribute (model name, metadata) is the wrapped LLM's.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._llm, name)

    async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
        completion = await self._llm.acomplete(prompt, **kwargs)
        ledger = _ACTIVE_LEDGER.get()
        if ledger is not None:
            facts = _facts(completion, reply_reader(self._provider))
            ledger.record(facts, keep_reasoning=self._keep_reasoning)
        return completion


def _wrap(target: Any, provider: str, *, keep_reasoning: bool) -> Any:
    if target is None or not hasattr(target, "acomplete"):
        return target
    return _RecordingLLM(target, provider, keep_reasoning=keep_reasoning)


def recording_answer_llm(
    factory: Callable[[], Any] | None, provider: str
) -> Callable[[], Any] | None:
    """Return the graph ``answer_llm`` resource with ledger recording added."""
    if factory is None:
        return None
    return lambda: _wrap(factory(), provider, keep_reasoning=True)


def recording_judge(
    factory: Callable[[Any], Any] | None, provider_of: Callable[[Any], str]
) -> Callable[[Any], Any] | None:
    """Return the graph ``verify_llm`` resource with ledger recording (usage only)."""
    if factory is None:
        return None
    return lambda block: _wrap(factory(block), provider_of(block), keep_reasoning=False)


def judge_provider_of(effective: EffectiveSettings) -> Callable[[Any], str]:
    """Return a function naming the judge provider for an answer block."""

    def provider_of(block: Any) -> str:
        return _judge_provider(effective.model_copy(update={"answer": block}))

    return provider_of
