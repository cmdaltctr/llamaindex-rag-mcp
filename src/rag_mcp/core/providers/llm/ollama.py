"""Ollama LLM provider (for metadata classification).

Constructs ``Ollama`` LLM from resolved settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


def build(settings: Settings, *, timeout: float | None = None) -> Any:
    """Construct an ``Ollama`` LLM for metadata classification.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead, since it does far more work
            per call than a single classification.

    Returns:
        A configured ``Ollama`` LLM.
    """
    from llama_index.llms.ollama import Ollama

    return Ollama(
        model=settings.metadata.ollama_classify_model,
        base_url=settings.ollama_base_url,
        # Ollama genuinely accepts ``request_timeout`` — unlike OpenAILike,
        # which names it ``timeout`` and silently drops this spelling.
        request_timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )
