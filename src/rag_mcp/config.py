"""Shared configuration for the RAG MCP server.

Loads environment variables once and configures the LlamaIndex global
``Settings.embed_model``.  Both ``ingestion.py`` and ``retrieval.py``
import from here so that embedding setup is guaranteed to run exactly
once, eliminating the previous duplication where each module
independently set ``Settings.embed_model`` at import time.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding

load_dotenv()

logger = logging.getLogger(__name__)


def _get_float_env(name: str, default: float) -> float:
    """Parse a float env var, failing fast with a clear error on bad input.

    A typo like ``HARD_TECHNICAL_THRESHOLD=O.3`` (letter O instead of zero)
    would otherwise produce a bare ``ValueError`` traceback. This wraps it
    with the variable name and the offending value so the operator knows
    exactly what to fix.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got: {raw!r}") from None

# ── Embedding model (local via Ollama) ──────────────────────────────────
# The model name MUST come from a .env file or ENV var — there is no
# hardcoded fallback.  Create or edit .env in the project root:
#
#   EMBED_MODEL=qwen3-embedding:8b
#
# See .env.example for more options.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL")
if not EMBED_MODEL_NAME:
    raise ValueError(
        "EMBED_MODEL environment variable is required. "
        "Set it in a .env file:\n\n"
        "    EMBED_MODEL=qwen3-embedding:8b\n\n"
        "See .env.example for alternatives."
    )

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "100"))

Settings.embed_model = OllamaEmbedding(
    model_name=EMBED_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
    embed_batch_size=EMBED_BATCH_SIZE,
)

# ── Shared paths and collection ─────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documents")
CHROMA_SCAN_PAGE_SIZE = int(os.getenv("CHROMA_SCAN_PAGE_SIZE", "10000"))

# ── Ingestion defaults ──────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
# Default overlap raised from 64 → 100 in the rag-retrieval-quality-improvements
# change (Stäbler et al. 2025 empirical sweet spot).  Existing collections
# are unaffected until they are re-ingested.
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "2"))

# ── Markdown chunking knobs ──────────────────────────────────────────────
# Experiment 6c promoted a Markdown-only chunk-size default of 1024. The
# global CHUNK_SIZE remains 512 for non-Markdown files; existing collections
# only pick up this value after re-ingestion.
MARKDOWN_CHUNK_SIZE = int(os.getenv("MARKDOWN_CHUNK_SIZE", "1024"))
# Heading prepend and min-size floor remain experimental and opt-in.
MARKDOWN_HEADING_PREPEND = os.getenv("MARKDOWN_HEADING_PREPEND", "false").lower() == "true"
MARKDOWN_MIN_CHUNK_FRACTION = _get_float_env("MARKDOWN_MIN_CHUNK_FRACTION", 0.0)

# ── Retrieval defaults ──────────────────────────────────────────────────
# Balanced evidence-retrieval profile promoted after Experiments 7a and 8a:
# keep CHUNK_OVERLAP=100 and top_k=10.  Reranker is disabled by default
# after Experiment 10 demonstrated the cross-encoder model
# (ms-marco-MiniLM-L-6-v2) is fundamentally mismatched for
# identifier-heavy technical documentation, degrading Coverage@20 by
# 19–27% at 19× latency cost.  Reranker remains available as an opt-in.
# Omitted rerank requests are resolved centrally in retrieval.py: first by
# RERANK_ENABLED, then by the semantic/technical policy below.
TOP_K = int(os.getenv("TOP_K", "10"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"

# Policy knob: when RERANK_ENABLED=False but the query/workload is below the
# configured technical threshold, retrieval.py may conditionally activate the
# reranker for semantic workloads.
RERANK_ENABLED_FOR_SEMANTIC = os.getenv("RERANK_ENABLED_FOR_SEMANTIC", "true").lower() == "true"

# Policy knob: fraction of identifier-heavy queries above which the reranker
# is automatically disabled (even when RERANK_ENABLED_FOR_SEMANTIC=True).
# Experiment 10 showed the cross-encoder is actively harmful at any
# pool size when ≥30% of queries are identifier-heavy.
HARD_TECHNICAL_THRESHOLD = _get_float_env("HARD_TECHNICAL_THRESHOLD", 0.3)
SIMILARITY_THRESHOLD = _get_float_env("SIMILARITY_THRESHOLD", 0.0)

# ── Reranker fetch-pool sizing ─────────────────────────────────────────
# When reranking is enabled, ``search()`` fetches a larger candidate pool
# from vector search and lets the cross-encoder re-score them before
# returning the final ``top_k``.  This implements the "Wide Net, Tight
# Filter" pattern from the rag-retrieval-quality-improvements change.
#
# Effective fetch size = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)
# clamped to the collection size so small collections do not over-fetch.
RERANK_FETCH_MULTIPLIER = int(os.getenv("RERANK_FETCH_MULTIPLIER", "10"))
RERANK_MAX_FETCH = int(os.getenv("RERANK_MAX_FETCH", "50"))

# ── Hybrid retrieval defaults ─────────────────────────────────────────────
# V1 deliberately defaults to the in-process BM25 path.  Promotion of
# HYBRID_SPARSE_BACKEND to "auto" is a follow-up change after Experiment 9
# validates native Chroma sparse support for this project's runtime mode.
HYBRID_ENABLED = os.getenv("HYBRID_ENABLED", "false").lower() == "true"
HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))
HYBRID_SPARSE_BACKEND = os.getenv("HYBRID_SPARSE_BACKEND", "bm25").lower()

