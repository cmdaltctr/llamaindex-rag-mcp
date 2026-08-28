"""Shared helpers for metadata extraction backends.

Holds the category normalisation, keyword/summary truncation, and LLM-prefix
stripping helpers used by multiple backends (keyword, ollama, llamaindex).
Extracted from the original ``metadata_extractor.py`` monolith as part of
Phase 1 (behaviour-preserving mechanical extraction).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

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
            cleaned, _MAX_CATEGORY_WORDS,
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
        cleaned = cleaned[:cleaned.index("\n\n")]
    # Strip surrounding markdown bold markers (one or more ** groups) and quotes.
    cleaned = cleaned.strip()
    cleaned = re.sub(r"^(?:\*{1,2}\s*)+", "", cleaned)
    cleaned = re.sub(r"(?:\s*\*{1,2})+$", "", cleaned)
    cleaned = cleaned.strip('"\'')
    return cleaned.strip()
