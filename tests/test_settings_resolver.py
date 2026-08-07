"""Pinning tests for the typed ``Settings`` resolver env-var interface.

Covers OpenSpec change ``phase-2-refactor-config-core-split`` task 2.6.
Every environment variable that the pre-refactor ``config.py`` honoured
SHALL keep the same name, default, and parsing semantics under the new
pydantic-settings resolver.

Each test builds a *fresh* ``Settings`` instance (never the module
singleton) after monkeypatching the environment, so resolution is
deterministic and independent of import-time state.
"""

from __future__ import annotations

import pytest

from rag_mcp.config import Settings


# ── Env var → (field name, documented default) ──────────────────────────
# EMBED_MODEL is handled separately because the model validator requires
# it whenever the effective embedding provider resolves to ollama.

_DEFAULTS: list[tuple[str, str, object]] = [
    # Provider selection.
    ("EMBED_PROVIDER", "embed_provider", "local"),
    ("METADATA_LLM_PROVIDER", "metadata_llm_provider", "local"),
    ("LOCAL_BACKEND", "local_backend", "llamacpp"),
    ("CLOUD_BACKEND", "cloud_backend", "openrouter"),
    # Provider connection.
    ("LLAMACPP_EMBED_URL", "llamacpp_embed_url", "http://localhost:8080/v1"),
    ("LLAMACPP_EMBED_MODEL", "llamacpp_embed_model", ""),
    ("LLAMACPP_CHAT_URL", "llamacpp_chat_url", "http://localhost:8081/v1"),
    ("LLAMACPP_CHAT_MODEL", "llamacpp_chat_model", ""),
    ("OPENROUTER_API_KEY", "openrouter_api_key", ""),
    ("OPENROUTER_EMBED_MODEL", "openrouter_embed_model", ""),
    ("OPENROUTER_LLM_MODEL", "openrouter_llm_model", ""),
    ("OLLAMA_BASE_URL", "ollama_base_url", "http://localhost:11434"),
    ("INGESTION__EMBED_BATCH_SIZE", "ingestion.embed_batch_size", 100),
    # Storage.
    ("CHROMA_PERSIST_DIR", "chroma_persist_dir", "./chroma_db"),
    ("COLLECTION_NAME", "collection_name", "documents"),
    ("CHROMA_SCAN_PAGE_SIZE", "chroma_scan_page_size", 10000),
    # Chunking.
    ("CHUNKING__CHUNK_SIZE", "chunking.chunk_size", 512),
    ("CHUNKING__CHUNK_OVERLAP", "chunking.chunk_overlap", 100),
    ("INGESTION__EMBED_CONCURRENCY", "ingestion.embed_concurrency", 4),
    ("CHUNKING__MARKDOWN_CHUNK_SIZE", "chunking.markdown_chunk_size", 1024),
    ("CHUNKING__MARKDOWN_HEADING_PREPEND", "chunking.markdown_heading_prepend", False),
    ("CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION", "chunking.markdown_min_chunk_fraction", 0.0),
    # Retrieval.
    ("RETRIEVAL__TOP_K", "retrieval.top_k", 10),
    # RERANK_ENABLED: the documents profile (default RAG_PROFILE) sets this
    # to true, restoring ADR-018's balanced intent (M1 behaviour change,
    # Phase 4). The field default is False (post-Experiment 10), but the
    # profile source sits above field defaults in the precedence chain.
    ("RETRIEVAL__RERANK_ENABLED", "retrieval.rerank_enabled", True),
    ("RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC", "retrieval.rerank_enabled_for_semantic", True),
    ("RETRIEVAL__HARD_TECHNICAL_THRESHOLD", "retrieval.hard_technical_threshold", 0.3),
    ("RETRIEVAL__SIMILARITY_THRESHOLD", "retrieval.similarity_threshold", 0.0),
    ("RETRIEVAL__RERANK_FETCH_MULTIPLIER", "retrieval.rerank_fetch_multiplier", 3),
    ("RETRIEVAL__RERANK_MAX_FETCH", "retrieval.rerank_max_fetch", 100),
    ("RETRIEVAL__HYBRID_ENABLED", "retrieval.hybrid_enabled", False),
    ("RETRIEVAL__HYBRID_RRF_K", "retrieval.hybrid_rrf_k", 60),
    ("RETRIEVAL__HYBRID_SPARSE_BACKEND", "retrieval.hybrid_sparse_backend", "bm25"),
    # PDF reader.
    ("PDF_READER", "pdf_reader", "auto"),
    ("LITEPARSE_NUM_WORKERS", "liteparse_num_workers", None),
    ("LITEPARSE_OCR_ENABLED", "liteparse_ocr_enabled", False),
    # Metadata.
    ("METADATA__EXTRACTION_MODE", "metadata.extraction_mode", "llamaindex"),
    ("METADATA__KEYWORD_RULES", "metadata.keyword_rules", None),
    ("METADATA__OLLAMA_CLASSIFY_MODEL", "metadata.ollama_classify_model", "qwen3:0.6b"),
    ("METADATA__CLASSIFY_MAX_ATTEMPTS", "metadata.classify_max_attempts", 3),
    ("METADATA__CLASSIFY_TIMEOUT", "metadata.classify_timeout", 30.0),
    # Codebase map.
    ("MAGIKA_BINARY", "magika_binary", "magika"),
    ("DOC_SIMILARITY_THRESHOLD", "doc_similarity_threshold", 0.85),
    ("CODEBASE_MAP_CACHE_DIR", "codebase_map_cache_dir", ".opencode"),
    ("CODEBASE_MAP_MAX_FILES", "codebase_map_max_files", 5000),
    ("CODEBASE_MAP_MAX_DEPTH", "codebase_map_max_depth", 10),
    # Document backend.
    ("DOCUMENT_BACKEND", "document_backend", "local"),
    ("AZURE_DOC_INTELLIGENCE_ENDPOINT", "azure_doc_intelligence_endpoint", ""),
    ("AZURE_DOC_INTELLIGENCE_KEY", "azure_doc_intelligence_key", ""),
    ("AZURE_DOC_INTELLIGENCE_MODEL", "azure_doc_intelligence_model", "prebuilt-layout"),
]


