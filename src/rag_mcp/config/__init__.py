"""Typed configuration resolver for the RAG MCP server.

This module is the **single source of truth** for resolved settings.
It resolves values from (lowest → highest priority):

1. Field defaults declared on the ``Settings`` model
2. ``config/defaults.yaml`` (shipped as package data)
3. Environment variables / ``.env``
4. Explicit instantiation arguments

It performs **zero object construction** — no provider instantiation,
no LlamaIndex ``Settings.embed_model`` assignment.  That responsibility
belongs to ``rag_mcp.compose`` (the composition root).

Legacy module-level constants (``TOP_K``, ``CHUNK_SIZE``, etc.) are
resolved via a PEP 562 ``__getattr__`` that reads from the resolved
``Settings`` singleton with a ``DeprecationWarning``.  This keeps
existing imports working during migration.
"""

from __future__ import annotations

import logging
import os
import warnings
from importlib.resources import files
from typing import Annotated, Any

import yaml
from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from dotenv import load_dotenv

from ..core.chunking.settings import ChunkingSettings
from ..core.metadata.settings import MetadataSettings
from ..core.retrieval.settings import RetrievalSettings

load_dotenv()

logger = logging.getLogger(__name__)


# ── Legacy bool parser ──────────────────────────────────────────────
# Pre-refactor code used ``.lower() == "true"`` for boolean env vars.
# Pydantic's native bool parser accepts "1"/"yes"/"on" as True, which
# would be a silent semantic change.  This validator constrains parsing
# to the legacy contract.


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans with legacy ``.lower() == "true"`` semantics."""
    if isinstance(value, str):
        return value.lower() == "true"
    return value


LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]


# ── YAML defaults source ────────────────────────────────────────────


class _YamlDefaultsSource(PydanticBaseSettingsSource):
    """Settings source reading ``config/defaults.yaml`` via importlib.resources.

    YAML keys use the same SCREAMING_SNAKE_CASE as env vars.  Values from
    this source sit between field defaults (lower) and env/.env (higher).
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load_yaml()

    def _load_yaml(self) -> dict[str, Any]:
        """Load defaults.yaml from the package, tolerating missing file."""
        try:
            yaml_path = files("rag_mcp.config") / "defaults.yaml"
            with yaml_path.open("r") as fh:
                data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ModuleNotFoundError):
            return {}

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        value = self._data.get(field_name.upper())
        return value, field_name.upper(), False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            env_key = field_name.upper()
            if env_key in self._data:
                result[field_name] = self._data[env_key]
        return result


# ── Profile YAML source (Phase 4) ───────────────────────────────────


def _load_profile_bundle(profile_name: str) -> dict[str, Any]:
    """Load a profile bundle from ``config/profiles/<name>.yaml``.

    Operational profiles (``documents``, ``codebase``) return their Tier 2
    lever overrides as a flat dict keyed by SCREAMING_SNAKE_CASE env names.

    The ``hybrid`` profile is a mode selector: it declares only a
    ``default_profile`` key.  This function resolves hybrid to the named
    default profile's bundle so the startup Settings carries concrete
    retrieval levers.

    Args:
        profile_name: One of ``documents``, ``codebase``, ``hybrid``.

    Returns:
        Flat dict of profile overrides, or an empty dict if the bundle
        cannot be loaded (graceful degradation).
    """
    try:
        yaml_path = files("rag_mcp.config") / "profiles" / f"{profile_name}.yaml"
        with yaml_path.open("r") as fh:
            data = yaml.safe_load(fh)
    except (FileNotFoundError, ModuleNotFoundError):
        return {}

    if not isinstance(data, dict):
        return {}

    # Hybrid is a mode selector — resolve to its default_profile's bundle.
    if profile_name == "hybrid":
        default_profile = data.get("default_profile", "documents")
        if default_profile not in ("documents", "codebase"):
            default_profile = "documents"
        return _load_profile_bundle(default_profile)

    return data


class _ProfileYamlSettingsSource(PydanticBaseSettingsSource):
    """Settings source reading the selected profile bundle.

    Sits between ``_YamlDefaultsSource`` (defaults.yaml, lower) and the
    environment sources (higher) in the precedence chain.  The profile
    bundle supplies Tier 2 lever overrides for the server-wide default
    profile selected by ``RAG_PROFILE``.

    Per-collection profile resolution at operation time is handled by
    :class:`rag_mcp.core.profiles.resolver.ProfileResolver`, not by this
    source.  This source only affects the startup ``Settings`` singleton.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load_profile()

    def _load_profile(self) -> dict[str, Any]:
        """Load the profile bundle selected by ``RAG_PROFILE``."""
        profile = os.environ.get("RAG_PROFILE", "documents")
        return _load_profile_bundle(profile)

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        value = self._data.get(field_name.upper())
        return value, field_name.upper(), False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            env_key = field_name.upper()
            if env_key in self._data:
                result[field_name] = self._data[env_key]
        return result


# ── Root Settings model ─────────────────────────────────────────────


class Settings(ChunkingSettings, RetrievalSettings, MetadataSettings, BaseSettings):
    """Resolved configuration for the RAG MCP server.

    Composes the per-subpackage settings models (chunking, retrieval,
    metadata) so defaults live near their code (spec: config-composition
    root).  Fields defined here are the cross-cutting knobs that do not
    belong to a single subpackage: storage, provider selection/connection,
    PDF reader, codebase map, and document backend.

    All fields map 1:1 to environment variables (case-insensitive).
    Defaults match the pre-refactor ``config.py`` exactly.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Storage ────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    collection_name: str = "documents"
    chroma_scan_page_size: int = 10000
    vector_store: str = "chroma"

    # ── Provider selection ────────────────────────────────────────
    embed_provider: str = "local"
    metadata_llm_provider: str = "local"
    local_backend: str = "llamacpp"
    cloud_backend: str = "openrouter"

    # ── Provider connection ───────────────────────────────────────
    llamacpp_embed_url: str = "http://localhost:8080/v1"
    llamacpp_embed_model: str = ""
    llamacpp_chat_url: str = "http://localhost:8081/v1"
    llamacpp_chat_model: str = ""
    openrouter_api_key: str = ""
    openrouter_embed_model: str = ""
    openrouter_llm_model: str = ""
    ollama_base_url: str = "http://localhost:11434"
    embed_model: str = ""

    # ── PDF reader ────────────────────────────────────────────────
    pdf_reader: str = "auto"
    liteparse_num_workers: int | None = None
    liteparse_ocr_enabled: LegacyBool = False

    # ── Codebase map ──────────────────────────────────────────────
    magika_binary: str = "magika"
    doc_similarity_threshold: float = 0.85
    codebase_map_cache_dir: str = ".opencode"
    codebase_map_max_files: int = 5000
    codebase_map_max_depth: int = 10

    # ── Document backend ──────────────────────────────────────────
    document_backend: str = "local"
    azure_doc_intelligence_endpoint: str = ""
    azure_doc_intelligence_key: str = ""
    azure_doc_intelligence_model: str = "prebuilt-layout"

    # ── Profiles (Phase 4) ────────────────────────────────────────
    # Server-wide default profile: "documents", "codebase", or "hybrid".
    # When "hybrid", untagged collections resolve to hybrid.yaml's
    # default_profile.  Individual collections override via metadata tags.
    rag_profile: str = "documents"

    # ── Validation ────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate_embed_model_required(self) -> Settings:
        """Preserve the legacy EMBED_MODEL validation.

        EMBED_MODEL is required when the effective embedding provider
        resolves to ollama (either via the flat or two-tier scheme).
        """
        effective = _resolve_effective_embed_provider(self)
        if effective == "ollama" and not self.embed_model:
            raise ValueError(
                "EMBED_MODEL environment variable is required when "
                "the embedding provider is ollama. Set it in a .env file:\n\n"
                "    EMBED_MODEL=qwen3-embedding:8b\n\n"
                "See .env.example for alternatives."
            )
        return self

    @model_validator(mode="after")
    def _validate_provider_selections(self) -> Settings:
        """Clamp unknown provider values to known defaults with a warning."""
        if self.embed_provider not in ("local", "cloud", "ollama", "llamacpp", "openrouter"):
            logger.warning("Unknown EMBED_PROVIDER=%r; falling back to local", self.embed_provider)
            object.__setattr__(self, "embed_provider", "local")

        if self.metadata_llm_provider not in ("local", "cloud"):
            logger.warning("Unknown METADATA_LLM_PROVIDER=%r; falling back to local", self.metadata_llm_provider)
            object.__setattr__(self, "metadata_llm_provider", "local")

        if self.local_backend not in ("llamacpp", "ollama"):
            logger.warning("Unknown LOCAL_BACKEND=%r; falling back to llamacpp", self.local_backend)
            object.__setattr__(self, "local_backend", "llamacpp")

        if self.cloud_backend not in ("openrouter",):
            logger.warning("Unknown CLOUD_BACKEND=%r; falling back to openrouter", self.cloud_backend)
            object.__setattr__(self, "cloud_backend", "openrouter")

        if self.hybrid_sparse_backend not in ("auto", "native", "bm25"):
            logger.warning("Unknown HYBRID_SPARSE_BACKEND=%r; falling back to bm25", self.hybrid_sparse_backend)
            object.__setattr__(self, "hybrid_sparse_backend", "bm25")

        if self.pdf_reader not in ("auto", "liteparse", "pypdfium2", "pypdf"):
            logger.warning("Unknown PDF_READER=%r; falling back to auto", self.pdf_reader)
            object.__setattr__(self, "pdf_reader", "auto")

        if self.document_backend not in ("local", "azure"):
            logger.warning("Unknown DOCUMENT_BACKEND=%r; falling back to local", self.document_backend)
            object.__setattr__(self, "document_backend", "local")

        # Vector store selection (Phase 3, ADR-034).  Only "chroma" is
        # registered today; unknown values raise at compose time with a
        # clear error listing available implementations.
        if self.vector_store not in ("chroma",):
            raise ValueError(
                f"VECTOR_STORE={self.vector_store!r} is not a registered "
                f"implementation. Available: chroma"
            )

        # Azure credential check.
        if self.document_backend == "azure":
            if not self.azure_doc_intelligence_endpoint or not self.azure_doc_intelligence_key:
                logger.warning(
                    "DOCUMENT_BACKEND=azure but AZURE_DOC_INTELLIGENCE_ENDPOINT or "
                    "AZURE_DOC_INTELLIGENCE_KEY is not set. Falling back to local mode."
                )
                object.__setattr__(self, "document_backend", "local")

        # Profile selection (Phase 4).  Unknown values fall back to
        # "documents" with a warning rather than raising — the profile
        # system degrades gracefully to the document-grounding default.
        if self.rag_profile not in ("documents", "codebase", "hybrid"):
            logger.warning(
                "Unknown RAG_PROFILE=%r; falling back to documents",
                self.rag_profile,
            )
            object.__setattr__(self, "rag_profile", "documents")

        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer sources: field defaults < YAML < profile < .env < env < explicit.

        The profile source (Phase 4) sits between defaults.yaml and the
        environment sources so env vars still win over profile bundles.
        """
        yaml_source = _YamlDefaultsSource(settings_cls)
        profile_source = _ProfileYamlSettingsSource(settings_cls)
        return (
            init_settings,        # explicit args (highest)
            env_settings,         # env vars
            dotenv_settings,      # .env file
            profile_source,       # config/profiles/<RAG_PROFILE>.yaml
            yaml_source,          # defaults.yaml
            file_secret_settings, # unused (lowest)
        )


# ── Effective provider resolution ───────────────────────────────────


def _resolve_effective_embed_provider(settings: Settings) -> str:
    """Resolve the effective embedding sub-provider name.

    Handles both the flat scheme (``embed_provider`` = ollama/llamacpp/
    openrouter) and the two-tier scheme (``embed_provider`` = local/cloud
    + ``local_backend``/``cloud_backend``).
    """
    ep = settings.embed_provider
    if ep in ("ollama", "llamacpp"):
        return ep
    if ep == "openrouter":
        return ep
    # Two-tier: local/cloud
    if ep == "local":
        return settings.local_backend
    if ep == "cloud":
        return settings.cloud_backend
    return settings.local_backend  # safe fallback


# ── Runtime resolution (capability probing) ─────────────────────────


def resolve_sparse_backend(settings: Settings) -> str:
    """Resolve the configured sparse backend to ``bm25`` or ``native``.

    Probes ChromaDB's native sparse capability when ``auto`` or
    ``native`` is selected.
    """
    backend = settings.hybrid_sparse_backend
    if backend == "bm25":
        return "bm25"

    from ..core.retrieval.sparse import _detect_native_sparse_capability

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
                "installed. Falling back to pypdf.", reader,
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


# ── Resolved singleton ──────────────────────────────────────────────

def get_settings() -> Settings:
    """Return the resolved Settings singleton.

    On first call the Settings model is instantiated (env + YAML + .env
    resolved).  Subsequent calls return the cached instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


_settings: Settings | None = None
settings = get_settings()

# Resolved runtime values (computed once from the singleton).
RESOLVED_HYBRID_SPARSE_BACKEND = resolve_sparse_backend(settings)
RESOLVED_PDF_READER = resolve_pdf_reader(settings)


def _resolve_sparse_backend() -> str:
    """Backward-compatible no-arg wrapper for ``resolve_sparse_backend``."""
    return resolve_sparse_backend(get_settings())


def _resolve_pdf_reader() -> str:
    """Backward-compatible no-arg wrapper for ``resolve_pdf_reader``."""
    return resolve_pdf_reader(get_settings())


# ── Static constants (not env-configurable) ─────────────────────────

MAGIKA_LABEL_TO_TREESITTER: dict[str, str] = {
    "python": "python", "javascript": "javascript", "typescript": "typescript",
    "tsx": "tsx", "jsx": "jsx", "java": "java", "c": "c", "cpp": "cpp",
    "csharp": "c_sharp", "go": "go", "rust": "rust", "ruby": "ruby",
    "php": "php", "swift": "swift", "kotlin": "kotlin", "scala": "scala",
    "html": "html", "css": "css", "sql": "sql", "bash": "bash",
    "shell": "bash", "yaml": "yaml", "toml": "toml", "json": "json",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}


