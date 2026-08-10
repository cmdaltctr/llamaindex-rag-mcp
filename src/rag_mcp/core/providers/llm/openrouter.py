"""OpenRouter LLM provider (for metadata classification).

Constructs ``OpenAILike`` LLM pointed at OpenRouter's OpenAI-compatible
``/v1`` endpoint.  Requires the optional dependency
``llama-index-llms-openai-like`` (``uv sync --extra openrouter``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Settings


# The endpoint moves from an inline literal in llamaindex.py to the provider
# definition, which is where the other providers already keep theirs.
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


def build(settings: Settings, *, timeout: float | None = None) -> Any:
    """Construct an ``OpenAILike`` LLM for OpenRouter from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead.

    Returns:
        A configured ``OpenAILike`` LLM.
    """
    from llama_index.llms.openai_like import OpenAILike

    return OpenAILike(
        model=settings.openrouter_llm_model,
        api_base=_OPENROUTER_API_BASE,
        api_key=settings.openrouter_api_key,
        # OpenAILike names this ``timeout``; ``request_timeout`` is the Ollama
        # spelling and is silently dropped, leaving the 60s default in place.
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )
