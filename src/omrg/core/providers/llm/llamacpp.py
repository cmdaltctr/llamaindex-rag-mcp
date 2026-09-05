"""llama.cpp LLM provider (for metadata classification).

Constructs ``OpenAILike`` LLM pointed at a llama.cpp server's OpenAI-
compatible ``/v1`` endpoint.  Requires the optional dependency
``llama-index-llms-openai-like`` (``uv sync --extra llamacpp``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
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
