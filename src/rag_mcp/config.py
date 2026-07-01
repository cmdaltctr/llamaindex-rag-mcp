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

# ── Provider registries ────────────────────────────────────────────────
# Config-based provider selection.  Adding a new provider = one dict entry.
# No if/elif changes needed in consuming modules.

from typing import Any, TypedDict


class _ProviderConfig(TypedDict):
    """Registry entry for an embedding or LLM provider."""
    module: str
    cls: str
    required_env: dict[str, str]
    optional_env: dict[str, str]
    default_env: dict[str, str]
    static_params: dict[str, Any]
    extra_dep: str


EMBED_PROVIDERS: dict[str, _ProviderConfig] = {
    "ollama": {
        "module": "llama_index.embeddings.ollama",
        "cls": "OllamaEmbedding",
        "required_env": {"EMBED_MODEL": "model_name", "OLLAMA_BASE_URL": "base_url"},
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "default_env": {},
        "static_params": {},
        "extra_dep": "llama-index-embeddings-ollama",
    },
    "llamacpp": {
        "module": "llama_index.embeddings.openai",
        "cls": "OpenAIEmbedding",
        "required_env": {"LLAMACPP_EMBED_MODEL": "model"},
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "default_env": {"LLAMACPP_EMBED_URL": "api_base"},
        "static_params": {"api_key": "no-key"},
        "extra_dep": "llama-index-embeddings-openai",
    },
    "openrouter": {
        "module": "llama_index.embeddings.openai",
        "cls": "OpenAIEmbedding",
        "required_env": {
            "OPENROUTER_EMBED_MODEL": "model",
            "OPENROUTER_API_KEY": "api_key",
        },
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "default_env": {},
        "static_params": {"api_base": "https://openrouter.ai/api/v1"},
        "extra_dep": "llama-index-embeddings-openai",
    },
}

LLM_PROVIDERS: dict[str, _ProviderConfig] = {
    "ollama": {
        "module": "llama_index.llms.ollama",
        "cls": "Ollama",
        "required_env": {"OLLAMA_CLASSIFY_MODEL": "model", "OLLAMA_BASE_URL": "base_url"},
        "optional_env": {},
        "default_env": {},
        "static_params": {"request_timeout": 180.0},
        "extra_dep": "llama-index-llms-ollama",
    },
    "llamacpp": {
        "module": "llama_index.llms.openai_like",
        "cls": "OpenAILike",
        "required_env": {"LLAMACPP_CHAT_MODEL": "model"},
        "optional_env": {},
        "default_env": {"LLAMACPP_CHAT_URL": "api_base"},
        "static_params": {"api_key": "no-key", "request_timeout": 180.0},
        "extra_dep": "llama-index-llms-openai-like",
    },
    "openrouter": {
        "module": "llama_index.llms.openai_like",
        "cls": "OpenAILike",
        "required_env": {
            "OPENROUTER_LLM_MODEL": "model",
            "OPENROUTER_API_KEY": "api_key",
        },
        "optional_env": {},
        "default_env": {},
        "static_params": {
            "api_base": "https://openrouter.ai/api/v1",
            "request_timeout": 180.0,
        },
        "extra_dep": "llama-index-llms-openai-like",
    },
}


