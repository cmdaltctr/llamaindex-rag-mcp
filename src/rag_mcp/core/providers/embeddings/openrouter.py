"""OpenRouter embedding provider.

Constructs ``OpenAIEmbedding`` pointed at OpenRouter's API.  Requires
the optional dependency ``llama-index-embeddings-openai``
(``uv sync --extra openrouter``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``OpenAIEmbedding`` for OpenRouter from *settings*.

    Raises:
        ImportError: If ``llama-index-embeddings-openai`` is not installed.
        ValueError: If ``OPENROUTER_API_KEY`` or ``OPENROUTER_EMBED_MODEL``
            is not set.
    """
    try:
        from llama_index.embeddings.openai import OpenAIEmbedding
    except ImportError:
        raise ImportError(
            "Provider 'openrouter' requires llama-index-embeddings-openai. "
            "Install it with:  uv sync --extra openrouter"
        ) from None

    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required for the openrouter embedding provider.")
    if not settings.openrouter_embed_model:
        raise ValueError(
            "OPENROUTER_EMBED_MODEL is required for the openrouter embedding provider."
        )

    return OpenAIEmbedding(
        model=settings.openrouter_embed_model,
        api_key=settings.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
