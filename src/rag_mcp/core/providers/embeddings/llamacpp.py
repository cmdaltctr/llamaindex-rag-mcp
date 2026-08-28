"""llama.cpp embedding provider.

Constructs ``OpenAILikeEmbedding`` for a llama.cpp server's OpenAI-compatible
``/v1`` endpoint. This accepts arbitrary local model identifiers and requires
``llama-index-embeddings-openai-like``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``OpenAILikeEmbedding`` for llama.cpp from *settings*.

    Raises:
        ImportError: If ``llama-index-embeddings-openai-like`` is absent.
    """
    try:
        from llama_index.embeddings.openai_like import OpenAILikeEmbedding
    except ImportError:
        raise ImportError(
            "Provider 'llamacpp' requires llama-index-embeddings-openai-like. "
            "Install it with: uv sync --extra llamacpp"
        ) from None

    return OpenAILikeEmbedding(
        model_name=settings.llamacpp_embed_model,
        api_base=settings.llamacpp_embed_url,
        api_key="no-key",
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
