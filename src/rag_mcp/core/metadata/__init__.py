"""Metadata extraction subpackage.

Provides the public entry point ``extract_metadata_async`` and the four
extraction backends (keyword, ollama, llamaindex, llamacpp) plus the
hybrid category taxonomy (ADR-013).  Extracted from the original
``metadata_extractor.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

from ._common import (
    _MAX_CATEGORY_WORDS,
    _MAX_KEYWORDS,
    _MAX_SUMMARY_CHARS,
    _normalise_category,
    _strip_llm_prefix,
    _truncate_keywords,
    _truncate_summary,
)
from .extractor import (
    _dispatch_local_extraction,
    _extract_disabled,
    _extract_openrouter_chat_async,
    extract_metadata_async,
)
from .keyword import (
    _DEFAULT_KEYWORD_RULES,
    _extract_keyword,
    _extract_keyword_async,
    _load_keyword_rules,
)
from .llamacpp import _extract_llamacpp_chat_async
from .llamaindex import (
    _aggregate_llamaindex_metadata,
    _derive_category,
    _extract_llamaindex_async,
    _first_nonempty_str_field,
    _get_max_chunks,
    _parse_keywords_from_meta,
)
from .ollama import (
    _build_ollama_prompt,
    _extract_ollama_async,
    _get_ollama_max_attempts,
    _get_ollama_timeout,
    _parse_ollama_json_response,
    _retry_sleep,
    _strip_markdown_fence,
)
from .taxonomy import (
    _chroma_client,
    _collect_categories_from_collection,
    _gather_existing_categories,
    _get_chroma_client,
    _get_seed_categories,
)

__all__ = [
    "extract_metadata_async",
]
