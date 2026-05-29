"""Shared configuration for the RAG MCP server.

Loads environment variables once and configures the LlamaIndex global
``Settings.embed_model``.  Both ``ingestion.py`` and ``retrieval.py``
import from here so that embedding setup is guaranteed to run exactly
once, eliminating the previous duplication where each module
independently set ``Settings.embed_model`` at import time.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding

load_dotenv()

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
MARKDOWN_MIN_CHUNK_FRACTION = float(os.getenv("MARKDOWN_MIN_CHUNK_FRACTION", "0.0"))

# ── Retrieval defaults ──────────────────────────────────────────────────
# Balanced evidence-retrieval profile promoted after Experiments 7a and 8a:
# keep CHUNK_OVERLAP=100, enable reranking, and return top_k=10 chunks.  7a
# showed this recovers overlap=100 on Qasper-like evidence QA without the
# latency cost of top_k=20; 8a confirmed repeated-query cache performance.
TOP_K = int(os.getenv("TOP_K", "10"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.0"))

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
OLLAMA_CLASSIFY_TIMEOUT = float(os.getenv("OLLAMA_CLASSIFY_TIMEOUT", "30.0"))

# Note: LLAMANDEX_EXTRACTOR_MAX_CHUNKS is read at call-time in
# metadata_extractor.py via os.getenv() so tests can override it
# with monkeypatch.setenv after module load.  Default: 10.

# ── File extensions we know how to handle ───────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
