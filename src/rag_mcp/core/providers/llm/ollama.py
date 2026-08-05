"""Ollama LLM provider (for metadata classification).

Constructs ``Ollama`` LLM from resolved settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``Ollama`` LLM for metadata classification."""
    from llama_index.llms.ollama import Ollama

    return Ollama(
        model=settings.metadata.ollama_classify_model,
        base_url=settings.ollama_base_url,
        request_timeout=settings.metadata.ollama_classify_timeout,
    )
