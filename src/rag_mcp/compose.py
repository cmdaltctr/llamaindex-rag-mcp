"""Composition root for the RAG MCP server.

This is the **only** module that instantiates provider and pipeline
objects.  It reads the resolved ``Settings`` from ``rag_mcp.config``
and wires objects together by resolving registries.

Importing this module triggers the LlamaIndex global ``Settings.embed_model``
assignment (previously done at import time in ``config.py``).  This means
entry points (``server.py``, ``cli.py``) should import ``compose`` early
in their startup sequence.
"""

from __future__ import annotations

import logging
from typing import Any

from llama_index.core import Settings as LlamaIndexSettings

from .config import Settings, get_settings, _resolve_effective_embed_provider
from .core.providers.embeddings import registry as embed_registry

logger = logging.getLogger(__name__)

# ── Runtime setup state ─────────────────────────────────────────────

_runtime_setup_done: bool = False


def build_embed_model(settings: Settings | None = None) -> Any:
    """Construct the embedding model from resolved settings.

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A LlamaIndex embedding model instance.

    Raises:
        ImportError: If the provider's optional dependency is not installed.
        ValueError: If a required env var is missing.
    """
    if settings is None:
        settings = get_settings()

    provider = _resolve_effective_embed_provider(settings)
    build_fn = embed_registry.get(provider)
    return build_fn(settings)


def build_llm_model(settings: Settings | None = None) -> Any:
    """Construct the LLM model for metadata classification.

    Resolves via the METADATA_LLM_PROVIDER + LOCAL_BACKEND/CLOUD_BACKEND
    two-tier scheme.
    """
    if settings is None:
        settings = get_settings()

    # Resolve the effective LLM provider (same two-tier logic as embeddings).
    if settings.metadata_llm_provider == "local":
        provider = settings.local_backend
    elif settings.metadata_llm_provider == "cloud":
        provider = settings.cloud_backend
    else:
        provider = settings.local_backend

    from .core.providers.llm import registry as llm_registry

    build_fn = llm_registry.get(provider)
    return build_fn(settings)


def build_reranker(settings: Settings | None = None) -> Any:
    """Construct the cross-encoder reranker from resolved settings.

    The reranker is a plain class (former ``__new__`` singleton).  The
    underlying ONNX session is cached process-wide inside
    ``core.retrieval.reranker`` keyed by model ID, so constructing a new
    instance here does NOT re-download or re-load the model.

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A ``CrossEncoderReranker`` instance wired to
        ``settings.rerank_model``.
    """
    if settings is None:
        settings = get_settings()

    from .core.retrieval.reranker import CrossEncoderReranker

    return CrossEncoderReranker(model_id=settings.rerank_model)


def ensure_runtime_setup() -> None:
    """Assign ``LlamaIndexSettings.embed_model`` (once per process).

    This replaces the import-time side effect previously in ``config.py``.
    Safe to call multiple times — only runs once.
    """
    global _runtime_setup_done
    if _runtime_setup_done:
        return
    settings = get_settings()
    try:
        LlamaIndexSettings.embed_model = build_embed_model(settings)
    except (ImportError, ValueError) as exc:
        logger.warning("Failed to construct embedding model: %s", exc)
    _runtime_setup_done = True


def reset_runtime_setup() -> None:
    """Force ``ensure_runtime_setup`` to run again on the next call.

    Used by tests that need to re-trigger setup with different env vars.
    """
    global _runtime_setup_done
    _runtime_setup_done = False


# Trigger runtime setup on import (preserves the pre-refactor side effect
# where importing config.py would set Settings.embed_model).
ensure_runtime_setup()
