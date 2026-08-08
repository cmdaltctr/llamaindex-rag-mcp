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
from ..core.ingestion.settings import IngestionSettings
from ..core.metadata.settings import MetadataSettings
from ..core.retrieval.settings import RetrievalSettings

load_dotenv()

from .sources import LegacyBool  # noqa: E402

logger = logging.getLogger(__name__)


# ── Root Settings model ─────────────────────────────────────────────


class Settings(BaseSettings):
    """Resolved configuration for the RAG MCP server.

    Composes the per-subpackage settings models by **nesting** (PROPOSAL
    §4.3), so defaults live near their code and each block owns its own
    namespace. Fields defined here are the cross-cutting knobs that belong
    to no single subpackage: storage, provider selection/connection, PDF
    reader, codebase map, and document backend.

    Environment variables:

    * Subpackage fields use the nested delimiter — ``RETRIEVAL__TOP_K``,
      ``CHUNKING__CHUNK_SIZE``, ``INGESTION__EMBED_CONCURRENCY``,
      ``METADATA__EXTRACTION_MODE``.
    * Cross-cutting fields keep their flat names — ``EMBED_MODEL``,
      ``RAG_PROFILE``, ``PDF_READER``, credentials, and so on.

    This is a **breaking change** from the pre-v2.0.0 flat interface. The
    pre-v2 flat subpackage names are not accepted as aliases; a startup
    validator raises with the nested replacement if it finds one.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        # The ROOT model stays permissive: it coexists with unrelated
        # process environment entries (PATH, HOME, CI vars). The four
        # subpackage models set extra="forbid", so a mistyped nested key
        # still fails loudly — see design.md D9.
        extra="ignore",
    )

    # ── Nested subpackage blocks ───────────────────────────────────
    chunking: ChunkingSettings = ChunkingSettings()
    ingestion: IngestionSettings = IngestionSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    metadata: MetadataSettings = MetadataSettings()

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

        if self.retrieval.hybrid_sparse_backend not in ("auto", "native", "bm25"):
            logger.warning(
                "Unknown RETRIEVAL__HYBRID_SPARSE_BACKEND=%r; falling back to bm25",
                self.retrieval.hybrid_sparse_backend,
            )
            # Write to the block that owns the field.  Every other clamp in this
            # validator targets a root field, so `self` is correct for them; this
            # one moved into `retrieval` with the v2 nesting and the write side
            # was never updated, leaving the fallback silently inert.
            object.__setattr__(self.retrieval, "hybrid_sparse_backend", "bm25")

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

# NOTE (task 5.7): the module-level ``settings = get_settings()`` singleton
# and the RESOLVED_* constants derived from it were deleted in v2.0.0.
# Importing this module now performs no environment or YAML resolution.
# ``compose.py`` is the only production caller of ``get_settings()``; every
# other layer receives a frozen ``EffectiveSettings`` by injection.
#
# The runtime capability probes (sparse backend, PDF reader) moved to
# ``compose.py`` — they are construction concerns, and keeping them here
# forced ``config`` to import ``core.retrieval.sparse``, inverting the
# layering (finding F3).


# ── PEP 562 legacy constant shim ────────────────────────────────────
# Maps each frozen legacy constant name to its Settings field path.
# When code does ``from rag_mcp.config import TOP_K``, Python calls
# ``__getattr__("TOP_K")``, which resolves the value from the Settings


# ── Re-exports ───────────────────────────────────────────────────────────
# Settings sources and the legacy-name tripwire live in sibling modules
# after the task 8.7 split.

from .legacy import (  # noqa: E402
    _RETIRED_ENV_VARS,
    check_legacy_env_vars,
)
from .sources import (  # noqa: E402
    _load_profile_bundle,
    _parse_legacy_bool,
    _ProfileYamlSettingsSource,
    _YamlDefaultsSource,
)
