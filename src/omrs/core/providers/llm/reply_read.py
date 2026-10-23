"""Shared helpers for reading a raw provider reply (add-chat-reasoning-and-usage D2).

A raw reply from LlamaIndex (``CompletionResponse.raw``) may be a dict, a
pydantic object (the openai ``ChatCompletion``) or a mix of both. The helpers
here read either shape and never raise: an unexpected shape gives ``None``.

:func:`read_openai_reply` is the reader for the OpenAI-shaped providers
(OpenRouter, OpenAI-compatible, llama.cpp).
"""

from __future__ import annotations

from typing import Any

from .reply import NO_FACTS, ReplyFacts


def field(node: Any, name: str) -> Any:
    """Return *name* from a dict or an object, or ``None`` when it is absent."""
    if node is None:
        return None
    if isinstance(node, dict):
        return node.get(name)
    if isinstance(node, (str, bytes, int, float, list, tuple)):
        return None
    try:
        return getattr(node, name, None)
    except Exception:  # noqa: BLE001 - a reader must never raise
        return None


def count(value: Any) -> int | None:
    """Return *value* as a token count, or ``None`` when it is not a whole number of 0 or more."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def money(value: Any) -> float | None:
    """Return *value* as a cost in US dollars, or ``None`` when it is not a number of 0 or more."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def text(value: Any) -> str | None:
    """Return *value* when it is non-empty text, else ``None``."""
    return value if isinstance(value, str) and value else None


def _first_message(raw: Any) -> Any:
    choices = field(raw, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    return field(choices[0], "message")


def read_openai_reply(raw: Any) -> ReplyFacts:
    """Read an OpenAI-shaped chat completion.

    Reasoning comes from ``choices[0].message.reasoning`` (OpenRouter) or
    ``reasoning_content`` (llama.cpp, vLLM). Usage comes from ``usage``:
    ``prompt_tokens``, ``completion_tokens``,
    ``completion_tokens_details.reasoning_tokens`` and ``cost`` when present.

    Args:
        raw: The raw reply, a dict or a ``ChatCompletion`` object.

    Returns:
        The facts found. An unexpected shape gives :data:`NO_FACTS`.
    """
    try:
        message = _first_message(raw)
        reasoning = text(field(message, "reasoning")) or text(field(message, "reasoning_content"))
        usage = field(raw, "usage")
        details = field(usage, "completion_tokens_details")
        return ReplyFacts(
            reasoning,
            count(field(usage, "prompt_tokens")),
            count(field(usage, "completion_tokens")),
            count(field(details, "reasoning_tokens")),
            money(field(usage, "cost")),
        )
    except Exception:  # noqa: BLE001 - a reader must never raise
        return NO_FACTS