def _build_provider(registry: dict[str, _ProviderConfig], provider_name: str) -> Any:
    """Resolve a provider from the registry, dynamic-import, and instantiate.

    Args:
        registry: The provider registry dict (EMBED_PROVIDERS or LLM_PROVIDERS).
        provider_name: Provider key to look up.

    Returns:
        Instantiated provider object.

    Raises:
        ValueError: If a required env var is missing.
        ImportError: If the optional dependency is not installed.
    """
    import importlib

    entry = registry.get(provider_name)
    if entry is None:
        raise ValueError(f"Unknown provider: {provider_name!r}")

    # Resolve required env vars → constructor params.
    params: dict[str, Any] = dict(entry["static_params"])
    for env_name, param_name in entry["required_env"].items():
        value = os.getenv(env_name)
        if not value:
            raise ValueError(
                f"{env_name} environment variable is required for "
                f"provider {provider_name!r}."
            )
        params[param_name] = value

    # Resolve optional env vars → constructor params.
    for env_name, param_name in entry["optional_env"].items():
        value = os.getenv(env_name)
        if value is not None:
            params[param_name] = int(value) if env_name == "EMBED_BATCH_SIZE" else value

    # Resolve env vars with defaults → constructor params.
    for env_name, param_name in entry.get("default_env", {}).items():
        value = os.getenv(env_name)
        if value:
            params[param_name] = value
        else:
            # Fall back to module-level constant if available.
            params[param_name] = globals().get(env_name, "")

    # Dynamic import + instantiate.
    try:
        mod = importlib.import_module(entry["module"])
    except ImportError as exc:
        raise ImportError(
            f"Provider {provider_name!r} requires {entry['extra_dep']}. "
            f"Install it with:  uv sync --extra {provider_name}"
        ) from exc

    cls = getattr(mod, entry["cls"])
    return cls(**params)


# ── Embedding provider selection ────────────────────────────────────────
# Replaces the old INFERENCE_BACKEND single-knob.  EMBED_PROVIDER controls
# embeddings only; METADATA_LLM_PROVIDER controls metadata extraction LLM.
_legacy_backend = os.getenv("INFERENCE_BACKEND")
_embed_provider_env = os.getenv("EMBED_PROVIDER")

if _embed_provider_env:
    EMBED_PROVIDER = _embed_provider_env.lower()
    if _legacy_backend:
        logger.warning(
            "Both EMBED_PROVIDER and INFERENCE_BACKEND are set — "
            "EMBED_PROVIDER takes precedence. Remove INFERENCE_BACKEND "
            "from your .env to silence this warning."
        )
elif _legacy_backend:
    EMBED_PROVIDER = _legacy_backend.lower()
    logger.warning(
        "INFERENCE_BACKEND is deprecated — use EMBED_PROVIDER instead. "
        "Update your .env:  INFERENCE_BACKEND → EMBED_PROVIDER"
    )
else:
    EMBED_PROVIDER = "ollama"

if EMBED_PROVIDER not in EMBED_PROVIDERS:
    logger.warning(
        "Unknown EMBED_PROVIDER=%r; falling back to ollama",
        EMBED_PROVIDER,
    )
    EMBED_PROVIDER = "ollama"

# ── Metadata LLM provider selection ─────────────────────────────────────
# Defaults to "ollama" (safe, local, free) — does NOT inherit EMBED_PROVIDER.
# This prevents surprising cloud API costs when a user sets
# EMBED_PROVIDER=openrouter without explicitly opting into cloud LLM.
METADATA_LLM_PROVIDER = os.getenv("METADATA_LLM_PROVIDER", "ollama").lower()

if METADATA_LLM_PROVIDER not in LLM_PROVIDERS:
    logger.warning(
        "Unknown METADATA_LLM_PROVIDER=%r; falling back to ollama",
        METADATA_LLM_PROVIDER,
    )
    METADATA_LLM_PROVIDER = "ollama"

# ── llamacpp backend URLs and models ────────────────────────────────────
LLAMACPP_EMBED_URL = os.getenv("LLAMACPP_EMBED_URL", "http://localhost:8080/v1")
LLAMACPP_EMBED_MODEL = os.getenv("LLAMACPP_EMBED_MODEL", "")
LLAMACPP_CHAT_URL = os.getenv("LLAMACPP_CHAT_URL", "http://localhost:8081/v1")
LLAMACPP_CHAT_MODEL = os.getenv("LLAMACPP_CHAT_MODEL", "")

# ── OpenRouter env vars ─────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_EMBED_MODEL = os.getenv("OPENROUTER_EMBED_MODEL", "")
OPENROUTER_LLM_MODEL = os.getenv("OPENROUTER_LLM_MODEL", "")

