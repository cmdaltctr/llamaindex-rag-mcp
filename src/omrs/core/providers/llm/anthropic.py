"""Anthropic LLM provider (Chat answers only).

Constructs the LlamaIndex ``Anthropic`` LLM. The address is fixed. Requires
the optional dependency ``llama-index-llms-anthropic``
(``uv sync --extra anthropic``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
    ReadOnlyValue,
    join_url,
    models_from,
)
from .reply import NO_FACTS, ReplyFacts
from .reply_read import count, field, text

if TYPE_CHECKING:
    from ....config import Settings

_ANTHROPIC_API_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"


def reasoning_kwargs(level: str) -> dict[str, Any] | None:
    """Return ``None``: Anthropic thinking needs a token budget, not a level."""
    return None


def read_reply(raw: Any) -> ReplyFacts:
    """Return thinking text and tokens from an Anthropic message.

    Thinking comes from ``content`` blocks of type ``thinking``, joined with a
    blank line. Usage comes from ``usage.input_tokens`` and
    ``usage.output_tokens``. Anthropic reports no cost.
    """
    try:
        blocks = field(raw, "content")
        thoughts = [
            found
            for block in (blocks if isinstance(blocks, (list, tuple)) else ())
            if field(block, "type") == "thinking" and (found := text(field(block, "thinking")))
        ]
        usage = field(raw, "usage")
        return ReplyFacts(
            reasoning="\n\n".join(thoughts) or None,
            input_tokens=count(field(usage, "input_tokens")),
            output_tokens=count(field(usage, "output_tokens")),
        )
    except Exception:  # noqa: BLE001 - a reader must never raise
        return NO_FACTS


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
    reasoning: str = "",
) -> Any:
    """Construct an Anthropic chat LLM from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the answer composition root
            passes ``answer.timeout``.
        answer_model: The model name. This provider has no model setting of
            its own, so the Chat model is required.
        reasoning: Accepted and ignored: Anthropic needs a token budget, not
            a level (add-chat-reasoning-and-usage D2).

    Returns:
        A configured ``llama_index.llms.anthropic.Anthropic`` LLM.

    Raises:
        ValueError: *answer_model* is missing or blank.
        ModuleNotFoundError: The ``anthropic`` extra is not installed.
    """
    if not (answer_model or "").strip():
        raise ValueError("The Anthropic provider needs a Chat model name.")
    from llama_index.llms.anthropic import Anthropic

    return Anthropic(
        model=answer_model,
        api_key=settings.anthropic_api_key,
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )


def _authorised(settings: Any) -> ConnectionTarget:
    """Return ``GET /v1/models`` with the key; no request without a key."""
    key = settings.anthropic_api_key.strip()
    if not key:
        return ConnectionTarget(())
    return ConnectionTarget(
        join_url(_ANTHROPIC_API_BASE, "/v1/models"),
        {"x-api-key": key, "anthropic-version": _ANTHROPIC_VERSION},
    )


#: Card data for the Anthropic provider (design D5).
CONNECTION = ConnectionDescriptor(
    display_name="Anthropic",
    locality="cloud",
    requires_module="llama_index.llms.anthropic",
    extra="anthropic",
    fields=(
        ConnectionField("api_key", "API key", "secret", "anthropic_api_key", "ANTHROPIC_API_KEY"),
    ),
    read_only=lambda s: [ReadOnlyValue("Address", _ANTHROPIC_API_BASE)],
    test_targets=_authorised,
    models_target=_authorised,
    parse_models=lambda payload: models_from(payload, "data", "id"),
)
