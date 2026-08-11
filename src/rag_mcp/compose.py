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

from .config import Settings, _resolve_effective_embed_provider, get_settings
from .core.providers.embeddings import registry as embed_registry

logger = logging.getLogger(__name__)

# ── Runtime setup state ─────────────────────────────────────────────

_runtime_setup_done: bool = False


# ── Runtime capability probes (moved from config.py, task 7.10) ──────
# These ask the runtime a question ("is native sparse available?", "is
# LiteParse installed?"), which is construction work, not settings data.
# Keeping them in config.py forced it to import core.retrieval.sparse,
# inverting the layering the config-is-leaf contract now forbids.


def resolve_sparse_backend(settings: Settings) -> str:
    """Resolve the configured sparse backend to ``bm25`` or ``native``.

    Probes ChromaDB's native sparse capability when ``auto`` or
    ``native`` is selected.
    """
    backend = settings.retrieval.hybrid_sparse_backend
    if backend == "bm25":
        return "bm25"

    from .core.retrieval.sparse import _detect_native_sparse_capability

    native_available = _detect_native_sparse_capability()
    if backend == "auto":
        return "native" if native_available else "bm25"

    if native_available:
        return "native"

    logger.warning(
        "HYBRID_SPARSE_BACKEND=native was requested, but the installed "
        "ChromaDB runtime does not expose native sparse retrieval for this "
        "project configuration. Falling back to bm25."
    )
    return "bm25"


def resolve_pdf_reader(settings: Settings) -> str:
    """Resolve the configured PDF reader to a concrete backend name.

    Probes imports in preference order: liteparse → pypdfium2 → pypdf.
    Mirrors the pre-refactor ``_resolve_pdf_reader`` logic.
    """
    reader = settings.pdf_reader
    if reader == "pypdf":
        return "pypdf"

    if reader in ("liteparse", "pypdfium2"):
        try:
            __import__(reader)
            return reader
        except ImportError:
            logger.error(
                "PDF_READER=%s was requested but the package is not "
                "installed. Falling back to pypdf.",
                reader,
            )
            return "pypdf"

    # auto resolution: probe in preference order.
    for backend in ("liteparse", "pypdfium2"):
        try:
            __import__(backend)
            logger.info("PDF_READER=auto resolved to %s", backend)
            return backend
        except ImportError:
            continue

    return "pypdf"