# ── Env var → (field name, override env string, expected parsed value) ──
# Only fields admitting a distinct *valid* override appear here.  Provider
# fields whose validator clamps unknown values (CLOUD_BACKEND,
# DOCUMENT_BACKEND) and EMBED_MODEL are exercised in dedicated tests.

_OVERRIDES: list[tuple[str, str, str, object]] = [
    # Provider selection.
    ("EMBED_PROVIDER", "embed_provider", "ollama", "ollama"),
    ("METADATA_LLM_PROVIDER", "metadata_llm_provider", "cloud", "cloud"),
    ("LOCAL_BACKEND", "local_backend", "ollama", "ollama"),
    # Provider connection.
    ("LLAMACPP_EMBED_URL", "llamacpp_embed_url", "http://embed:9999/v1", "http://embed:9999/v1"),
    ("LLAMACPP_EMBED_MODEL", "llamacpp_embed_model", "emb.gguf", "emb.gguf"),
    ("LLAMACPP_CHAT_URL", "llamacpp_chat_url", "http://chat:9998/v1", "http://chat:9998/v1"),
    ("LLAMACPP_CHAT_MODEL", "llamacpp_chat_model", "chat.gguf", "chat.gguf"),
    ("OPENROUTER_API_KEY", "openrouter_api_key", "sk-or-test", "sk-or-test"),
    ("OPENROUTER_EMBED_MODEL", "openrouter_embed_model", "or-emb", "or-emb"),
    ("OPENROUTER_LLM_MODEL", "openrouter_llm_model", "or-llm", "or-llm"),
    ("OLLAMA_BASE_URL", "ollama_base_url", "http://ollama:11434", "http://ollama:11434"),
    ("INGESTION__EMBED_BATCH_SIZE", "ingestion.embed_batch_size", "250", 250),
    # Storage.
    ("CHROMA_PERSIST_DIR", "chroma_persist_dir", "/tmp/custom_chroma", "/tmp/custom_chroma"),
    ("COLLECTION_NAME", "collection_name", "my_collection", "my_collection"),
    ("CHROMA_SCAN_PAGE_SIZE", "chroma_scan_page_size", "5000", 5000),
    # Chunking.
    ("CHUNKING__CHUNK_SIZE", "chunking.chunk_size", "999", 999),
    ("CHUNKING__CHUNK_OVERLAP", "chunking.chunk_overlap", "50", 50),
    ("INGESTION__EMBED_CONCURRENCY", "ingestion.embed_concurrency", "8", 8),
    ("CHUNKING__MARKDOWN_CHUNK_SIZE", "chunking.markdown_chunk_size", "2048", 2048),
    ("CHUNKING__MARKDOWN_HEADING_PREPEND", "chunking.markdown_heading_prepend", "true", True),
    ("CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION", "chunking.markdown_min_chunk_fraction", "0.5", 0.5),
    # Retrieval.
    ("RETRIEVAL__TOP_K", "retrieval.top_k", "25", 25),
    ("RETRIEVAL__RERANK_ENABLED", "retrieval.rerank_enabled", "true", True),
    ("RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC", "retrieval.rerank_enabled_for_semantic", "false", False),
    ("RETRIEVAL__HARD_TECHNICAL_THRESHOLD", "retrieval.hard_technical_threshold", "0.7", 0.7),
    ("RETRIEVAL__SIMILARITY_THRESHOLD", "retrieval.similarity_threshold", "0.5", 0.5),
    ("RETRIEVAL__RERANK_FETCH_MULTIPLIER", "retrieval.rerank_fetch_multiplier", "5", 5),
    ("RETRIEVAL__RERANK_MAX_FETCH", "retrieval.rerank_max_fetch", "200", 200),
    ("RETRIEVAL__HYBRID_ENABLED", "retrieval.hybrid_enabled", "true", True),
    ("RETRIEVAL__HYBRID_RRF_K", "retrieval.hybrid_rrf_k", "30", 30),
    ("RETRIEVAL__HYBRID_SPARSE_BACKEND", "retrieval.hybrid_sparse_backend", "native", "native"),
    # PDF reader.
    ("PDF_READER", "pdf_reader", "pypdf", "pypdf"),
    ("LITEPARSE_NUM_WORKERS", "liteparse_num_workers", "4", 4),
    ("LITEPARSE_OCR_ENABLED", "liteparse_ocr_enabled", "true", True),
    # Metadata.
    ("METADATA__EXTRACTION_MODE", "metadata.extraction_mode", "disabled", "disabled"),
    ("METADATA__KEYWORD_RULES", "metadata.keyword_rules", "rules.json", "rules.json"),
    ("METADATA__OLLAMA_CLASSIFY_MODEL", "metadata.ollama_classify_model", "llama3:8b", "llama3:8b"),
    ("METADATA__CLASSIFY_MAX_ATTEMPTS", "metadata.classify_max_attempts", "5", 5),
    ("METADATA__CLASSIFY_TIMEOUT", "metadata.classify_timeout", "60.5", 60.5),
    # Codebase map.
    ("MAGIKA_BINARY", "magika_binary", "/usr/bin/magika", "/usr/bin/magika"),
    ("DOC_SIMILARITY_THRESHOLD", "doc_similarity_threshold", "0.9", 0.9),
    ("CODEBASE_MAP_CACHE_DIR", "codebase_map_cache_dir", ".mycache", ".mycache"),
    ("CODEBASE_MAP_MAX_FILES", "codebase_map_max_files", "10000", 10000),
    ("CODEBASE_MAP_MAX_DEPTH", "codebase_map_max_depth", "20", 20),
    # Document backend (endpoint/key/model keep distinct valid overrides).
    ("AZURE_DOC_INTELLIGENCE_ENDPOINT", "azure_doc_intelligence_endpoint", "https://example.azure.com/", "https://example.azure.com/"),
    ("AZURE_DOC_INTELLIGENCE_KEY", "azure_doc_intelligence_key", "key-123", "key-123"),
    ("AZURE_DOC_INTELLIGENCE_MODEL", "azure_doc_intelligence_model", "prebuilt-read", "prebuilt-read"),
]