if HYBRID_SPARSE_BACKEND not in {"auto", "native", "bm25"}:
    logger.warning(
        "Unknown HYBRID_SPARSE_BACKEND=%r; falling back to bm25",
        HYBRID_SPARSE_BACKEND,
    )
    HYBRID_SPARSE_BACKEND = "bm25"


def _resolve_sparse_backend() -> str:
    """Resolve the configured sparse backend to ``bm25`` or ``native``."""
    if HYBRID_SPARSE_BACKEND == "bm25":
        return "bm25"

    from .sparse_retriever import _detect_native_sparse_capability

    native_available = _detect_native_sparse_capability()
    if HYBRID_SPARSE_BACKEND == "auto":
        return "native" if native_available else "bm25"

    if native_available:
        return "native"

    logger.warning(
        "HYBRID_SPARSE_BACKEND=native was requested, but the installed "
        "ChromaDB runtime does not expose native sparse retrieval for this "
        "project configuration. Falling back to bm25."
    )
    return "bm25"


RESOLVED_HYBRID_SPARSE_BACKEND = _resolve_sparse_backend()

# ── Metadata extraction ─────────────────────────────────────────────────
# Controls how document metadata (e.g., category) is extracted during
# ingestion.  Allowed values: "disabled", "keyword", "ollama", "llamaindex".
METADATA_EXTRACTION_MODE = os.getenv("METADATA_EXTRACTION_MODE", "keyword")

# Optional JSON string of [{"pattern": "regex", "category": "name"}, ...]
# overriding the built-in default keyword rules.  Falls back to defaults
# on parse error (WARNING logged).
METADATA_KEYWORD_RULES = os.getenv("METADATA_KEYWORD_RULES", None)

# Chat model used for Ollama-based classification (only when
# METADATA_EXTRACTION_MODE is "ollama" or "llamaindex").
OLLAMA_CLASSIFY_MODEL = os.getenv("OLLAMA_CLASSIFY_MODEL", "qwen3:0.6b")

# Bounded retry / per-attempt timeout for Ollama metadata extraction.
# Reads at import time; tests override via ``monkeypatch.setenv`` and
# ``monkeypatch.setattr`` on the ``rag_mcp.metadata_extractor`` module
# (which copies these constants at its own import time).
OLLAMA_CLASSIFY_MAX_ATTEMPTS = int(os.getenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "3"))
OLLAMA_CLASSIFY_TIMEOUT = _get_float_env("OLLAMA_CLASSIFY_TIMEOUT", 30.0)

# Note: LLAMANDEX_EXTRACTOR_MAX_CHUNKS is read at call-time in
# metadata_extractor.py via os.getenv() so tests can override it
# with monkeypatch.setenv after module load.  Default: 10.

# ── File extensions we know how to handle ───────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