# ── PEP 562 legacy constant shim ────────────────────────────────────
# Maps each frozen legacy constant name to its Settings field path.
# When code does ``from rag_mcp.config import TOP_K``, Python calls
# ``__getattr__("TOP_K")``, which resolves the value from the Settings
# singleton and emits a DeprecationWarning.

_LEGACY_ALIASES: dict[str, str] = {
    # Direct 1:1 mappings (constant name → settings field name).
    "CHUNK_SIZE": "chunk_size",
    "CHUNK_OVERLAP": "chunk_overlap",
    "MARKDOWN_CHUNK_SIZE": "markdown_chunk_size",
    "MARKDOWN_HEADING_PREPEND": "markdown_heading_prepend",
    "MARKDOWN_MIN_CHUNK_FRACTION": "markdown_min_chunk_fraction",
    "EMBED_CONCURRENCY": "embed_concurrency",
    "EMBED_BATCH_SIZE": "embed_batch_size",
    "TOP_K": "top_k",
    "SIMILARITY_THRESHOLD": "similarity_threshold",
    "RERANK_ENABLED": "rerank_enabled",
    "RERANK_ENABLED_FOR_SEMANTIC": "rerank_enabled_for_semantic",
    "HARD_TECHNICAL_THRESHOLD": "hard_technical_threshold",
    "RERANK_FETCH_MULTIPLIER": "rerank_fetch_multiplier",
    "RERANK_MAX_FETCH": "rerank_max_fetch",
    "RERANK_MODEL": "rerank_model",
    "HYBRID_ENABLED": "hybrid_enabled",
    "HYBRID_RRF_K": "hybrid_rrf_k",
    "HYBRID_SPARSE_BACKEND": "hybrid_sparse_backend",
    "METADATA_EXTRACTION_MODE": "metadata_extraction_mode",
    "METADATA_KEYWORD_RULES": "metadata_keyword_rules",
    "OLLAMA_CLASSIFY_MODEL": "ollama_classify_model",
    "OLLAMA_CLASSIFY_MAX_ATTEMPTS": "ollama_classify_max_attempts",
    "OLLAMA_CLASSIFY_TIMEOUT": "ollama_classify_timeout",
    "CHROMA_PERSIST_DIR": "chroma_persist_dir",
    "COLLECTION_NAME": "collection_name",
    "CHROMA_SCAN_PAGE_SIZE": "chroma_scan_page_size",
    "VECTOR_STORE": "vector_store",
    "EMBED_PROVIDER": "embed_provider",
    "METADATA_LLM_PROVIDER": "metadata_llm_provider",
    "LOCAL_BACKEND": "local_backend",
    "CLOUD_BACKEND": "cloud_backend",
    "LLAMACPP_EMBED_URL": "llamacpp_embed_url",
    "LLAMACPP_EMBED_MODEL": "llamacpp_embed_model",
    "LLAMACPP_CHAT_URL": "llamacpp_chat_url",
    "LLAMACPP_CHAT_MODEL": "llamacpp_chat_model",
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "OPENROUTER_EMBED_MODEL": "openrouter_embed_model",
    "OPENROUTER_LLM_MODEL": "openrouter_llm_model",
    "OLLAMA_BASE_URL": "ollama_base_url",
    "PDF_READER": "pdf_reader",
    "LITEPARSE_OCR_ENABLED": "liteparse_ocr_enabled",
    "MAGIKA_BINARY": "magika_binary",
    "DOC_SIMILARITY_THRESHOLD": "doc_similarity_threshold",
    "CODEBASE_MAP_CACHE_DIR": "codebase_map_cache_dir",
    "CODEBASE_MAP_MAX_FILES": "codebase_map_max_files",
    "CODEBASE_MAP_MAX_DEPTH": "codebase_map_max_depth",
    "DOCUMENT_BACKEND": "document_backend",
    "AZURE_DOC_INTELLIGENCE_ENDPOINT": "azure_doc_intelligence_endpoint",
    "AZURE_DOC_INTELLIGENCE_KEY": "azure_doc_intelligence_key",
    "AZURE_DOC_INTELLIGENCE_MODEL": "azure_doc_intelligence_model",
    "RAG_PROFILE": "rag_profile",
    "CHUNK_STRATEGY_FALLBACK": "chunk_strategy_fallback",
    "METADATA_TAXONOMY_MODE": "metadata_taxonomy_mode",
    # Special alias: EMBED_MODEL_NAME was the old constant for the EMBED_MODEL env var.
    "EMBED_MODEL_NAME": "embed_model",
    # LITEPARSE_NUM_WORKERS needs int parsing.
    "LITEPARSE_NUM_WORKERS": "liteparse_num_workers",
}


def __getattr__(name: str) -> Any:
    """PEP 562: resolve legacy module-level constants from Settings.

    Emits a ``DeprecationWarning`` directing consumers to the structured
    ``settings`` object.
    """
    if name in _LEGACY_ALIASES:
        field = _LEGACY_ALIASES[name]
        warnings.warn(
            f"`from rag_mcp.config import {name}` is deprecated; "
            f"use `from rag_mcp.config import settings; settings.{field}` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        s = get_settings()
        return getattr(s, field)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