def _resolve_sparse_backend_for(settings: Settings) -> str:
    """Resolve ``auto`` to a concrete sparse backend via the capability probe."""
    return resolve_sparse_backend(settings)


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

    # The nested Settings blocks map 1:1 onto the EffectiveSettings blocks,
    # so this is a straight copy plus the cross-cutting fields. Before the
    # nested schema this function had to restate ~30 flat field names.
    return EffectiveSettings(
        chunking=ChunkingBlock(**settings.chunking.model_dump()),
        ingestion=IngestionBlock(**settings.ingestion.model_dump()),
        retrieval=RetrievalBlock(
            **{
                **settings.retrieval.model_dump(),
                # Bake the RESOLVED backend in: the `auto` capability probe
                # runs once here, so core/ performs a plain read instead of
                # probing at query time (task 7.10).
                "hybrid_sparse_backend": _resolve_sparse_backend_for(settings),
            }
        ),
        metadata=MetadataBlock(**settings.metadata.model_dump()),
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
        # Bake the RESOLVED reader in: the `auto` probe (is LiteParse
        # installed?) runs once here, not on every PDF read.
        pdf_reader=resolve_pdf_reader(settings),
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


def build_reranker(settings: Settings | None = None) -> Any:
    """Construct the cross-encoder reranker from resolved settings.

    The reranker is a plain class (former ``__new__`` singleton).  The
    underlying model is cached process-wide inside
    ``core.retrieval._reranker_cache`` keyed by ``(backend, model_id)``,
    so constructing a new instance here does NOT re-download or re-load
    the model.

    Backend selection flows through ``core.retrieval.backend`` so both
    this path and the lazy pipeline path share the same fallback
    behaviour (design decision 5).

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A reranker instance wired to
        ``settings.retrieval.rerank_model`` and selected by
        ``settings.retrieval.rerank_backend``.
    """
    if settings is None:
        settings = get_settings()

    from .core.retrieval.backend import build_reranker_from_settings

    return build_reranker_from_settings(settings)


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

    # Unreachable: the Settings model_validator raises on non-chroma
    # vector_store at construction time (config/__init__.py line 198).
    raise ValueError(f"VECTOR_STORE={settings.vector_store!r} is not registered. Available: chroma")


def build_profile_resolver(settings: Settings | None = None) -> Any:
    """Construct the :class:`ProfileResolver` with its dependencies injected.

    This is the only sanctioned way to build a resolver in production.
    A bare ``ProfileResolver()`` inherits neither the server profile nor the
    server-default :class:`EffectiveSettings`, so every field the profile
    does not own would silently fall back to class defaults instead of the
    operator's configuration (task 4.4/4.5).

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A :class:`ProfileResolver` with ``server_profile`` and ``base``
        injected.
    """
    from .core.profiles import ProfileResolver

    if settings is None:
        settings = get_settings()

    return ProfileResolver(
        server_profile=settings.rag_profile,
        base=settings_to_effective(settings),
    )


def _resolve_active_strategies(settings: Settings) -> None:
    """Resolve the *configured* strategies at startup so a bad ``register()``
    import string fails fast rather than at first query (task 3.6).

    Only the strategies this deployment actually selects are resolved, and
    their errors propagate.  Resolving *every* registered name would defeat
    §4.4 rule 2's lazy-import benefit — it would eagerly import the ONNX
    reranker and every optional provider on each boot — and swallowing the
    errors would make this function a no-op rather than the documented
    fail-fast gate.

    Exhaustive resolution of all registered names is a test-suite concern
    and lives in ``tests/test_registry_contract.py::test_registry_all_names_resolve``.
    """
    from .core.chunking import registry as chunking_registry
    from .core.metadata import registry as metadata_registry
    from .core.providers.embeddings import registry as embed_registry
    from .core.providers.llm import registry as llm_registry

    active: list[tuple[str, Any, str]] = [
        ("chunking", chunking_registry, settings.chunking.strategy_fallback),
        ("metadata", metadata_registry, settings.metadata.extraction_mode),
        ("embeddings", embed_registry, _resolve_effective_embed_provider(settings)),
        ("llm", llm_registry, settings.metadata_llm_provider),
    ]

    for label, registry, name in active:
        if not name or name in ("disabled", "none"):
            continue
        if name not in registry.available():
            # Not a registry-backed selection (e.g. a mode handled inline);
            # leave validation to the consuming dispatcher.
            continue
        registry.get(name)
        logger.debug("Resolved active %s strategy %r at startup", label, name)


def ensure_runtime_setup() -> None:
    """Assign ``LlamaIndexSettings.embed_model`` and the default vector store.

    Replaces the import-time side effect previously in ``config.py``.
    Constructs the vector store from the ``VECTOR_STORE`` setting and
    registers it as the process-wide default so all pipeline callers
    share one instance (and one generation counter dict).  Safe to call
    multiple times — only runs once.

    Construction failures (``ImportError`` for missing optional deps,
    ``ValueError`` for missing credentials) propagate instead of being
    swallowed.  Because this function runs at module scope, the failure
    surfaces at import time — consistent with the existing
    ``VECTOR_STORE`` unknown-value check (ADR-034).
    """
    global _runtime_setup_done
    if _runtime_setup_done:
        return
    # Fail fast on pre-v2.0.0 flat env vars before resolving anything, so an
    # unmigrated .env produces a naming error rather than silent defaults.
    from .config import check_legacy_env_vars

    check_legacy_env_vars()
    settings = get_settings()
    # Construction failures propagate instead of being swallowed.  A process
    # that reports successful startup MUST have a working embed model and a
    # registered default vector store — leaving either unset and continuing
    # turns a construction failure into a confusing downstream error (or
    # silent misbehaviour) instead of a clear startup failure.  Because
    # ensure_runtime_setup() runs at module scope, the failure surfaces at
    # import time, consistent with the existing VECTOR_STORE check.
    LlamaIndexSettings.embed_model = build_embed_model(settings)
    from .core.vectordb import set_default_store

    set_default_store(build_vector_store(settings))
    # Install the process-wide default EffectiveSettings so core entry points
    # have a composition-root-provided fallback when no instance is passed.
    from .core.settings import set_default_effective_settings

    set_default_effective_settings(settings_to_effective(settings))
    # Resolve the configured strategies so a bad import string fails fast.
    _resolve_active_strategies(settings)
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