# ── Embedding model ─────────────────────────────────────────────────────
# EMBED_MODEL is required only for the ollama provider.  llamacpp and
# openrouter have their own model env vars (LLAMACPP_EMBED_MODEL,
# OPENROUTER_EMBED_MODEL).
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL")
if EMBED_PROVIDER == "ollama" and not EMBED_MODEL_NAME:
    raise ValueError(
        "EMBED_MODEL environment variable is required when "
        "EMBED_PROVIDER=ollama. Set it in a .env file:\n\n"
        "    EMBED_MODEL=qwen3-embedding:8b\n\n"
        "See .env.example for alternatives."
    )

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "100"))

# Build the embedding model from the registry.
Settings.embed_model = _build_provider(EMBED_PROVIDERS, EMBED_PROVIDER)

# ── Backward compatibility alias ────────────────────────────────────────
# Existing code and tests that import INFERENCE_BACKEND will get the
# EMBED_PROVIDER value.  This is a read-only alias — setting it has no
# effect on provider selection.
INFERENCE_BACKEND = EMBED_PROVIDER

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
RERANK_FETCH_MULTIPLIER = int(os.getenv("RERANK_FETCH_MULTIPLIER", "3"))
RERANK_MAX_FETCH = int(os.getenv("RERANK_MAX_FETCH", "100"))

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

# ── PDF reader selection ───────────────────────────────────────────────
# Controls which parser handles .pdf files during ingestion. Accepted
# values: "auto", "liteparse", "pypdfium2", "pypdf". Default is "auto",
# which resolves to LiteParse when installed, falling back to pypdf.
# See ADR-020.
PDF_READER = os.getenv("PDF_READER", "auto").lower()

if PDF_READER not in {"auto", "liteparse", "pypdfium2", "pypdf"}:
    logger.warning(
        "Unknown PDF_READER=%r; falling back to auto", PDF_READER,
    )
    PDF_READER = "auto"

# LiteParse constructor knobs. OCR is disabled by default — the corpus
# has no scanned PDFs, and OCR adds ~16s/file overhead (see Experiment 11).
LITEPARSE_NUM_WORKERS: int | None = (
    int(v) if (v := os.getenv("LITEPARSE_NUM_WORKERS")) else None
)
LITEPARSE_OCR_ENABLED = os.getenv("LITEPARSE_OCR_ENABLED", "false").lower() == "true"


def _resolve_pdf_reader() -> str:
    """Resolve the configured PDF reader to a concrete backend name.

    Mirrors the ``_resolve_sparse_backend()`` pattern. Probes imports in
    preference order: ``liteparse → pypdfium2 → pypdf``.
    """
    if PDF_READER == "pypdf":
        return "pypdf"

    # Explicit backend requests: verify the package is importable.
    if PDF_READER in ("liteparse", "pypdfium2"):
        try:
            __import__(PDF_READER)
            return PDF_READER
        except ImportError:
            logger.error(
                "PDF_READER=%s was requested but the package is not "
                "installed. Falling back to pypdf.", PDF_READER,
            )
            return "pypdf"

    # auto resolution: probe in preference order.
    for backend in ("liteparse", "pypdfium2"):
        try:
            __import__(backend)
            logger.info(
                "PDF_READER=auto resolved to %s", backend,
            )
            return backend
        except ImportError:
            continue

    return "pypdf"


RESOLVED_PDF_READER = _resolve_pdf_reader()

# ── Metadata extraction ─────────────────────────────────────────────────
# Controls how document metadata (e.g., category) is extracted during
# ingestion.  Allowed values: "disabled", "keyword", "local", "llamaindex".
# "ollama" is silently mapped to "local" for backward compatibility.
METADATA_EXTRACTION_MODE = os.getenv("METADATA_EXTRACTION_MODE", "llamaindex")

