"""Detection of retired configuration variable names.

Split out of ``config/__init__.py`` (task 8.7).

See design.md D9: this is the second of two guards. ``extra="forbid"`` on
the subpackage models catches a mistyped *nested* key, but a bare ``TOP_K``
never reaches a subpackage model at all, so it needs an explicit check.

LIFETIME: permanent through the v2.x line, removed in v3.0.0.
"""

from __future__ import annotations

import os


# ── Retired env-var tripwire (design.md D9, layer 2) ─────────────────

# Retired variable names mapped to their current replacement. Two kinds
# live here: pre-v2.0.0 flat names for settings that now live in a nested
# block, and nested names retired by a later rename.
#
# `extra="forbid"` on the subpackage models catches a mistyped *nested* key,
# but a bare `TOP_K` never reaches a subpackage model at all — with
# env_nested_delimiter it is simply an unrecognised root-level key that
# `extra="ignore"` would swallow in silence. A retired *nested* name is
# swallowed the same way, by the block model that no longer declares it.
# That silent behaviour change on upgrade is exactly what this guard exists
# to eliminate, so it is caught here instead.
#
# LIFETIME: permanent through the v2.x line, removed in v3.0.0. This is a
# decided removal trigger, not a deferral to an unplanned minor.
_RETIRED_ENV_VARS: dict[str, str] = {
    "CHUNK_SIZE": "CHUNKING__CHUNK_SIZE",
    "CHUNK_OVERLAP": "CHUNKING__CHUNK_OVERLAP",
    "MARKDOWN_CHUNK_SIZE": "CHUNKING__MARKDOWN_CHUNK_SIZE",
    "MARKDOWN_HEADING_PREPEND": "CHUNKING__MARKDOWN_HEADING_PREPEND",
    "MARKDOWN_MIN_CHUNK_FRACTION": "CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION",
    "CHUNK_STRATEGY_FALLBACK": "CHUNKING__STRATEGY_FALLBACK",
    "EMBED_CONCURRENCY": "INGESTION__EMBED_CONCURRENCY",
    "EMBED_BATCH_SIZE": "INGESTION__EMBED_BATCH_SIZE",
    "TOP_K": "RETRIEVAL__TOP_K",
    "SIMILARITY_THRESHOLD": "RETRIEVAL__SIMILARITY_THRESHOLD",
    "RERANK_ENABLED": "RETRIEVAL__RERANK_ENABLED",
    "RERANK_ENABLED_FOR_SEMANTIC": "RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC",
    "HARD_TECHNICAL_THRESHOLD": "RETRIEVAL__HARD_TECHNICAL_THRESHOLD",
    "RERANK_FETCH_MULTIPLIER": "RETRIEVAL__RERANK_FETCH_MULTIPLIER",
    "RERANK_MAX_FETCH": "RETRIEVAL__RERANK_MAX_FETCH",
    "RERANK_MODEL": "RETRIEVAL__RERANK_MODEL",
    "HYBRID_ENABLED": "RETRIEVAL__HYBRID_ENABLED",
    "HYBRID_RRF_K": "RETRIEVAL__HYBRID_RRF_K",
    "HYBRID_SPARSE_BACKEND": "RETRIEVAL__HYBRID_SPARSE_BACKEND",
    "METADATA_EXTRACTION_MODE": "METADATA__EXTRACTION_MODE",
    "METADATA_KEYWORD_RULES": "METADATA__KEYWORD_RULES",
    "METADATA_TAXONOMY_MODE": "METADATA__TAXONOMY_MODE",
    "OLLAMA_CLASSIFY_MODEL": "METADATA__OLLAMA_CLASSIFY_MODEL",
    "OLLAMA_CLASSIFY_MAX_ATTEMPTS": "METADATA__CLASSIFY_MAX_ATTEMPTS",
    "OLLAMA_CLASSIFY_TIMEOUT": "METADATA__CLASSIFY_TIMEOUT",
    # Old v2 nested names (pre-rename) — same tripwire treatment so an
    # operator upgrading from v2.0 to v2.2 gets a clear rename message.
    "METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS": "METADATA__CLASSIFY_MAX_ATTEMPTS",
    "METADATA__OLLAMA_CLASSIFY_TIMEOUT": "METADATA__CLASSIFY_TIMEOUT",
}


def check_legacy_env_vars(env: dict[str, str] | None = None) -> None:
    """Raise if the environment carries retired configuration names.

    Covers both pre-v2.0.0 flat subpackage names and nested names retired
    by a later rename.

    Args:
        env: Environment mapping to scan (defaults to ``os.environ``).

    Raises:
        ValueError: Naming every offending variable and its current
            replacement, so the fix is mechanical.
    """
    source = os.environ if env is None else env
    found = [(old, new) for old, new in _RETIRED_ENV_VARS.items() if old in source]
    if not found:
        return
    lines = "\n".join(f"  {old}  ->  {new}" for old, new in sorted(found))
    raise ValueError(
        "Retired configuration variable(s) found in the environment. These "
        "names are no longer read and would have been silently ignored — "
        "either they are pre-v2.0.0 flat names (v2.0.0 moved subpackage "
        "settings into nested blocks), or nested names retired by a later "
        "rename. Rename them:\n"
        f"{lines}\n"
        "Cross-cutting names (EMBED_MODEL, RAG_PROFILE, PDF_READER, "
        "credentials) are unchanged. See docs/adr/037 for the full table."
    )