def _get_nested(obj: object, dotted: str) -> object:
    """Resolve a dotted field path (``retrieval.top_k``) on nested Settings."""
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Build a fresh ``Settings`` with the ``.env`` source disabled.

    ``_env_file=None`` keeps the test deterministic regardless of any
    stray ``.env`` at the repo root; the YAML + env + field-default
    sources remain active.
    """
    return Settings(_env_file=None)


# ── Default resolution ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "env_name, field_name, expected",
    _DEFAULTS,
    ids=[d[0] for d in _DEFAULTS],
)
def test_env_var_resolves_to_documented_default(
    env_name: str,
    field_name: str,
    expected: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the env var unset, the resolver SHALL yield the documented default."""
    monkeypatch.delenv(env_name, raising=False)
    settings = _fresh_settings(monkeypatch)
    assert _get_nested(settings, field_name) == expected


# ── Env-var override and parsing ────────────────────────────────────────


@pytest.mark.parametrize(
    "env_name, field_name, override_env, expected",
    _OVERRIDES,
    ids=[d[0] for d in _OVERRIDES],
)
def test_env_var_override_parses_correctly(
    env_name: str,
    field_name: str,
    override_env: str,
    expected: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An env-var override SHALL parse to the expected typed value."""
    monkeypatch.setenv(env_name, override_env)
    settings = _fresh_settings(monkeypatch)
    assert _get_nested(settings, field_name) == expected


# ── EMBED_MODEL (validator-gated) ───────────────────────────────────────


def test_embed_model_default_when_provider_not_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EMBED_MODEL defaults to empty string when ollama is not effective."""
    # Flat llamacpp scheme avoids the ollama EMBED_MODEL requirement.
    monkeypatch.setenv("EMBED_PROVIDER", "llamacpp")
    monkeypatch.delenv("EMBED_MODEL", raising=False)
    settings = _fresh_settings(monkeypatch)
    assert settings.embed_model == ""


def test_embed_model_override_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EMBED_MODEL env var SHALL be read into the ``embed_model`` field."""
    monkeypatch.setenv("EMBED_MODEL", "custom-embed-model")
    settings = _fresh_settings(monkeypatch)
    assert settings.embed_model == "custom-embed-model"


def test_embed_model_required_for_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ollama embedding provider without EMBED_MODEL SHALL raise."""
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    monkeypatch.delenv("EMBED_MODEL", raising=False)
    with pytest.raises(ValueError, match="EMBED_MODEL"):
        _fresh_settings(monkeypatch)


# ── Provider-selection clamping ─────────────────────────────────────────


def test_cloud_backend_invalid_value_clamped_to_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLOUD_BACKEND has a single valid value; others clamp to openrouter."""
    monkeypatch.setenv("CLOUD_BACKEND", "definitely-not-a-backend")
    settings = _fresh_settings(monkeypatch)
    assert settings.cloud_backend == "openrouter"


def test_document_backend_azure_without_credentials_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOCUMENT_BACKEND=azure without credentials SHALL fall back to local."""
    monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)
    settings = _fresh_settings(monkeypatch)
    assert settings.document_backend == "local"


def test_document_backend_azure_kept_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOCUMENT_BACKEND=azure with credentials SHALL stay azure."""
    monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "secret-key")
    settings = _fresh_settings(monkeypatch)
    assert settings.document_backend == "azure"


# ── Legacy boolean semantics ────────────────────────────────────────────


@pytest.mark.parametrize(
    "env_value, expected",
    [
        ("1", False),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", False),
        ("on", False),
        ("0", False),
        ("false", False),
        ("", False),
    ],
    ids=["one", "lower-true", "title-true", "upper-true", "yes", "on", "zero", "false", "empty"],
)
def test_legacy_bool_semantics_for_rerank_enabled(
    env_value: str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LegacyBool SHALL treat only the literal ``true`` (case-insensitive) as True.

    Pre-refactor code used ``.lower() == "true"``; pydantic's native bool
    parser (which accepts ``1``/``yes``/``on``) would be a silent semantic
    change.  This guards the legacy contract.
    """
    monkeypatch.setenv("RETRIEVAL__RERANK_ENABLED", env_value)
    settings = _fresh_settings(monkeypatch)
    assert settings.retrieval.rerank_enabled is expected
