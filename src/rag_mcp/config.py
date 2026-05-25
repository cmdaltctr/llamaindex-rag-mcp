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
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "2"))

# ── Retrieval defaults ──────────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "5"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.0"))

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

# Note: LLAMANDEX_EXTRACTOR_MAX_CHUNKS is read at call-time in
# metadata_extractor.py via os.getenv() so tests can override it
# with monkeypatch.setenv after module load.  Default: 10.

# ── File extensions we know how to handle ───────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
