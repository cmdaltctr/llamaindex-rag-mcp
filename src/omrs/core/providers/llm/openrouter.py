"""OpenRouter LLM provider (for metadata classification).

Constructs ``OpenAILike`` LLM pointed at OpenRouter's OpenAI-compatible
``/v1`` endpoint.  Requires
``llama-index-llms-openai-like``, which is part of the base install (ADR-083).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
    ProviderLookup,
    ReadOnlyValue,
    join_url,
    models_from,
)
from .openrouter_catalogue import parse_credit, parse_reasoning_levels
from .reply import ReplyFacts
from .reply_read import read_openai_reply

if TYPE_CHECKING:
    from ....config import Settings


# The endpoint moves from an inline literal in llamaindex.py to the provider
# definition, which is where the other providers already keep theirs.
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


def reasoning_kwargs(level: str) -> dict[str, Any] | None:
    """Return the request fields for reasoning *level*, or ``None`` for an empty level.

    OpenRouter reads ``reasoning: {"effort": level}`` from the request body.
    The openai client sends unknown body fields through ``extra_body``.
    """
    return {"extra_body": {"reasoning": {"effort": level}}} if level else None


def read_reply(raw: Any) -> ReplyFacts:
    """Return reasoning text, tokens and cost from an OpenRouter chat completion."""
    return read_openai_reply(raw)


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
    reasoning: str = "",
) -> Any:
    """Construct an ``OpenAILike`` LLM for OpenRouter from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead, and the answer
            composition root passes ``answer.timeout``.
        answer_model: Backwards-compatible model override used by the
            answering operation so it never silently reuses the
            metadata classification model.  ``None`` keeps
            ``openrouter_llm_model`` (existing callers).
        reasoning: Reasoning level (add-chat-reasoning-and-usage D2). Empty
            sends nothing, so the model default applies.

    Returns:
        A configured ``OpenAILike`` LLM.
    """
    from llama_index.llms.openai_like import OpenAILike

    return OpenAILike(
        model=(answer_model if answer_model is not None else settings.openrouter_llm_model),
        api_base=_OPENROUTER_API_BASE,
        api_key=settings.openrouter_api_key,
        # The default False sends prompts to the legacy /completions endpoint,
        # where a reasoning model writes its reasoning into the answer (TDR-037).
        is_chat_model=True,
        # OpenAILike names this ``timeout``; ``request_timeout`` is the Ollama
        # spelling and is silently dropped, leaving the 60s default in place.
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
        # An empty level adds nothing, so the request stays as it was.
        **({"additional_kwargs": extra} if (extra := reasoning_kwargs(reasoning)) else {}),
    )


def _authorised(settings: Any, path: str) -> ConnectionTarget:
    """Return a request to ``path`` with the key; no request without a key."""
    key = settings.openrouter_api_key.strip()
    if not key:
        return ConnectionTarget(())
    return ConnectionTarget(
        join_url(_OPENROUTER_API_BASE, path), {"Authorization": f"Bearer {key}"}
    )


#: Card data for the OpenRouter provider (design D5). The connection test
#: uses ``GET /key``, which answers 401 for a wrong key; ``GET /models``
#: returns the public catalogue to anyone.
CONNECTION = ConnectionDescriptor(
    display_name="OpenRouter",
    locality="cloud",
    requires_module="llama_index.llms.openai_like",
    extra="openrouter",
    fields=(
        ConnectionField("api_key", "API key", "secret", "openrouter_api_key", "OPENROUTER_API_KEY"),
    ),
    read_only=lambda s: [
        ReadOnlyValue("Address", _OPENROUTER_API_BASE),
        ReadOnlyValue("Embedding model", s.openrouter_embed_model),
        ReadOnlyValue("Chat model", s.openrouter_llm_model),
    ],
    test_targets=lambda s: _authorised(s, "/key"),
    models_target=lambda s: _authorised(s, "/models"),
    parse_models=lambda payload: models_from(payload, "data", "id"),
    # The public catalogue needs no key, so none is sent (D5).
    reasoning_levels=ProviderLookup(
        target=lambda s: ConnectionTarget(join_url(_OPENROUTER_API_BASE, "/models")),
        parse=parse_reasoning_levels,
    ),
    credit=ProviderLookup(target=lambda s: _authorised(s, "/key"), parse=parse_credit),
)
