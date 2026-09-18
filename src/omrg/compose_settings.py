"""Server-default :class:`EffectiveSettings` construction (change page-level-ocr-routing).

Split out of ``compose.py``, which sits at the 500-line ceiling, the same way
``compose_answer`` and ``compose_engine`` were. ``compose`` re-exports
:func:`settings_to_effective`, so every existing import site is unchanged.
"""

from __future__ import annotations

from typing import Any

from .capabilities import (
    _resolve_sparse_backend_for,
    resolve_document_backend,
    resolve_pdf_reader,
)
from .config import Settings, get_settings


def settings_to_effective(settings: Settings | None = None) -> Any:
    """Produce the server-default :class:`EffectiveSettings` from resolved ``Settings``.

    This is the adapter that bridges the config layer (flat ``Settings``)
    and the core layer (frozen ``EffectiveSettings``). The
    :class:`ProfileResolver` overlays only profile-owned levers (task 4.4).

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A frozen :class:`EffectiveSettings` with cross-cutting fields.
    """
    from .core.settings import (
        AnswerBlock,
        ChunkingBlock,
        EffectiveSettings,
        EmbeddingBlock,
        IngestionBlock,
        MetadataBlock,
        RetrievalBlock,
    )

    if settings is None:
        settings = get_settings()

    if settings.chunking.chunk_overlap >= settings.chunking.markdown_chunk_size:
        raise ValueError("CHUNKING__CHUNK_OVERLAP must be less than CHUNKING__MARKDOWN_CHUNK_SIZE")

    # Nested Settings blocks map 1:1 onto EffectiveSettings blocks — a
    # straight copy plus cross-cutting fields (pre-nested-schema: ~30 names).
    return EffectiveSettings(
        chunking=ChunkingBlock(**settings.chunking.model_dump()),
        ingestion=IngestionBlock(**settings.ingestion.model_dump()),
        embedding=EmbeddingBlock(**settings.embedding.model_dump()),
        retrieval=RetrievalBlock(
            **{
                **settings.retrieval.model_dump(),
                # Bake the RESOLVED backend in: the `auto` probe runs
                # once here, so core/ performs a plain read (task 7.10).
                "hybrid_sparse_backend": _resolve_sparse_backend_for(settings),
            }
        ),
        metadata=MetadataBlock(**settings.metadata.model_dump()),
        answer=AnswerBlock(**settings.answer.model_dump()),
        profile_name=settings.rag_profile,
        chroma_persist_dir=settings.chroma_persist_dir,
        collection_name=settings.collection_name,
        chroma_scan_page_size=settings.chroma_scan_page_size,
        vector_store=settings.vector_store,
        lancedb_uri=settings.lancedb_uri,
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
        # Bake the RESOLVED reader in: the `auto` probe runs once here.
        pdf_reader=resolve_pdf_reader(settings),
        liteparse_num_workers=settings.liteparse_num_workers,
        liteparse_ocr_enabled=settings.liteparse_ocr_enabled,
        ocr_fallback_enabled=settings.ocr_fallback_enabled,
        ocr_fallback_min_confidence=settings.ocr_fallback_min_confidence,
        ocr_fallback_page_fraction=settings.ocr_fallback_page_fraction,
        ocr_routing_unit=settings.ocr_routing_unit,
        ocr_local_min_confidence=settings.ocr_local_min_confidence,
        ocr_local_offline=settings.ocr_local_offline,
        ocr_local_model_directory=settings.ocr_local_model_directory,
        ocr_worker_command=settings.ocr_worker_command,
        ocr_worker_env_dir=settings.ocr_worker_env_dir,
        ocr_worker_request_timeout=settings.ocr_worker_request_timeout,
        magika_binary=settings.magika_binary,
        doc_similarity_threshold=settings.doc_similarity_threshold,
        codebase_map_cache_dir=settings.codebase_map_cache_dir,
        codebase_map_max_files=settings.codebase_map_max_files,
        codebase_map_max_depth=settings.codebase_map_max_depth,
        community_algorithm=settings.community_algorithm.strip() or "louvain",
        community_seed=settings.community_seed,
        # Bake the RESOLVED backend in: azure without the optional SDK
        # degrades to local here, so ingestion performs a plain registry
        # read instead of probing at read time (task 2.4).
        document_backend=resolve_document_backend(settings),
        azure_doc_intelligence_endpoint=settings.azure_doc_intelligence_endpoint,
        azure_doc_intelligence_key=settings.azure_doc_intelligence_key,
        azure_doc_intelligence_model=settings.azure_doc_intelligence_model,
        rag_profile=settings.rag_profile,
    )
