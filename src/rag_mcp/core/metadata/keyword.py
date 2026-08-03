"""Keyword-regex metadata extraction backend.

Classifies text using regex pattern matching against user-overridable rules.
Each rule maps a regex pattern (case-insensitive) to a category label; the
category with the most keyword matches wins.  Extracted from the original
``metadata_extractor.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from ...config import METADATA_KEYWORD_RULES
from ._common import logger

# ── Default keyword rules ──────────────────────────────────────────────
# Each rule maps a regex pattern (case-insensitive) to a category label.
# Rules are scored by the number of matches found in the document text;
# the category with the highest score is assigned.
#
# Users can override these by setting METADATA_KEYWORD_RULES in .env
# to a JSON string of [{"pattern": "regex", "category": "name"}, ...].

_DEFAULT_KEYWORD_RULES: list[dict[str, str]] = [
    {
        "pattern": "attention|transformer|token|embedding|llm|rag|neural|deep.learning",
        "category": "AI",
    },
    {
        "pattern": "mantiq|logic|reasoning|ontology|epistemology|ghazali|usul",
        "category": "Philosophy",
    },
    {
        "pattern": "crispr|genome|protein|cell|biology|cancer|gene",
        "category": "Biology",
    },
    {
        "pattern": "marketing|seo|campaign|brand|pricing|funnel|conversion",
        "category": "Marketing",
    },
    {
        "pattern": "javascript|python|rust|api|frontend|backend|compiler",
        "category": "Programming",
    },
]

# ── Keyword rule loading ────────────────────────────────────────────────


def _load_keyword_rules() -> list[dict[str, str]]:
    """Load keyword->category rules, preferring env var over defaults.

    Returns:
        List of rule dicts with keys ``pattern`` and ``category``.
        Falls back to ``_DEFAULT_KEYWORD_RULES`` if
        ``METADATA_KEYWORD_RULES`` is not set or contains invalid JSON.
    """
    if not METADATA_KEYWORD_RULES:
        return _DEFAULT_KEYWORD_RULES

    try:
        custom = json.loads(METADATA_KEYWORD_RULES)
        if not isinstance(custom, list):
            raise ValueError("METADATA_KEYWORD_RULES must be a JSON array")
        for rule in custom:
            if "pattern" not in rule or "category" not in rule:
                raise ValueError(
                    "Each rule must have 'pattern' and 'category' keys"
                )
        logger.info(
            "Loaded %d custom keyword rule(s) from METADATA_KEYWORD_RULES",
            len(custom),
        )
        return custom
    except ValueError as exc:
        logger.warning(
            "Invalid METADATA_KEYWORD_RULES (%s) — falling back to defaults",
            exc,
        )
        return _DEFAULT_KEYWORD_RULES


def _extract_keyword(text: str) -> dict:
    """Classify text using regex keyword matching with scoring.

    Each rule is tested against *text* (case-insensitive).  The category
    with the most keyword matches wins.  If no keywords match, the
    category is ``"uncategorised"``.

    Args:
        text: The full document text to classify.

    Returns:
        A dict with key ``"category"``, e.g. ``{"category": "AI"}`` or
        ``{"category": "uncategorised"}``.
    """
    rules = _load_keyword_rules()
    if not rules:
        return {"category": "uncategorised"}

    scores: dict[str, int] = {}
    for rule in rules:
        pattern = rule["pattern"]
        category = rule["category"]
        try:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            if matches > 0:
                scores[category] = matches
        except re.error as exc:
            logger.warning(
                "Invalid regex pattern for category '%s': %s — skipping",
                category,
                exc,
            )
            continue

    if not scores:
        return {"category": "uncategorised"}

    best_category = max(scores, key=scores.__getitem__)  # type: ignore[arg-type]
    logger.debug(
        "Keyword scores: %s → %s", scores, best_category
    )
    return {"category": best_category}


async def _extract_keyword_async(text: str) -> dict:
    """Async wrapper around keyword extraction.

    Offloads to a worker thread because regex matching against large
    documents (10+ MB) can take several seconds and would otherwise
    block the event loop.  See ADR-015 / Experiment 4 findings.

    Args:
        text: The full document text to classify.

    Returns:
        Same dict as ``_extract_keyword()``.
    """
    return await asyncio.to_thread(_extract_keyword, text)