# Optional JSON string of [{"pattern": "regex", "category": "name"}, ...]
# overriding the built-in default keyword rules.  Falls back to defaults
# on parse error (WARNING logged).
METADATA_KEYWORD_RULES = os.getenv("METADATA_KEYWORD_RULES", None)

# Chat model used for Ollama-based classification (only when
# METADATA_EXTRACTION_MODE is "local" or "llamaindex").
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

# ── Codebase map: Magika file-type detection ────────────────────────────
# Path to the Magika CLI binary. If not on $PATH, the system falls back to
# suffix-based detection. Install via `brew install magika`.
MAGIKA_BINARY = os.getenv("MAGIKA_BINARY", "magika")

# ── Codebase map: document similarity threshold ─────────────────────────
# Cosine similarity threshold for document graph edges. Chunks with
# similarity above this value get an edge in the document graph.
# Default 0.85 — needs experiment calibration with qwen3-embedding:0.6b.
DOC_SIMILARITY_THRESHOLD = _get_float_env("DOC_SIMILARITY_THRESHOLD", 0.85)

# ── Codebase map: cache directory ───────────────────────────────────────
# Per-project cache for codebase map, keyed by git commit hash.
# Defaults to .opencode/ which is gitignored by convention.
CODEBASE_MAP_CACHE_DIR = os.getenv("CODEBASE_MAP_CACHE_DIR", ".opencode")

# ── Codebase map: file count and depth limits ───────────────────────────
# Maximum number of files to scan before truncating (prevents hangs on
# monorepos). When exceeded, scanning stops and a warning is logged.
CODEBASE_MAP_MAX_FILES = int(os.getenv("CODEBASE_MAP_MAX_FILES", "5000"))
# Maximum directory depth for recursive scanning.
CODEBASE_MAP_MAX_DEPTH = int(os.getenv("CODEBASE_MAP_MAX_DEPTH", "10"))

# ── Document backend selection ──────────────────────────────────────────
# Controls which parser handles document files (PDF, DOCX) during
# ingestion. Accepted values: "local" (default), "azure".
# "local" uses the existing LiteParse → pypdfium2 → pypdf chain.
# "azure" uses Azure Document Intelligence with automatic fallback to local.
DOCUMENT_BACKEND = os.getenv("DOCUMENT_BACKEND", "local").lower()

if DOCUMENT_BACKEND not in {"local", "azure"}:
    logger.warning(
        "Unknown DOCUMENT_BACKEND=%r; falling back to local",
        DOCUMENT_BACKEND,
    )
    DOCUMENT_BACKEND = "local"

# Azure Document Intelligence credentials (only used when DOCUMENT_BACKEND=azure).
# These are validated at config load time — if missing, fallback to "local".
AZURE_DOC_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
AZURE_DOC_INTELLIGENCE_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_KEY", "")
AZURE_DOC_INTELLIGENCE_MODEL = os.getenv(
    "AZURE_DOC_INTELLIGENCE_MODEL", "prebuilt-layout"
)

# Validate Azure credentials at config load time.
if DOCUMENT_BACKEND == "azure":
    if not AZURE_DOC_INTELLIGENCE_ENDPOINT or not AZURE_DOC_INTELLIGENCE_KEY:
        logger.warning(
            "DOCUMENT_BACKEND=azure but AZURE_DOC_INTELLIGENCE_ENDPOINT or "
            "AZURE_DOC_INTELLIGENCE_KEY is not set. Falling back to local mode."
        )
        DOCUMENT_BACKEND = "local"

# ── Magika label → tree-sitter language mapping ─────────────────────────
# Maps Magika content-type labels to tree-sitter language identifiers
# for CodeSplitter. Keys are Magika labels (e.g., "typescript", "python").
# Labels not in this map fall back to SentenceSplitter.
MAGIKA_LABEL_TO_TREESITTER: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "jsx",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "c_sharp",
    "go": "go",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "bash": "bash",
    "shell": "bash",
    "yaml": "yaml",
    "toml": "toml",
    "json": "json",
}

# ── File extensions we know how to handle ───────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
