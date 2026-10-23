"""Facts read from one raw provider reply (ADR-093, design D2).

Each Chat provider module may define ``read_reply(raw) -> ReplyFacts`` and
``reasoning_kwargs(level) -> dict | None``. The registry looks them up by
attribute, so dispatch never branches on provider names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplyFacts:
    """Reasoning text and usage figures from one completion call.

    A figure is ``None`` when the provider did not report it. ``0`` means
    the provider reported zero.

    Attributes:
        reasoning: Reasoning text kept apart from the answer, or ``None``.
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens.
        reasoning_tokens: Reasoning tokens inside the completion.
        cost_usd: Cost of the call in US dollars.
    """

    reasoning: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None


#: Facts for a reply the provider gives nothing for.
NO_FACTS = ReplyFacts()
