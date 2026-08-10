"""Detection of retired configuration variable names.

Split out of ``config/__init__.py`` (task 8.7).

See design.md D9: this is the second of two guards. ``extra="forbid"`` on
the subpackage models catches a mistyped *nested* key, but a bare ``TOP_K``
never reaches a subpackage model at all, so it needs an explicit check.

Retirement lifetime (shape-aware)
---------------------------------

A retired name's lifetime depends on whether settings validation can detect
it without this tripwire:

- **Nested** names (carrying a block prefix, e.g. ``METADATA__…``) are
  rejected by their settings block's ``extra="forbid"`` independently of
  this list. The tripwire only improves the error message. Such an entry
  is retained for one major version after the release that retired it and
  may then be deleted: the failure survives, only the message degrades.

- **Flat** names (no block prefix, e.g. ``TOP_K``) are **not detectable**
  by settings validation. Pydantic-settings never collects an env var that
  matches no field, so an unrecognised flat name is silently discarded.
  ``extra="forbid"`` on the root ``Settings`` model does not help: the
  variable never reaches the model, so there is nothing for ``forbid`` to
  reject (verified empirically). This tripwire is the *only* mechanism
  that detects them. Such an entry is retained for as long as an upgrade
  path exists from a version that read it and is **not** deleted merely
  because a major version has elapsed — deleting it would restore the
  silent misconfiguration it exists to prevent.

The lifetime is stated as this rule, not as a version number, so a release
that retires a name cannot also be the release that expires it.
"""

from __future__ import annotations

import os

# ── Retired env-var tripwire (design.md D9, layer 2) ─────────────────
#
# Two groups with different lifetimes — see the module docstring for the
# full rule.  ``extra="forbid"`` on the subpackage models catches a
# mistyped *nested* key, but a bare ``TOP_K`` never reaches a subpackage
# model at all, so the tripwire is the only detector for flat names.
#
# Lifetime by shape:
#   FLAT   — pydantic cannot detect; retain while an upgrade path exists.
#   NESTED — block ``extra="forbid"`` detects without the tripwire;
#            retain one major after the rename, then deletable.
_RETIRED_ENV_VARS: dict[str, str] = {
    # ── FLAT (pre-v2.0.0 root-level names moved into nested blocks) ──
    # Pydantic-settings silently discards these — the tripwire is the
    # only detector.  Do NOT delete merely because a major has elapsed.
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
    # ── NESTED (v2 rename) — block extra="forbid" detects these without ──
    # the tripwire; the tripwire only improves the message.  Retain one
    # major version after the rename, then deletable (design.md D1).
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
    flat = sorted((old, new) for old, new in found if "__" not in old)
    nested = sorted((old, new) for old, new in found if "__" in old)
    sections = []
    if flat:
        flat_lines = "\n".join(f"  {old}  ->  {new}" for old, new in flat)
        sections.append(
            "Pre-v2.0.0 flat names (v2.0.0 moved subpackage settings into "
            "nested blocks). Pydantic-settings silently discards these — "
            "without this check they would be ignored with no error:\n"
            f"{flat_lines}"
        )
    if nested:
        nested_lines = "\n".join(f"  {old}  ->  {new}" for old, new in nested)
        sections.append(
            "Nested names retired by a later rename. These are rejected "
            'outright by their settings block\'s extra="forbid":\n'
            f"{nested_lines}"
        )
    body = "\n".join(sections)
    raise ValueError(
        "Retired configuration variable(s) found in the environment. "
        "Rename them:\n"
        f"{body}\n"
        "Cross-cutting names (EMBED_MODEL, RAG_PROFILE, PDF_READER, "
        "credentials) are unchanged. See docs/adr/037 for the full table."
    )
