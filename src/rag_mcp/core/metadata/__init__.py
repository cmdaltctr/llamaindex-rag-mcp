"""Metadata extraction subpackage.

Provides the public entry point ``extract_metadata_async`` and the four
extraction backends (keyword, ollama, llamaindex, llamacpp) plus the
hybrid category taxonomy (ADR-013).  Extracted from the original
``metadata_extractor.py`` monolith as part of Phase 1.

Backend modules are imported **lazily** (PEP 562 ``__getattr__``) so
that importing this package never eagerly imports a backend module —
mirrors the lazy-registry contract (PROPOSAL §4.4) and keeps the
config/compose/DI layering free of import cycles.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "extract_metadata_async",
]

# Legacy name -> owning submodule (imported on demand).
_NAMES: dict[str, str] = {
    "_MAX_CATEGORY_WORDS": "._common",
    "_MAX_KEYWORDS": "._common",
    "_MAX_SUMMARY_CHARS": "._common",
    "_normalise_category": "._common",
    "_strip_llm_prefix": "._common",
    "_truncate_keywords": "._common",
    "_truncate_summary": "._common",
    "_dispatch_local_extraction": ".extractor",
    "_extract_disabled": ".extractor",
    "_extract_openrouter_chat_async": ".extractor",
    "extract_metadata_async": ".extractor",
    "_DEFAULT_KEYWORD_RULES": ".keyword",
    "_extract_keyword": ".keyword",
    "_extract_keyword_async": ".keyword",
    "_load_keyword_rules": ".keyword",
    "_extract_llamacpp_chat_async": ".llamacpp",
    "_aggregate_llamaindex_metadata": ".llamaindex",
    "_derive_category": ".llamaindex",
    "_extract_llamaindex_async": ".llamaindex",
    "_first_nonempty_str_field": ".llamaindex",
    "_get_max_chunks": ".llamaindex",
    "_parse_keywords_from_meta": ".llamaindex",
    "_build_ollama_prompt": ".ollama",
    "_extract_ollama_async": ".ollama",
    "_get_ollama_max_attempts": ".ollama",
    "_get_ollama_timeout": ".ollama",
    "_parse_ollama_json_response": ".ollama",
    "_retry_sleep": ".ollama",
    "_strip_markdown_fence": ".ollama",
    "_collect_categories_from_collection": ".taxonomy",
    "_gather_existing_categories": ".taxonomy",
    "_get_seed_categories": ".taxonomy",
}


def __getattr__(name: str) -> Any:
    """Resolve a lazily-imported backend name (PEP 562)."""
    if name in _NAMES:
        import importlib

        module = importlib.import_module(_NAMES[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
