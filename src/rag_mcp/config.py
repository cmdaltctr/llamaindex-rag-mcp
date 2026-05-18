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
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "nomic-embed-text")

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "100"))

Settings.embed_model = OllamaEmbedding(
    model_name=EMBED_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
    embed_batch_size=EMBED_BATCH_SIZE,
)

# ── Shared paths and collection ─────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documents")

# ── Ingestion defaults ──────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "4"))
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "2"))

# ── Retrieval defaults ──────────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "5"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.0"))

# ── File extensions we know how to handle ───────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
