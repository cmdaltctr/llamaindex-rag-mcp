"""Answer composition for :meth:`omrs.Engine.answer` (design D8).

Lives beside ``engine.py`` so the Engine stays under the 500-line ceiling.
The helpers choose the completion source (the Engine's server model or a
caller's client completion) and build the claim verifier. The verifier is
always the Engine's server-side model; a client completion never replaces it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .core.answer.synthesis import CompletionSeam
    from .core.settings import EffectiveSettings


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


def server_seam(llm: Any) -> CompletionSeam:
    """Adapt a composition-root LLM to the core async completion seam."""

    async def seam(prompt: str) -> str:
        completion = await llm.acomplete(prompt)
        return completion.text

    return seam


def select_completion(
    effective: EffectiveSettings,
    client_completion: ClientCompletion | None,
    get_server_llm: Callable[[], Any],
) -> tuple[CompletionSeam | None, EffectiveSettings, str]:
    """Choose the answer model for one request.

    Args:
        effective: Settings resolved for the collection.
        client_completion: The caller's completion, or ``None``.
        get_server_llm: Returns the Engine's lazily built answer LLM, or
            ``None`` when none is configured. Not called when a client
            completion is set.

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
    return (server_seam(llm) if llm is not None else None), effective, "server"


def build_verifier(
    effective: EffectiveSettings,
    verify_llm_factory: Callable[[Any], Any] | None,
    redact: Callable[[str], str],
) -> tuple[CompletionSeam | None, str | None]:
    """Build the claim verifier when verification is enabled.

    A construction failure degrades to ``verification_skipped`` with the
    redacted provider diagnostic retained (ADR-059). A ``None`` judge keeps
    the plain no-judge reason.

    Args:
        effective: Settings resolved for the collection.
        verify_llm_factory: Builds the judge from the answer block, or ``None``.
        redact: Removes credential values from error text.

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
    return server_seam(verify_llm), None
