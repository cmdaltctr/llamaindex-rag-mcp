"""OpenRouter embedding provider.

Constructs ``OpenAILikeEmbedding`` for OpenRouter's OpenAI-compatible API.
This accepts arbitrary OpenRouter embedding model identifiers, including
Qwen models. Requires ``llama-index-embeddings-openai-like``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``OpenAILikeEmbedding`` for OpenRouter from *settings*.

    Configuration is validated before the optional import so a missing
    key or model reports the actual misconfiguration instead of an
    optional-dependency ``ImportError`` on a base install.

    Raises:
        ValueError: If ``OPENROUTER_API_KEY`` or ``OPENROUTER_EMBED_MODEL``
            is not set.
        ImportError: If ``llama-index-embeddings-openai-like`` is absent.
    """
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required for the openrouter embedding provider.")
    if not settings.openrouter_embed_model:
        raise ValueError(
            "OPENROUTER_EMBED_MODEL is required for the openrouter embedding provider."
        )

    try:
        from llama_index.embeddings.openai_like import OpenAILikeEmbedding
    except ImportError:
        raise ImportError(
            "Provider 'openrouter' requires llama-index-embeddings-openai-like. "
            "Install it with: uv sync --extra openrouter"
        ) from None

    return OpenAILikeEmbedding(
        model_name=settings.openrouter_embed_model,
        api_key=settings.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
