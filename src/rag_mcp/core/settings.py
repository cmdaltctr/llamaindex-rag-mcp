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

from pydantic import BaseModel, ConfigDict


class ChunkingBlock(BaseModel):
    """Chunking knobs carried in :attr:`EffectiveSettings.chunking`."""

    chunk_size: int = 512
    chunk_overlap: int = 100
    markdown_chunk_size: int = 1024
    markdown_heading_prepend: bool = False
    markdown_min_chunk_fraction: float = 0.0
    strategy_fallback: str = "markdown"


class IngestionBlock(BaseModel):
    """Ingestion knobs carried in :attr:`EffectiveSettings.ingestion` (D10)."""

    embed_concurrency: int = 2
    embed_batch_size: int = 100


class RetrievalBlock(BaseModel):
    """Retrieval knobs carried in :attr:`EffectiveSettings.retrieval`."""

    top_k: int = 10
    similarity_threshold: float = 0.0
    rerank_enabled: bool = False
    rerank_enabled_for_semantic: bool = True
    hard_technical_threshold: float = 0.3
    rerank_fetch_multiplier: int = 3
    rerank_max_fetch: int = 100
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    hybrid_enabled: bool = False
    hybrid_rrf_k: int = 60
    hybrid_sparse_backend: str = "bm25"


class MetadataBlock(BaseModel):
    """Metadata knobs carried in :attr:`EffectiveSettings.metadata`."""

    extraction_mode: str = "llamaindex"
    keyword_rules: str | None = None
    ollama_classify_model: str = "qwen3:0.6b"
    ollama_classify_max_attempts: int = 3
    ollama_classify_timeout: float = 30.0
    taxonomy_mode: str = "category"


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
    retrieval: RetrievalBlock = RetrievalBlock()
    metadata: MetadataBlock = MetadataBlock()

    # ── Profile identity ──────────────────────────────────────────
    profile_name: str = "documents"

    # ── Storage ───────────────────────────────────────────────────
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
    liteparse_ocr_enabled: bool = False

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
