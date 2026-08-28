"""llama.cpp embedding provider.

Constructs ``OpenAIEmbedding`` pointed at a llama.cpp server's OpenAI-
compatible ``/v1`` endpoint.  Requires the optional dependency
``llama-index-embeddings-openai`` (``uv sync --extra llamacpp``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``OpenAIEmbedding`` for llama.cpp from *settings*.

    Raises:
        ImportError: If ``llama-index-embeddings-openai`` is not installed.
    """
    try:
        from llama_index.embeddings.openai import OpenAIEmbedding
    except ImportError:
        raise ImportError(
            "Provider 'llamacpp' requires llama-index-embeddings-openai. "
            "Install it with:  uv sync --extra llamacpp"
        ) from None

    return OpenAIEmbedding(
        model=settings.llamacpp_embed_model,
        api_base=settings.llamacpp_embed_url,
        api_key="no-key",
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
