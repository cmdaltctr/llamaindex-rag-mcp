"""Composition root for OMRG — Opinionated Modular RAG.

This is the **only** module that instantiates provider and pipeline
objects.  It reads the resolved ``Settings`` from ``omrg.config``
and wires objects together by resolving registries.

Entry points call :func:`ensure_runtime_setup` during startup to assign the
LlamaIndex global ``Settings.embed_model`` and register the default vector
store. Importing this module has no runtime side effects.
"""

from __future__ import annotations

import logging
from typing import Any

from .capabilities import (  # noqa: F401  (re-exported for existing callers/tests)
    _resolve_sparse_backend_for,
    resolve_document_backend,
    resolve_pdf_reader,
    resolve_sparse_backend,
    validate_document_backend,
    validate_sparse_backend,
)
from .config import Settings, _resolve_effective_embed_provider, get_settings
from .core.providers.embeddings import registry as embed_registry

logger = logging.getLogger(__name__)

# Embedding-provider selection is engine scoped: each Engine owns its
# embedder, store and settings, and multiple engines with different
# providers coexist in one process. The legacy ``ensure_runtime_setup``
# path still installs one engine as the process default for transport
# compatibility, but direct Engine construction never mutates the global.
EMBEDDING_PROVIDER_SCOPE = "engine"

# ── Runtime setup state ─────────────────────────────────────────────

_runtime_setup_done: bool = False


