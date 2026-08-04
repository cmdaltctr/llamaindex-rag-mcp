"""Backward-compatible re-export shim for the metadata extraction subpackage.

.. deprecated::
    Import from ``rag_mcp.core.metadata`` instead.  This shim will be
    removed in v2.0.0 after all five refactor phases land.

The original monolithic ``metadata_extractor.py`` (1164 lines) was split
into ``rag_mcp.core.metadata`` submodules as part of Phase 1.  This file
re-exports every public and private name so existing imports continue to
resolve.  Tests that monkeypatch module-level variables
(``METADATA_EXTRACTION_MODE``, ``METADATA_KEYWORD_RULES``,
``_chroma_client``, ``_retry_sleep``) must patch the corresponding
submodule after the split — see ``notes/cross-imports.md``.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.metadata_extractor is deprecated; "
    "import from rag_mcp.core.metadata instead. "
    "Removal in v2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

# ── Config variables (re-exported for backward compatibility) ───────────
from .config import (  # noqa: F401
    CHROMA_PERSIST_DIR,
    LLAMACPP_CHAT_MODEL,
    LLAMACPP_CHAT_URL,
    METADATA_EXTRACTION_MODE,
    METADATA_KEYWORD_RULES,
    CLOUD_BACKEND,
    LOCAL_BACKEND,
    METADATA_LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_CLASSIFY_MAX_ATTEMPTS,
    OLLAMA_CLASSIFY_MODEL,
    OLLAMA_CLASSIFY_TIMEOUT,
    OPENROUTER_API_KEY,
    OPENROUTER_LLM_MODEL,
)

# ── Shared helpers ──────────────────────────────────────────────────────
from .core.metadata._common import (  # noqa: F401
    _MAX_CATEGORY_WORDS,
    _MAX_KEYWORDS,
    _MAX_SUMMARY_CHARS,
    _normalise_category,
    _strip_llm_prefix,
    _truncate_keywords,
    _truncate_summary,
)

# ── Keyword backend ─────────────────────────────────────────────────────
from .core.metadata.keyword import (  # noqa: F401
    _DEFAULT_KEYWORD_RULES,
    _extract_keyword,
    _extract_keyword_async,
    _load_keyword_rules,
)

# ── Taxonomy (ADR-013) ──────────────────────────────────────────────────
from .core.metadata.taxonomy import (  # noqa: F401
    _collect_categories_from_collection,
    _gather_existing_categories,
    _get_seed_categories,
)

# ── Ollama backend ──────────────────────────────────────────────────────
from .core.metadata.ollama import (  # noqa: F401
    _build_ollama_prompt,
    _extract_ollama_async,
    _get_ollama_max_attempts,
    _get_ollama_timeout,
    _parse_ollama_json_response,
    _retry_sleep,
    _strip_markdown_fence,
)

# ── llama.cpp backend ───────────────────────────────────────────────────
from .core.metadata.llamacpp import _extract_llamacpp_chat_async  # noqa: F401

# ── LlamaIndex backend ──────────────────────────────────────────────────
from .core.metadata.llamaindex import (  # noqa: F401
    _aggregate_llamaindex_metadata,
    _derive_category,
    _extract_llamaindex_async,
    _first_nonempty_str_field,
    _get_max_chunks,
    _parse_keywords_from_meta,
)

# ── Orchestrator ────────────────────────────────────────────────────────
from .core.metadata.extractor import (  # noqa: F401
    _dispatch_local_extraction,
    _extract_disabled,
    _extract_openrouter_chat_async,
    extract_metadata_async,
)
