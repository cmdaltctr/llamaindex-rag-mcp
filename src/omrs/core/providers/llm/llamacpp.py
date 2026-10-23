"""llama.cpp LLM provider (for metadata classification).

Constructs ``OpenAILike`` LLM pointed at a llama.cpp server's OpenAI-
compatible ``/v1`` endpoint.  Requires
``llama-index-llms-openai-like``, which is part of the base install (ADR-083).
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
from .reply import ReplyFacts
from .reply_read import read_openai_reply

if TYPE_CHECKING:
    from ....config import Settings


def reasoning_kwargs(level: str) -> dict[str, Any] | None:
    """Return ``None``: llama.cpp has no stable request field for a level."""
    return None


def read_reply(raw: Any) -> ReplyFacts:
    """Return reasoning text and tokens from a llama.cpp chat completion."""
    return read_openai_reply(raw)


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
    reasoning: str = "",
) -> Any:
    """Construct an ``OpenAILike`` LLM for llama.cpp from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead, and the answer
            composition root passes ``answer.timeout``.
        answer_model: Backwards-compatible model override used by the
            answering operation so it never silently reuses the
            metadata classification model.  ``None`` keeps
            ``llamacpp_chat_model`` (existing callers).
        reasoning: Accepted and ignored: llama.cpp has no stable request
            field for a level (add-chat-reasoning-and-usage D2).

    Returns:
        A configured ``OpenAILike`` LLM.
    """
    from llama_index.llms.openai_like import OpenAILike

    return OpenAILike(
        model=(answer_model if answer_model is not None else settings.llamacpp_chat_model),
        api_base=settings.llamacpp_chat_url,
        api_key="no-key",
        # OpenAILike names this ``timeout``; ``request_timeout`` is the Ollama
        # spelling and is silently dropped, leaving the 60s default in place.
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )


def _test_targets(settings: Any) -> ConnectionTarget:
    urls = (
        *join_url(settings.llamacpp_embed_url, "/models"),
        *join_url(settings.llamacpp_chat_url, "/models"),
    )
    return ConnectionTarget(tuple(dict.fromkeys(urls)))


#: Card data for the llama.cpp provider (design D5).
CONNECTION = ConnectionDescriptor(
    display_name="llama.cpp",
    locality="local",
    requires_module="llama_index.llms.openai_like",
    extra="llamacpp",
    fields=(
        ConnectionField(
            "chat_url", "Chat address", "url", "llamacpp_chat_url", "LLAMACPP_CHAT_URL"
        ),
    ),
    read_only=lambda s: [
        ReadOnlyValue("Embedding address", s.llamacpp_embed_url),
        ReadOnlyValue("Embedding model", s.llamacpp_embed_model),
        ReadOnlyValue("Chat model", s.llamacpp_chat_model),
    ],
    test_targets=_test_targets,
    models_target=lambda s: ConnectionTarget(join_url(s.llamacpp_chat_url, "/models")),
    parse_models=lambda payload: models_from(payload, "data", "id"),
)
