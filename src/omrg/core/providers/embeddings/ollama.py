"""Ollama embedding provider.

Constructs ``OllamaEmbedding`` from resolved settings.  The optional
dependency ``llama-index-embeddings-ollama`` is a core dep (always installed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


def build(settings: Settings, *, model: str | None = None) -> Any:
    """Construct an ``OllamaEmbedding`` from *settings*.

    Args:
        settings: Resolved settings (URL and batch size).
        model: Optional model name that replaces ``settings.embed_model``.

    Raises:
        ValueError: If no model is given and ``EMBED_MODEL`` is not set.
    """
    from llama_index.embeddings.ollama import OllamaEmbedding

    model_name = model or settings.embed_model
    if not model_name:
        raise ValueError(
            "EMBED_MODEL environment variable is required for the ollama embedding provider."
        )

    return OllamaEmbedding(
        model_name=model_name,
        base_url=settings.ollama_base_url,
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
