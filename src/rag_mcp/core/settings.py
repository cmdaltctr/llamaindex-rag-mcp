"""Frozen effective settings value object consumed by ``core/`` and ``integrations/``.

This is the single immutable settings object threaded through ``search()`` and
``ingest_path_async()`` and propagated to every module they call
(PROPOSAL §6.3.1, settings-dependency-injection spec).  It composes nested
chunking/ingestion/retrieval/metadata blocks plus the cross-cutting fields
``core/`` needs.

This module is pure data — no imports from ``config``, ``compose``, or any
other ``core/`` module (enforced by the ``settings-models-are-pure-data``
import-linter contract extended in task 10.2).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChunkingBlock(BaseModel):
    """Chunking knobs carried in :attr:`EffectiveSettings.chunking`."""

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    # Sentence/Markdown splitters consume tokenizer units.
    chunk_size: int = 512
    chunk_overlap: int = 100
    markdown_chunk_size: int = 1024

    # LlamaIndex CodeSplitter consumes lines plus a character ceiling.
    # These stay separate from the token-oriented document settings.
    code_chunk_lines: int = 40
    code_chunk_lines_overlap: int = 15
    code_max_chars: int = 1500

    markdown_heading_prepend: bool = False
    markdown_min_chunk_fraction: float = 0.0
    strategy_fallback: str = "markdown"


class IngestionBlock(BaseModel):
    """Ingestion knobs carried in :attr:`EffectiveSettings.ingestion` (D10)."""

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    embed_concurrency: int = 2
    embed_batch_size: int = 100

    # File extensions ingestion collects (design D4 of
    # fix-embedding-and-structure-fidelity-1: profile-scoped). The default
    # repeats DEFAULT_INGEST_EXTENSIONS from core/ingestion/settings.py —
    # the pure-data import-linter contract forbids importing it here, so
    # both models must stay in sync (mirroring the MetadataBlock/
    # MetadataSettings timeout convention). Values arriving here are
    # already normalised by IngestionSettings or the profile overlay.
    ingest_extensions: tuple[str, ...] = (
        ".pdf",
        ".docx",
        ".pptx",
        ".txt",
        ".md",
        ".html",
        ".csv",
    )


class EmbeddingSettings(BaseModel):
    """Config-facing embedding norm-guard knobs (env prefix ``EMBEDDING__``).

    The Settings twin of :class:`EmbeddingBlock`. Lives here — next to its
    Block, in the pure-data settings module — rather than under
    ``core/providers/embeddings/``: the providers package is quarantined
    behind import-linter contracts that forbid transitive imports from
    retrieval, vectordb, and daemon, and ``config`` composing a providers
    submodule would leak that package across every module that imports
    config.
    """

    model_config = ConfigDict(extra="forbid")

    # Fail-closed at ingest, warn-and-continue at query. Disabling is an
    # explicit, startup-logged operator escape hatch — never a silent
    # default.
    norm_guard_enabled: bool = True
    # Observed float32 rounding band for the production model is ~1e-7;
    # three orders of headroom catch real drift without false alarms.
    norm_tolerance: float = Field(default=0.001, gt=0)


class EmbeddingBlock(BaseModel):
    """Embedding norm-guard knobs in :attr:`EffectiveSettings.embedding`.

    The dense path ranks by L2 distance and converts to cosine-like
    similarity at the store boundary — rank-equivalent to cosine only for
    unit-normalised vectors. These knobs enforce that contract at both
    embedding boundaries (guard-embedding-normalisation, design D3).
    """

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    # Fail-closed at ingest, warn-and-continue at query. Disabling is an
    # explicit, startup-logged operator escape hatch — never a silent
    # default (compose logs the disabled state).
    norm_guard_enabled: bool = True
    # Observed float32 rounding band for the production model is ~1e-7;
    # three orders of headroom catch real drift without false alarms.
    norm_tolerance: float = Field(default=0.001, gt=0)


class RetrievalBlock(BaseModel):
    """Retrieval knobs carried in :attr:`EffectiveSettings.retrieval`."""

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    top_k: int = 10
    similarity_threshold: float = 0.0
    rerank_enabled: bool = False
    rerank_enabled_for_semantic: bool = True
    hard_technical_threshold: float = 0.3
    rerank_fetch_multiplier: int = 3
    rerank_max_fetch: int = 100
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_backend: str = "onnx"
    hybrid_enabled: bool = False
    hybrid_rrf_k: int = 60
    hybrid_sparse_backend: str = "bm25"


class MetadataBlock(BaseModel):
    """Metadata knobs carried in :attr:`EffectiveSettings.metadata`."""

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    extraction_mode: str = "llamaindex"
    keyword_rules: str | None = None
    ollama_classify_model: str = "qwen3:0.6b"
    # Both knobs reject non-positive values outright rather than clamping:
    # silently rewriting an operator's 0 to 1 hides the misconfiguration,
    # and a non-positive timeout reaches httpx as a nonsensical deadline.
    classify_max_attempts: int = Field(default=3, gt=0)
    classify_timeout: float = Field(default=30.0, gt=0)
    # Separate budget for the llamaindex pipeline: three extractors per chunk,
    # one attempt, no retry.  See MetadataSettings for why it is not merged
    # with classify_timeout.
    pipeline_timeout: float = Field(default=180.0, gt=0)
    # Per-provider overrides for the two shared timeouts above.  ``None``
    # means "unset, use the shared value" — mirrors ``MetadataSettings``
    # (core/metadata/settings.py); both models must stay in sync.
    llamacpp_classify_timeout_override: float | None = Field(default=None, gt=0)
    ollama_classify_timeout_override: float | None = Field(default=None, gt=0)
    openrouter_classify_timeout_override: float | None = Field(default=None, gt=0)
    llamacpp_pipeline_timeout_override: float | None = Field(default=None, gt=0)
    ollama_pipeline_timeout_override: float | None = Field(default=None, gt=0)
    openrouter_pipeline_timeout_override: float | None = Field(default=None, gt=0)
    taxonomy_mode: str = "category"


class AnswerBlock(BaseModel):
    """Answering knobs carried in :attr:`EffectiveSettings.answer`.

    Mirrors :class:`rag_mcp.core.answer.settings.AnswerSettings` (the
    config-side model); both must stay in sync — the MetadataBlock/
    MetadataSettings pair established the convention.  Answering is
    server-level configuration, with one carve-out: the three
    ``verify_*`` fields ARE profile-overlaid per collection (the
    ``documents`` use case may opt into the cloud judge while
    ``codebase`` stays speed-first); every other answer field stays
    server-level.
    """

    # Frozen like the parent: EffectiveSettings.model_copy shares block
    # instances by reference between overlays, so a mutable block would
    # let one operation silently rewrite another's configuration.
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3:4b"
    timeout: float = Field(default=120.0, gt=0)
    max_rounds: int = Field(default=4, ge=1, le=8)
    context_window: int = Field(default=8192, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    prefer_client_sampling: bool = True
    allow_legacy_sampling: bool = True
    # Claim verification (ADR-059): opt-in cloud judge.  The three
    # verify fields are the profile-overlaid carve-out; see the class
    # docstring.  Keep in sync with AnswerSettings.
    verify_claims: bool = False
    verify_model: str = ""
    verify_provider: str = "cloud"


class EffectiveSettings(BaseModel):
    """Frozen settings value object threaded through all ``core/`` operations.

    Carries every configuration value the ``core/`` and ``integrations/``
    layers need: the chunking, ingestion, retrieval, and metadata blocks
    plus cross-cutting fields (storage identifiers, embedding model, PDF
    reader, document backend, magika binary, thresholds).

    Producers:
        - :class:`ProfileResolver.resolve(collection)` for collection-bound
          operations.
        - ``compose.py`` for operations with no collection (codebase map).

    The model is frozen — mutation raises ``ValidationError``.
    """

    model_config = ConfigDict(frozen=True)

    # ── Nested subpackage blocks ──────────────────────────────────
    chunking: ChunkingBlock = ChunkingBlock()
    ingestion: IngestionBlock = IngestionBlock()
    embedding: EmbeddingBlock = EmbeddingBlock()
    retrieval: RetrievalBlock = RetrievalBlock()
    metadata: MetadataBlock = MetadataBlock()
    answer: AnswerBlock = AnswerBlock()

    # ── Profile identity ──────────────────────────────────────────
    profile_name: str = "documents"

    # ── Storage ───────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    collection_name: str = "documents"
    chroma_scan_page_size: int = 10000
    # Canonical default (make-lancedb-default-and-isolate-chromadb, task
    # 2.1): LanceDB is the qualified base-install backend (ADR-049).
    vector_store: str = "lancedb"
    lancedb_uri: str = "./lancedb"

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
    liteparse_ocr_enabled: bool = False

    # ── Codebase map ──────────────────────────────────────────────
    magika_binary: str = "magika"
    doc_similarity_threshold: float = 0.85
    codebase_map_cache_dir: str = ".opencode"
    codebase_map_max_files: int = 5000
    codebase_map_max_depth: int = 10
    # Community detection (shared by codebase and document graphs).
    # Louvain stays the base-install default; "leiden" requires the
    # optional community-leiden extra and fails startup when missing
    # (no silent fallback — an explicit algorithm is an operator contract).
    community_algorithm: str = "louvain"
    community_seed: int = 0

    # ── Document backend ──────────────────────────────────────────
    document_backend: str = "local"
    azure_doc_intelligence_endpoint: str = ""
    azure_doc_intelligence_key: str = ""
    azure_doc_intelligence_model: str = "prebuilt-layout"

    # ── Server-wide default profile ───────────────────────────────
    rag_profile: str = "documents"

    # ── Backward-compatible flat property aliases ─────────────────
    # These preserve the pre-group-5 access pattern (effective_settings.top_k)
    # so the tree stays runnable while group 5 threads the nested blocks.
    # They will be removed after group 11 completes the test migration.

    @property
    def top_k(self) -> int:
        """Alias for ``retrieval.top_k`` (backward compat)."""
        return self.retrieval.top_k

    @property
    def reranker_enabled(self) -> bool:
        """Alias for ``retrieval.rerank_enabled`` (backward compat)."""
        return self.retrieval.rerank_enabled

    @property
    def hybrid_enabled(self) -> bool:
        """Alias for ``retrieval.hybrid_enabled`` (backward compat)."""
        return self.retrieval.hybrid_enabled

    @property
    def chunk_strategy_fallback(self) -> str:
        """Alias for ``chunking.strategy_fallback`` (backward compat)."""
        return self.chunking.strategy_fallback

    @property
    def metadata_taxonomy_mode(self) -> str:
        """Alias for ``metadata.taxonomy_mode`` (backward compat)."""
        return self.metadata.taxonomy_mode


# ── Composition-root-provided default ───────────────────────────────────
#
# Entry points (``search``, ``ingest_path_async``) resolve their settings
# ONCE at the boundary: an explicitly passed instance always wins, otherwise
# the default the composition root installed at startup is used.  Everything
# below the entry point receives the resolved instance as a required
# parameter and performs no lookup of its own.
#
# This mirrors ``core.vectordb.get_default_store`` — the DI pattern already
# established in this codebase — and satisfies the settings-dependency-
# injection contract: no ``core/`` or ``integrations/`` module imports the
# resolved ``Settings`` singleton, and two operations in one process each
# honour the instance they were given.

_default_effective: EffectiveSettings | None = None


def set_default_effective_settings(settings: EffectiveSettings) -> None:
    """Install the process-wide default (called only by the composition root)."""
    global _default_effective
    _default_effective = settings


def reset_default_effective_settings() -> None:
    """Clear the installed default (used by tests)."""
    global _default_effective
    _default_effective = None


def get_default_effective_settings() -> EffectiveSettings:
    """Return the composition-root default.

    Raises:
        RuntimeError: If the composition root has not installed one. Falling
            back to class defaults here would silently discard the operator's
            configuration — the H-7 failure mode — so this fails loudly.
    """
    if _default_effective is None:
        raise RuntimeError(
            "No default EffectiveSettings installed. The composition root "
            "(rag_mcp.compose) installs one at startup; import it before "
            "calling core operations, or pass effective_settings explicitly."
        )
    return _default_effective


def resolve_effective_settings(
    settings: EffectiveSettings | None,
) -> EffectiveSettings:
    """Return *settings* if given, else the composition-root default."""
    return settings if settings is not None else get_default_effective_settings()
