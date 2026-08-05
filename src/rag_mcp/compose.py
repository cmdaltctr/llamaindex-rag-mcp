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


def settings_to_effective(settings: Settings | None = None) -> Any:
    """Produce the server-default :class:`EffectiveSettings` from resolved ``Settings``.

    This is the adapter that bridges the config layer (flat ``Settings``)
    and the core layer (frozen ``EffectiveSettings``).  The
    :class:`ProfileResolver` overlays only the profile-owned levers onto
    the instance this function produces (task 4.4).

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A frozen :class:`EffectiveSettings` with all cross-cutting fields
        populated from *settings*.
    """
    from .core.settings import (
        ChunkingBlock,
        EffectiveSettings,
        IngestionBlock,
        MetadataBlock,
        RetrievalBlock,
    )

    if settings is None:
        settings = get_settings()

    return EffectiveSettings(
        chunking=ChunkingBlock(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            markdown_chunk_size=settings.markdown_chunk_size,
            markdown_heading_prepend=settings.markdown_heading_prepend,
            markdown_min_chunk_fraction=settings.markdown_min_chunk_fraction,
            strategy_fallback=settings.chunk_strategy_fallback,
        ),
        ingestion=IngestionBlock(
            embed_concurrency=settings.embed_concurrency,
            embed_batch_size=settings.embed_batch_size,
        ),
        retrieval=RetrievalBlock(
            top_k=settings.top_k,
            similarity_threshold=settings.similarity_threshold,
            rerank_enabled=settings.rerank_enabled,
            rerank_enabled_for_semantic=settings.rerank_enabled_for_semantic,
            hard_technical_threshold=settings.hard_technical_threshold,
            rerank_fetch_multiplier=settings.rerank_fetch_multiplier,
            rerank_max_fetch=settings.rerank_max_fetch,
            rerank_model=settings.rerank_model,
            hybrid_enabled=settings.hybrid_enabled,
            hybrid_rrf_k=settings.hybrid_rrf_k,
            hybrid_sparse_backend=settings.hybrid_sparse_backend,
        ),
        metadata=MetadataBlock(
            extraction_mode=settings.metadata_extraction_mode,
            keyword_rules=settings.metadata_keyword_rules,
            ollama_classify_model=settings.ollama_classify_model,
            ollama_classify_max_attempts=settings.ollama_classify_max_attempts,
            ollama_classify_timeout=settings.ollama_classify_timeout,
            taxonomy_mode=settings.metadata_taxonomy_mode,
        ),
        profile_name=settings.rag_profile,
        chroma_persist_dir=settings.chroma_persist_dir,
        collection_name=settings.collection_name,
        chroma_scan_page_size=settings.chroma_scan_page_size,
        vector_store=settings.vector_store,
        embed_provider=settings.embed_provider,
        metadata_llm_provider=settings.metadata_llm_provider,
        local_backend=settings.local_backend,
        cloud_backend=settings.cloud_backend,
        llamacpp_embed_url=settings.llamacpp_embed_url,
        llamacpp_embed_model=settings.llamacpp_embed_model,
        llamacpp_chat_url=settings.llamacpp_chat_url,
        llamacpp_chat_model=settings.llamacpp_chat_model,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_embed_model=settings.openrouter_embed_model,
        openrouter_llm_model=settings.openrouter_llm_model,
        ollama_base_url=settings.ollama_base_url,
        embed_model=settings.embed_model,
        pdf_reader=settings.pdf_reader,
        liteparse_num_workers=settings.liteparse_num_workers,
        liteparse_ocr_enabled=settings.liteparse_ocr_enabled,
        magika_binary=settings.magika_binary,
        doc_similarity_threshold=settings.doc_similarity_threshold,
        codebase_map_cache_dir=settings.codebase_map_cache_dir,
        codebase_map_max_files=settings.codebase_map_max_files,
        codebase_map_max_depth=settings.codebase_map_max_depth,
        document_backend=settings.document_backend,
        azure_doc_intelligence_endpoint=settings.azure_doc_intelligence_endpoint,
        azure_doc_intelligence_key=settings.azure_doc_intelligence_key,
        azure_doc_intelligence_model=settings.azure_doc_intelligence_model,
        rag_profile=settings.rag_profile,
    )


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


def build_vector_store(settings: Settings | None = None) -> Any:
    """Construct the vector store from the ``VECTOR_STORE`` setting.

    Phase 3 (ADR-034): the store is constructed in the composition root
    and injected into the ingestion writer and retrieval pipeline.
    Only ``chroma`` is registered today; the Settings validator rejects
    unknown values at construction time with a clear error.

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A :class:`rag_mcp.core.vectordb.base.VectorStore` instance.

    Raises:
        ValueError: If ``VECTOR_STORE`` names an unregistered impl.
    """
    if settings is None:
        settings = get_settings()

    if settings.vector_store == "chroma":
        from .core.vectordb.chroma import build_chroma_vector_store

        return build_chroma_vector_store()

    # The Settings validator should have caught this already, but guard
    # defensively in case Settings was constructed with _env_file=None
    # bypassing validation.
    raise ValueError(
        f"VECTOR_STORE={settings.vector_store!r} is not registered. "
        f"Available: chroma"
    )


def _resolve_all_strategies() -> None:
    """Resolve every registered strategy at startup so a bad ``register()``
    import string fails fast rather than at first query (task 3.6).

    Walks ``available()`` → ``get()`` for all five registries.  Errors are
    logged but do not abort startup — a missing optional dependency for one
    strategy should not prevent the server from starting if that strategy
    is not selected.
    """
    from .core.chunking import registry as chunking_registry
    from .core.metadata import registry as metadata_registry
    from .core.retrieval import registry as retrieval_registry
    from .core.providers.embeddings import registry as embed_registry
    from .core.providers.llm import registry as llm_registry

    for label, registry in (
        ("chunking", chunking_registry),
        ("metadata", metadata_registry),
        ("retrieval", retrieval_registry),
        ("embeddings", embed_registry),
        ("llm", llm_registry),
    ):
        for name in registry.available():
            try:
                registry.get(name)
            except ImportError as exc:
                logger.debug(
                    "Strategy %s/%s skipped (optional dependency missing): %s",
                    label, name, exc,
                )


def ensure_runtime_setup() -> None:
    """Assign ``LlamaIndexSettings.embed_model`` and the default vector store.

    Replaces the import-time side effect previously in ``config.py``.
    Constructs the vector store from the ``VECTOR_STORE`` setting and
    registers it as the process-wide default so all pipeline callers
    share one instance (and one generation counter dict).  Safe to call
    multiple times — only runs once.
    """
    global _runtime_setup_done
    if _runtime_setup_done:
        return
    settings = get_settings()
    try:
        LlamaIndexSettings.embed_model = build_embed_model(settings)
    except (ImportError, ValueError) as exc:
        logger.warning("Failed to construct embedding model: %s", exc)
    try:
        from .core.vectordb import set_default_store

        set_default_store(build_vector_store(settings))
    except (ImportError, ValueError) as exc:
        logger.warning("Failed to construct vector store: %s", exc)
    # Resolve all registered strategies so a bad import string fails fast.
    _resolve_all_strategies()
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
