"""Ollama LLM provider (for metadata classification and answering).

Constructs ``Ollama`` LLM from resolved settings.
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


#: Levels that Ollama's ``think`` field takes as text. Other levels turn
#: thinking on (``True``); ``none`` turns it off.
_THINK_LEVELS = frozenset({"low", "medium", "high"})


def reasoning_kwargs(level: str) -> dict[str, Any] | None:
    """Return ``{"think": ...}`` for reasoning *level*, or ``None`` for an empty level."""
    if not level:
        return None
    if level == "none":
        return {"think": False}
    return {"think": level if level in _THINK_LEVELS else True}


def read_reply(raw: Any) -> ReplyFacts:
    """Return thinking text and tokens from an Ollama chat reply.

    Thinking comes from ``message.thinking``, tokens from ``prompt_eval_count``
    and ``eval_count``. Ollama reports no cost and no separate reasoning count.
    """
    try:
        return ReplyFacts(
            reasoning=text(field(field(raw, "message"), "thinking")),
            input_tokens=count(field(raw, "prompt_eval_count")),
            output_tokens=count(field(raw, "eval_count")),
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
    """Construct an ``Ollama`` LLM from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead, and the answer
            composition root passes ``answer.timeout``.
        answer_model: Backwards-compatible model override used by the
            answering operation so it never silently reuses the
            metadata classification model.  ``None`` keeps the
            metadata-classification model (existing callers).
        reasoning: Reasoning level (add-chat-reasoning-and-usage D2), sent as
            the top-level ``think`` field. Empty sends nothing.

    Returns:
        A configured ``Ollama`` LLM.
    """
    from llama_index.llms.ollama import Ollama

    model = answer_model if answer_model is not None else settings.metadata.ollama_classify_model
    return Ollama(
        model=model,
        base_url=settings.ollama_base_url,
        # An explicit window stops LlamaIndex reading the model maximum from
        # ``/api/show`` and sending it as ``num_ctx`` (TDR-036: 262,144 tokens
        # ran a 4B model out of GPU memory).
        context_window=settings.ollama_context_window,
        # Ollama genuinely accepts ``request_timeout`` — unlike OpenAILike,
        # which names it ``timeout`` and silently drops this spelling.
        request_timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
        # ``think`` is a top-level request field. ``additional_kwargs`` would put
        # it in ``options``, where Ollama ignores it, so it goes in ``thinking``.
        **({"thinking": think["think"]} if (think := reasoning_kwargs(reasoning)) else {}),
    )


def _tags(settings: Any) -> ConnectionTarget:
    return ConnectionTarget(join_url(settings.ollama_base_url, "/api/tags"))


#: Card data for the Ollama provider (design D5).
CONNECTION = ConnectionDescriptor(
    display_name="Ollama",
    locality="local",
    requires_module="llama_index.llms.ollama",
    extra=None,
    fields=(
        ConnectionField("base_url", "Address", "url", "ollama_base_url", "OLLAMA_BASE_URL"),
        ConnectionField(
            "context_window",
            "Context window (tokens)",
            "int",
            "ollama_context_window",
            "OLLAMA_CONTEXT_WINDOW",
            minimum=2048,
            maximum=262144,
        ),
    ),
    read_only=lambda s: [
        ReadOnlyValue("Embedding model", s.embed_model),
        ReadOnlyValue("Metadata model", s.metadata.ollama_classify_model),
    ],
    test_targets=_tags,
    models_target=_tags,
    parse_models=lambda payload: models_from(payload, "models", "name"),
)
