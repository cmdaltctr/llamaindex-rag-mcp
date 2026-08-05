"""Ollama embedding provider.

Constructs ``OllamaEmbedding`` from resolved settings.  The optional
dependency ``llama-index-embeddings-ollama`` is a core dep (always installed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Settings


def build(settings: Settings) -> Any:
    """Construct an ``OllamaEmbedding`` from *settings*.

    Raises:
        ValueError: If ``EMBED_MODEL`` is not set.
    """
    from llama_index.embeddings.ollama import OllamaEmbedding

    if not settings.embed_model:
        raise ValueError(
            "EMBED_MODEL environment variable is required for the ollama "
            "embedding provider."
        )

    return OllamaEmbedding(
        model_name=settings.embed_model,
        base_url=settings.ollama_base_url,
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
