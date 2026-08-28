"""Shared connection configuration for embedding and LLM providers.

Used by both ``providers/embeddings/*`` and ``providers/llm/*`` modules
to read endpoint and key settings from the resolved ``Settings`` object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...config import Settings


def get_embed_endpoint(settings: Settings) -> tuple[str, str, str]:
    """Return ``(api_base, model_name, api_key)`` for the effective embed provider.

    Handles the flat (ollama/llamacpp/openrouter) and two-tier
    (local/cloud + local_backend/cloud_backend) selection schemes.
    """
    from ...config import _resolve_effective_embed_provider

    provider = _resolve_effective_embed_provider(settings)
    if provider == "ollama":
        return (settings.ollama_base_url, settings.embed_model, "")
    if provider == "llamacpp":
        return (settings.llamacpp_embed_url, settings.llamacpp_embed_model, "no-key")
    if provider == "openrouter":
        return ("https://openrouter.ai/api/v1", settings.openrouter_embed_model, settings.openrouter_api_key)
    # Fallback (should not reach here — validated in Settings).
    return (settings.ollama_base_url, settings.embed_model, "")
