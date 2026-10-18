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

if TYPE_CHECKING:
    from ....config import Settings


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
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

    Returns:
        A configured ``Ollama`` LLM.
    """
    from llama_index.llms.ollama import Ollama

    model = answer_model if answer_model is not None else settings.metadata.ollama_classify_model
    return Ollama(
        model=model,
        base_url=settings.ollama_base_url,
        # Ollama genuinely accepts ``request_timeout`` — unlike OpenAILike,
        # which names it ``timeout`` and silently drops this spelling.
        request_timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )


def _tags(settings: Any) -> ConnectionTarget:
    return ConnectionTarget(join_url(settings.ollama_base_url, "/api/tags"))


#: Card data for the Ollama provider (design D5).
CONNECTION = ConnectionDescriptor(
    display_name="Ollama",
    locality="local",
    requires_module="llama_index.llms.ollama",
    extra=None,
    fields=(ConnectionField("base_url", "Address", "url", "ollama_base_url", "OLLAMA_BASE_URL"),),
    read_only=lambda s: [
        ReadOnlyValue("Embedding model", s.embed_model),
        ReadOnlyValue("Metadata model", s.metadata.ollama_classify_model),
    ],
    test_targets=_tags,
    models_target=_tags,
    parse_models=lambda payload: models_from(payload, "models", "name"),
)