# ── Runtime capability probes ────────────────────────────────────────
# resolve_sparse_backend / resolve_pdf_reader / _resolve_sparse_backend_for
# moved to .capabilities (register-document-backend-strategies, task 2.4:
# this module sits at the 500-line ceiling and must not grow inline).
# resolve_document_backend (azure→local SDK degradation) and
# validate_document_backend (registry-owned name validation at startup)
# live there too; both are re-exported above.


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

    # The nested Settings blocks map 1:1 onto the EffectiveSettings blocks,
    # so this is a straight copy plus the cross-cutting fields. Before the
    # nested schema this function had to restate ~30 flat field names.
    return EffectiveSettings(
        chunking=ChunkingBlock(**settings.chunking.model_dump()),
        ingestion=IngestionBlock(**settings.ingestion.model_dump()),
        embedding=EmbeddingBlock(**settings.embedding.model_dump()),
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
        community_algorithm=settings.community_algorithm.strip() or "louvain",
        community_seed=settings.community_seed,
        # Bake the RESOLVED backend in: azure without the optional SDK
        # degrades to local here (with a diagnostic naming the missing
        # dependency), so ingestion performs a plain registry read
        # instead of probing at read time (task 2.4).
        document_backend=resolve_document_backend(settings),
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


def runtime_summary() -> tuple[str, int, int]:
    """Return resolved embedding settings for startup logging."""
    settings = get_settings()
    return (
        settings.embed_model,
        settings.ingestion.embed_batch_size,
        settings.ingestion.embed_concurrency,
    )


def redaction_values() -> dict[str, str]:
    """Return the active credential values used for error-text redaction.

    Composition-root surface for transports that redact tool errors
    (gotcha #1) without calling ``get_settings()`` directly — the
    settings-resolution boundary forbids that outside ``compose``
    siblings.
    """
    settings = get_settings()
    return {
        "chroma_cloud_api_key": settings.chroma_cloud_api_key,
        "chroma_cloud_tenant": settings.chroma_cloud_tenant,
        "chroma_cloud_database": settings.chroma_cloud_database,
        "openrouter_api_key": settings.openrouter_api_key,
    }


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

    Phase 3 (ADR-034) constructed the store in the composition root and
    injected it into the pipeline; this change resolves it through the
    vector-store registry (``core/vectordb/registry.py``) instead of a
    branch over the name (architecture invariant #10).  The registry
    resolves the settings-driven factory registered under the
    configured name; an unregistered name is translated to a
    ``ValueError`` at this boundary listing the registered names,
    which propagates through ``ensure_runtime_setup``.

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A :class:`omrg.core.vectordb.base.VectorStore` instance.

    Raises:
        ValueError: Unregistered ``VECTOR_STORE`` name (lists the
            registered names) or incomplete cloud values.
        RuntimeError: Cloud connection check failed (redacted).
    """
    if settings is None:
        settings = get_settings()

    from .core.vectordb import registry as vectordb_registry

    try:
        # verify_available() distinguishes unknown/absent/partial/broken
        # installs generically (task 3.2) and raises an actionable error
        # naming the backend, required packages, extra, and guidance.
        factory = vectordb_registry.verify_available(settings.vector_store)
    except KeyError as exc:
        # Startup selection errors are ValueError by house convention
        # (see _validate_community_strategy); the registry itself keeps
        # the KeyError pattern shared by every strategy registry.
        raise ValueError(
            f"VECTOR_STORE={settings.vector_store!r} is not a registered vector "
            f"store. Available: {', '.join(vectordb_registry.available())}."
        ) from exc
    return factory(settings)


def storage_summary(settings: Settings | None = None) -> str:
    """One-line storage description for the SELECTED backend (task 2.6)."""
    if settings is None:
        settings = get_settings()
    return _summary_storage(settings)


# Answer-model builder lives in a sibling module (task 2.9: this module
# sits at the 500-line ceiling); re-exported here because the composition
# root is the sanctioned construction surface.  build_verify_llm (ADR-059)
# joins it for the same reason.
from .compose_answer import build_answer_llm, build_verify_llm  # noqa: E402,F401

# Backward-compatible import surface (existing callers/tests).
from .core.vectordb.summary import storage_summary as _summary_storage  # noqa: E402


def build_profile_resolver(
    settings: Settings | None = None,
    *,
    store: Any = None,
    env_overrides: Any = None,
) -> Any:
    """Construct the :class:`ProfileResolver` with its dependencies injected.

    This is the only sanctioned way to build a resolver in production.
    A bare ``ProfileResolver()`` inherits neither the server profile nor the
    server-default :class:`EffectiveSettings`, so every field the profile
    does not own would silently fall back to class defaults instead of the
    operator's configuration (task 4.4/4.5).

    Args:
        settings: Resolved settings (defaults to the singleton).
        store: Optional engine-owned :class:`VectorStore` the resolver
            reads collection metadata from. ``build_engine`` always
            injects the engine's store so profile tags are read from
            the right store in multi-engine processes; legacy transport
            callers omit it and resolve through the process-default
            store.
        env_overrides: Optional snapshot of the applicable profile env
            overrides, captured at composition time so an
            already-constructed engine never observes later environment
            changes. ``None`` keeps the legacy live-environment read.

    Returns:
        A :class:`ProfileResolver` with ``server_profile``, ``base``,
        ``store`` and ``env_overrides`` injected.
    """
    from .core.profiles import ProfileResolver

    if settings is None:
        settings = get_settings()

    return ProfileResolver(
        store=store,
        server_profile=settings.rag_profile,
        base=settings_to_effective(settings),
        env_overrides=env_overrides,
    )


def _validate_community_strategy(settings: Settings) -> None:
    """Validate the community strategy selection strictly at startup.

    Unlike the loop below, an unknown community strategy name FAILS startup
    (spec: community-detection-strategies) — the error lists the registered
    names.  Availability is probed through the registry's registered probe,
    so selecting ``leiden`` without the optional extra fails here with an
    installation instruction instead of silently falling back to Louvain.

    The empty/whitespace value idiom (``COMMUNITY_ALGORITHM=``) resets to
    the ``louvain`` default, matching ``_validate_provider_value`` policy.
    """
    from .core.community import registry as community_registry

    name = settings.community_algorithm.strip() or "louvain"
    if name not in community_registry.available():
        raise ValueError(
            f"COMMUNITY_ALGORITHM={settings.community_algorithm!r} is not a "
            "registered community strategy. Available: "
            f"{', '.join(community_registry.available())}."
        )
    # Resolve the callable (fail-fast on a bad import string) and probe
    # optional-dependency availability (raises ImportError with the
    # installation instruction when the extra is missing).
    community_registry.get(name)
    community_registry.verify_available(name)


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
    ]
    if settings.metadata.extraction_mode in ("llamaindex", "local"):
        # Only these two modes route through the LLM registry (see
        # core.metadata.extractor._LLM_BACKED_MODES). Resolve the
        # local/cloud alias to the concrete backend name here so the
        # actually-selected provider is what gets validated below —
        # not the alias itself, which is always a valid registry miss.
        llm_backend = (
            settings.cloud_backend
            if settings.metadata_llm_provider == "cloud"
            else settings.local_backend
        )
        active.append(("llm", llm_registry, llm_backend))

    # The answer LLM resolves through the same registry: validate the
    # configured provider name fail-fast (task 3.4) so a typo in
    # ANSWER__PROVIDER surfaces at startup, not at first answer.  Only
    # the NAME is validated here — resolving the callable would import
    # the provider module eagerly; ``build_answer_llm`` stays lazy and
    # tolerates a missing optional dependency (retrieval-only startup).
    if settings.answer.enabled:
        _answer_name = settings.answer.provider.strip()
        if _answer_name and _answer_name not in llm_registry.available():
            raise ValueError(
                f"ANSWER__PROVIDER={settings.answer.provider!r} is not a "
                "registered LLM provider. Available: "
                f"{', '.join(llm_registry.available())}."
            )

    # The verification judge (ADR-059) validates the same way as the
    # answer provider above, but only when opted in — the alias
    # resolution and registry check live beside the builder in
    # ``compose_answer`` (this module sits at the 500-line ceiling).
    from .compose_answer import validate_verify_provider

    validate_verify_provider(settings)

    for label, registry, name in active:
        if label == "chunking" and name == "markdown":
            # The default document path is dispatched inline by
            # core.ingestion.chunker, so it has no callable registry entry.
            continue
        if label == "metadata" and name in ("disabled", "local"):
            # Both modes are validated by Settings. ``disabled`` has no
            # implementation, while ``local`` selects a provider strategy
            # inline in core.metadata.extractor.
            continue
        if name not in registry.available():
            available = ", ".join(registry.available())
            if label == "chunking":
                raise ValueError(
                    f"CHUNKING__STRATEGY_FALLBACK={name!r} is not a registered "
                    f"strategy. Available: {available}"
                )
            raise ValueError(
                f"Configured {label} selection {name!r} is not registered. Available: {available}"
            )
        registry.get(name)
        logger.debug("Resolved active %s strategy %r at startup", label, name)

    # Community detection validates strictly: unknown names fail startup
    # (no skip-on-unknown — the error listing available names IS the gate).
    _validate_community_strategy(settings)

    # Document backends validate strictly too (unknown names fail startup
    # listing the registered names, task 2.4).  An unavailable azure SDK
    # degrades to local in settings_to_effective rather than failing here
    # (cloud opt-in, ADR-024) — unlike community strategies, which fail.
    validate_document_backend(settings)
    # Sparse backends validate the same way (task 3.5,
    # implement-native-sparse-backend-strategy): unknown concrete names
    # fail startup listing ``auto`` plus the registered names, backed by
    # the concrete sparse-backend registry.
    validate_sparse_backend(settings)


def _log_norm_guard_state(settings: Settings) -> None:
    """Log the embedding norm guard's disabled state at startup.

    Spec (guard-embedding-normalisation): disabling the guard is an
    explicit operator action and MUST be logged at startup — the guard is
    the only enforcement of the unit-norm contract that makes L2 ranking
    behave like cosine, so an operator who disables it needs the
    consequence visible in the startup log.
    """
    if not settings.embedding.norm_guard_enabled:
        logger.warning(
            "Embedding norm guard is DISABLED (EMBEDDING__NORM_GUARD_ENABLED=false): "
            "vector norms are not verified, so dense L2 ranking silently stops "
            "behaving like cosine if the embedding model emits non-unit vectors."
        )


def ensure_runtime_setup() -> None:
    """Build the default engine from the environment and install it as the process default.

    Delegates construction to ``compose.build_engine()`` (the single
    construction path — the legacy-env tripwire, the recognised-Chroma-data
    protection and the active-strategy validation all run inside the
    builder, before any dependency is constructed), then installs the
    result as the process default store, default effective settings, and
    LlamaIndex global embed model for legacy transport compatibility. The
    builder itself installs nothing.

    Safe to call multiple times — only runs once.
    """
    global _runtime_setup_done
    if _runtime_setup_done:
        return
    engine = build_engine()
    engine._install_as_process_default()
    _runtime_setup_done = True


def reset_runtime_setup() -> None:
    """Force ``ensure_runtime_setup`` to run again on the next call.

    Used by tests that need to re-trigger setup with different env vars.
    """
    global _runtime_setup_done
    _runtime_setup_done = False


# Engine construction lives in a sibling module (this module sits at the
# 500-line ceiling); re-exported here because the composition root is the
# sanctioned construction surface.  configured_vector_store exposes the
# adapter name for transports without a direct get_settings() call.
from .compose_engine import build_engine, configured_vector_store  # noqa: E402,F401
