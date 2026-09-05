"""Typed configuration resolver for the RAG MCP server.

This module is the **single source of truth** for resolved settings.
It resolves values from (lowest → highest priority):

1. Field defaults declared on the ``Settings`` model
2. ``config/defaults.yaml`` (shipped as package data)
3. Environment variables / ``.env``
4. Explicit instantiation arguments

It performs **zero object construction** — no provider instantiation,
no LlamaIndex ``Settings.embed_model`` assignment.  That responsibility
belongs to ``omrg.compose`` (the composition root).

Legacy module-level constants (``TOP_K``, ``CHUNK_SIZE``, etc.) are
resolved via a PEP 562 ``__getattr__`` that reads from the resolved
``Settings`` singleton with a ``DeprecationWarning``.  This keeps
existing imports working during migration.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from ..core.answer.settings import AnswerSettings
from ..core.chunking.settings import ChunkingSettings
from ..core.ingestion.settings import IngestionSettings
from ..core.metadata.settings import MetadataSettings
from ..core.retrieval.settings import RetrievalSettings
from ..core.settings import EmbeddingSettings

load_dotenv()

from .sources import LegacyBool  # noqa: E402
from .storage import StorageValidationMixin, source_keys  # noqa: E402

logger = logging.getLogger(__name__)

_METADATA_EXTRACTION_MODES = (
    "disabled",
    "keyword",
    "local",
    "llamaindex",
    "ollama",
    "llamacpp",
    "openrouter",
)


# ── Provider-selection validation helper ──────────────────────────────


def _validate_provider_value(
    obj: object,
    field: str,
    accepted: tuple[str, ...],
    env_name: str,
) -> None:
    """Strip whitespace, reset empty to default, raise on unrecognised value.

    An empty or whitespace-only value (``SETTING=`` in .env) is how operators
    unset a knob, so it resets to the field's declared default rather than
    raising.  A non-empty value not in ``accepted`` raises ValueError naming
    the offending value and the accepted set.  The stripped value is stored
    so that padded input like ``" auto "`` resolves to ``"auto"``.

    Args:
        obj: The model instance owning the field (``self`` or a nested block).
        field: The field name on ``obj``.
        accepted: The recognised values.
        env_name: The environment variable name for the error message.
    """
    raw = getattr(obj, field)
    if not isinstance(raw, str):
        return
    stripped = raw.strip()
    if not stripped:
        # Empty after strip = operator unset the knob.  Reset to the
        # declared default so "" does not reach runtime code that would
        # probe it (e.g. resolve_sparse_backend on "").
        object.__setattr__(obj, field, type(obj).model_fields[field].default)
        return
    if stripped not in accepted:
        raise ValueError(
            f"{env_name}={raw!r} is not recognised. Accepted values: {', '.join(accepted)}."
        )
    # Store the stripped value so " auto " becomes "auto".
    object.__setattr__(obj, field, stripped)


# ── Root Settings model ─────────────────────────────────────────────


class Settings(StorageValidationMixin, BaseSettings):
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
        # process environment entries (PATH, HOME, CI vars). The five
        # subpackage models set extra="forbid", so a mistyped nested key
        # still fails loudly — see design.md D9.
        extra="ignore",
    )

    # ── Nested subpackage blocks ───────────────────────────────────
    chunking: ChunkingSettings = ChunkingSettings()
    ingestion: IngestionSettings = IngestionSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    metadata: MetadataSettings = MetadataSettings()
    answer: AnswerSettings = AnswerSettings()

    # ── Storage ────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    collection_name: str = "documents"
    chroma_scan_page_size: int = 10000
    # Canonical default (make-lancedb-default-and-isolate-chromadb, task 2.1).
    # LanceDB is the qualified base-install backend (ADR-049); Chroma is a
    # supported but quarantined optional extra.
    vector_store: str = "lancedb"
    # Records whether VECTOR_STORE came from an explicit operator source
    # (constructor/CLI, environment, .env) or from shipped defaults. This
    # is internal configuration data, not another backend selector
    # (design D6) — the fail-closed legacy-Chroma gate reads it.
    vector_store_provenance: str = "default"
    # Parent directory for LanceDB tables when VECTOR_STORE=lancedb.
    lancedb_uri: str = "./lancedb"

    # ── Chroma deployment mode ─────────────────────────────────────
    # Local keeps the embedded PersistentClient (unchanged default).
    # Cloud selects hosted Chroma Cloud; the API key never appears in
    # YAML, profiles, logs, or result files — .env only.
    chroma_mode: str = "local"
    chroma_cloud_api_key: str = ""
    chroma_cloud_tenant: str = ""
    chroma_cloud_database: str = ""

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
    pdf_reader: str = "pdf_inspector"
    liteparse_num_workers: int | None = None
    liteparse_ocr_enabled: LegacyBool = False

    # ── Codebase map ──────────────────────────────────────────────
    magika_binary: str = "magika"
    doc_similarity_threshold: float = 0.85
    codebase_map_cache_dir: str = ".opencode"
    codebase_map_max_files: int = 5000
    codebase_map_max_depth: int = 10
    # Community detection algorithm shared by codebase and document graphs.
    # Validation is registry-driven: compose checks the name against the
    # community registry at startup and fails with the available names
    # (config must not duplicate registry knowledge — invariant #10).
    community_algorithm: str = "louvain"
    community_seed: int = 0

    # ── Document backend ──────────────────────────────────────────
    # Declared as a plain string: accepted backend names are registry-
    # owned and validated at the composition boundary
    # (omrg.capabilities.validate_document_backend), so config must
    # not duplicate the accepted-name tuple (invariant #10).  The Azure
    # credential check below stays here deliberately: it is graceful
    # degradation under the cloud-opt-in boundary, not name validation.
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
    # Provider validation runs BEFORE the EMBED_MODEL-required check so a
    # bad EMBED_PROVIDER reports itself, not a missing EMBED_MODEL (§6.1).
    # Pydantic runs mode="after" validators in definition order.
    @model_validator(mode="after")
    def _validate_provider_selections(self) -> Settings:
        """Validate provider-selection fields: raise on unrecognised values.

        Provider settings raise ValueError on an unrecognised non-empty
        value. An empty or
        whitespace-only value (``SETTING=`` in .env) is treated as unset and
        reset to the field's declared default — raising on it would be
        hostile to a common operator idiom.

        DOCUMENT_BACKEND no longer validates names here: accepted names
        are registry-owned and checked at the composition boundary
        (compose → capabilities.validate_document_backend), so config
        keeps only the whitespace/reset idiom for it.

        Deliberate graceful-degradation policies are unchanged:
        DOCUMENT_BACKEND=azure with missing credentials falls back to local
        (cloud-opt-in hard boundary), and an unrecognised RAG_PROFILE falls
        back to documents (profile system design).  PDF_READER's unknown-value
        handling is also unchanged (governed by the pdf-reader capability).
        """
        _validate_provider_value(
            self,
            "embed_provider",
            ("local", "cloud", "ollama", "llamacpp", "openrouter"),
            "EMBED_PROVIDER",
        )
        _validate_provider_value(
            self, "metadata_llm_provider", ("local", "cloud"), "METADATA_LLM_PROVIDER"
        )
        _validate_provider_value(
            self.metadata,
            "extraction_mode",
            _METADATA_EXTRACTION_MODES,
            "METADATA__EXTRACTION_MODE",
        )
        _validate_provider_value(self, "local_backend", ("llamacpp", "ollama"), "LOCAL_BACKEND")
        _validate_provider_value(self, "cloud_backend", ("openrouter",), "CLOUD_BACKEND")
        # Sparse backend names are registry-owned: compose validates
        # RETRIEVAL__HYBRID_SPARSE_BACKEND against the concrete
        # sparse-backend registry at startup and fails listing ``auto``
        # plus the registered names (task 3.5,
        # implement-native-sparse-backend-strategy; document_backend
        # precedent).  Only the §6.10 whitespace idiom stays here:
        # strip padding and reset an empty value to the declared
        # default.
        object.__setattr__(
            self.retrieval,
            "hybrid_sparse_backend",
            self.retrieval.hybrid_sparse_backend.strip() or "bm25",
        )
        _validate_provider_value(
            self.retrieval,
            "rerank_backend",
            ("onnx", "torch"),
            "RETRIEVAL__RERANK_BACKEND",
        )
        # Document backend names are registry-owned: compose validates
        # DOCUMENT_BACKEND against the document-backend registry at
        # startup and fails listing the registered names (task 2.4,
        # register-document-backend-strategies).  Only the §6.10
        # whitespace idiom stays here: strip padding and reset an empty
        # value to the declared default.
        object.__setattr__(self, "document_backend", self.document_backend.strip() or "local")
        # Chroma deployment mode is an explicit selector: API-key presence
        # must NEVER switch storage silently (design decision 1).
        _validate_provider_value(self, "chroma_mode", ("local", "cloud"), "CHROMA_MODE")

        # Azure credential check — deliberate graceful degradation.
        # DOCUMENT_BACKEND=azure is a valid selection, but without
        # credentials the cloud-opt-in hard boundary requires a local
        # fallback.  The diagnostic names the missing credential(s).
        if self.document_backend == "azure":
            missing = [
                name
                for name, value in (
                    ("AZURE_DOC_INTELLIGENCE_ENDPOINT", self.azure_doc_intelligence_endpoint),
                    ("AZURE_DOC_INTELLIGENCE_KEY", self.azure_doc_intelligence_key),
                )
                if not value
            ]
            if missing:
                logger.warning(
                    "DOCUMENT_BACKEND=azure but %s %s not set. Falling back to local mode.",
                    " and ".join(missing),
                    "is" if len(missing) == 1 else "are",
                )
                object.__setattr__(self, "document_backend", "local")

        # PDF reader — governed by the pdf-reader capability spec, which
        # has its own warn-and-fallback contract.  Unchanged here.
        if self.pdf_reader not in ("auto", "liteparse", "pdf_inspector", "pypdfium2", "pypdf"):
            logger.warning("Unknown PDF_READER=%r; falling back to auto", self.pdf_reader)
            object.__setattr__(self, "pdf_reader", "auto")

        # Profile selection (Phase 4).  Unknown values fall back to
        # "documents" with a warning rather than raising — the profile
        # system degrades gracefully to the document-grounding default.
        # This warn-and-fallback is a deliberate design decision, not an
        # oversight: see silent-failure-audit-and-guards/design.md.
        if self.rag_profile not in ("documents", "codebase", "hybrid"):
            logger.warning(
                "Unknown RAG_PROFILE=%r; falling back to documents",
                self.rag_profile,
            )
            object.__setattr__(self, "rag_profile", "documents")

        return self

    @model_validator(mode="after")
    def _validate_embed_model_required(self) -> Settings:
        """Preserve the legacy EMBED_MODEL validation.

        EMBED_MODEL is required when the effective embedding provider
        resolves to ollama (either via the flat or two-tier scheme).
        Runs after _validate_provider_selections so a bad EMBED_PROVIDER
        reports itself, not a missing EMBED_MODEL.
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

        Also records whether an explicit (operator) source resolves
        ``vector_store`` so the provenance validator can distinguish
        operator selection from shipped defaults (task 2.4, design D6).
        """
        yaml_source = _YamlDefaultsSource(settings_cls)
        profile_source = _ProfileYamlSettingsSource(settings_cls)
        cls._explicit_vector_store_sources = {
            "vector_store"
            for source in (init_settings, env_settings, dotenv_settings)
            for key in source_keys(source)
            if key.lower() == "vector_store"
        }
        return (
            init_settings,  # explicit args (highest)
            env_settings,  # env vars
            dotenv_settings,  # .env file
            profile_source,  # config/profiles/<RAG_PROFILE>.yaml
            yaml_source,  # defaults.yaml
            file_secret_settings,  # unused (lowest)
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
# When code does ``from omrg.config import TOP_K``, Python calls
# ``__getattr__("TOP_K")``, which resolves the value from the Settings


# ── Re-exports ───────────────────────────────────────────────────────────
# Settings sources and the legacy-name tripwire live in sibling modules
# after the task 8.7 split.

from .legacy import (  # noqa: E402, F401
    _RETIRED_ENV_VARS,
    check_legacy_env_vars,
)
from .sources import (  # noqa: E402, F401
    _load_profile_bundle,
    _parse_legacy_bool,
    _ProfileYamlSettingsSource,
    _YamlDefaultsSource,
)
