"""Shared helpers for metadata extraction backends.

Holds the category normalisation, keyword/summary truncation, and LLM-prefix
stripping helpers used by multiple backends (keyword, ollama, llamaindex).
Extracted from the original ``metadata_extractor.py`` monolith as part of
Phase 1 (behaviour-preserving mechanical extraction).
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import re

logger = logging.getLogger(__name__)

# Sleep hook used between classification retry attempts.  Module-level so
# tests can replace it with a no-op without touching ``asyncio`` globally.
_retry_sleep = asyncio.sleep

# Side-channel set by a backend when it abandons the configured LLM-backed
# mode for a lower tier (missing package, unparseable/empty response, or
# exhausted classification retries).  Read and reset by
# ``extract_metadata_with_status_async`` in ``extractor.py``.  A ContextVar
# rather than a module-level bool keeps concurrent async tasks isolated;
# plain awaits within one task share the same context, so a flag set deep
# in a backend call is visible to the wrapper once the await chain returns.
# See openspec/changes/fix-silent-metadata-degradation/design.md D3.
_degradation_flag: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_degradation_flag", default=False
)


def _signal_degraded() -> None:
    """Mark that metadata extraction fell back from the configured mode.

    Called from the LLM-backed backends' own failure branches (llamaindex
    pipeline abandonment, direct-chat retry exhaustion).  A backend cannot
    tell whether it was invoked as the primary mode or as a fallback, so
    it only reports "I did not produce a real classification"; the wrapper
    in ``extractor.py`` decides whether that counts as degradation for the
    configured mode.
    """
    _degradation_flag.set(True)


# ── Category normalisation helpers ──────────────────────────────────────

_MAX_CATEGORY_WORDS = 3
_MAX_KEYWORDS = 10
_MAX_SUMMARY_CHARS = 300


def _normalise_category(raw: str) -> str:
    """Normalise a category label for metadata consistency.

    Applies lowercase, replaces spaces with underscores, strips excess
    characters.  Rejects labels longer than ``_MAX_CATEGORY_WORDS``
    words by returning ``"uncategorised"``.

    Args:
        raw: The raw category string from the LLM or other source.

    Returns:
        Normalised category string, or ``"uncategorised"`` if invalid.
    """
    if not raw:
        return "uncategorised"

    cleaned = raw.strip().strip('"').strip("'").lower()
    # Replace any whitespace runs with a single underscore.
    cleaned = re.sub(r"\s+", "_", cleaned)
    # Remove any leading/trailing underscores, dashes, hashes, backticks,
    # or punctuation.  ``#`` handles markdown headings (``### Notes``)
    # and ``` ` ``` handles code-formatted keywords (`` `fetch` ``).
    cleaned = cleaned.strip("_-#`.,;:!?")

    word_count = len(cleaned.split("_"))
    if word_count > _MAX_CATEGORY_WORDS:
        logger.debug(
            "Category '%s' exceeds %d words — falling back to uncategorised",
            cleaned,
            _MAX_CATEGORY_WORDS,
        )
        return "uncategorised"

    if not cleaned:
        return "uncategorised"

    # Final shape check: a valid category must match
    # ``[a-z][a-z0-9_-]*`` — start with a letter, contain only lowercase
    # letters, digits, underscores, and hyphens.  This single principled
    # guard rejects any LLM output with leftover punctuation, markdown
    # syntax, code formatting, embedded labels (e.g. ``keywords:_/think``,
    # ``4._[pubmed_api]``, ``### notes``), or other noise — without us
    # having to enumerate every character class to strip.
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", cleaned):
        logger.debug(
            "Category '%s' rejected (does not match [a-z][a-z0-9_-]*) "
            "— falling back to uncategorised",
            cleaned,
        )
        return "uncategorised"

    return cleaned


def _truncate_keywords(keywords: list[str]) -> list[str]:
    """Truncate keyword list to ``_MAX_KEYWORDS``."""
    return keywords[:_MAX_KEYWORDS]


def _truncate_summary(summary: str) -> str:
    """Truncate summary string to ``_MAX_SUMMARY_CHARS``."""
    if len(summary) > _MAX_SUMMARY_CHARS:
        return summary[:_MAX_SUMMARY_CHARS] + "…"
    return summary


def _strip_llm_prefix(text: str) -> str:
    """Strip LLM-emitted labels and markdown formatting from extracted text.

    LlamaIndex's extractor prompts often produce outputs that begin with
    a literal label (``**Title:** Foo``, ``Keywords: a, b, c``,
    ``**Summary:** ...``) rather than the bare value.  The LLM may also
    wrap the entire value in markdown bold markers (``** "value" **``) or
    append an explanation paragraph after a double newline.

    This helper removes those artefacts so downstream code can treat the
    text as a clean value.

    Args:
        text: Raw text from an extractor's metadata field.

    Returns:
        Text with labels, bold markers, and trailing explanations stripped,
        or the original text if no recognised noise was present.
    """
    if not text:
        return text
    cleaned = re.sub(
        r"^\s*\**\s*(title|summary|keywords?)\s*\**\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Truncate at the first double-newline — LLMs often append an
    # explanation paragraph (e.g. "This title encapsulates...").
    if "\n\n" in cleaned:
        cleaned = cleaned[: cleaned.index("\n\n")]
    # Strip surrounding markdown bold markers (one or more ** groups) and quotes.
    cleaned = cleaned.strip()
    cleaned = re.sub(r"^(?:\*{1,2}\s*)+", "", cleaned)
    cleaned = re.sub(r"(?:\s*\*{1,2})+$", "", cleaned)
    cleaned = cleaned.strip("\"'")
    return cleaned.strip()


def _get_classify_max_attempts(resolved) -> int:
    """Return the bounded retry budget for metadata classification.

    The value is injected via ``resolved.metadata.classify_max_attempts``
    and constrained to ``> 0`` by ``Field(gt=0)`` on the settings model,
    which rejects rather than clamps, so no floor is needed here.

    Args:
        resolved: An :class:`EffectiveSettings` (or compatible) object.

    Returns:
        Maximum number of classification attempts (>= 1).
    """
    return resolved.metadata.classify_max_attempts


def _resolve_classify_timeout(resolved, provider: str) -> float:
    """Return the effective per-attempt classify timeout for *provider*.

    Returns the provider-specific override (``{provider}_classify_timeout_override``)
    when set, else the shared ``classify_timeout``.  An unrecognised
    *provider* has no matching field, so ``getattr`` falls through to the
    shared value — the same behaviour as an unset override.

    Args:
        resolved: An :class:`EffectiveSettings` (or compatible) object.
        provider: The registered backend name (``"llamacpp"``, ``"ollama"``,
            or ``"openrouter"``).

    Returns:
        Timeout in seconds.
    """
    override = getattr(resolved.metadata, f"{provider}_classify_timeout_override", None)
    return override if override is not None else resolved.metadata.classify_timeout


def _resolve_pipeline_timeout(resolved, provider: str) -> float:
    """Return the effective llamaindex pipeline timeout for *provider*.

    Returns the provider-specific override (``{provider}_pipeline_timeout_override``)
    when set, else the shared ``pipeline_timeout``.  An unrecognised
    *provider* has no matching field, so ``getattr`` falls through to the
    shared value — the same behaviour as an unset override.

    Args:
        resolved: An :class:`EffectiveSettings` (or compatible) object.
        provider: The registered backend name (``"llamacpp"``, ``"ollama"``,
            or ``"openrouter"``).

    Returns:
        Timeout in seconds.
    """
    override = getattr(resolved.metadata, f"{provider}_pipeline_timeout_override", None)
    return override if override is not None else resolved.metadata.pipeline_timeout
