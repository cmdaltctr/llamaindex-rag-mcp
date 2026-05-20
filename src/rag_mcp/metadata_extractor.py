"""Metadata extraction during document ingestion.

Provides a single public entry point ``extract_metadata(file_text, file_name)``
that dispatches to the active extraction mode based on the
``METADATA_EXTRACTION_MODE`` environment variable.

Modes
-----
- ``"disabled"`` — returns an empty dict (no metadata).
- ``"keyword"`` — regex pattern matching against user-overridable rules.
- ``"ollama"`` — single Ollama chat API call per file.
- ``"llamaindex"`` — stubbed for future LlamaIndex MetadataExtractor
  integration; falls back to keyword mode.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from .config import (
    METADATA_EXTRACTION_MODE,
    METADATA_KEYWORD_RULES,
    OLLAMA_BASE_URL,
    OLLAMA_CLASSIFY_MODEL,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
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
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Invalid METADATA_KEYWORD_RULES — falling back to defaults: %s",
            exc,
        )
        return _DEFAULT_KEYWORD_RULES


# ── Extraction functions ────────────────────────────────────────────────


def _extract_disabled() -> dict:
    """Return an empty dict — no metadata extraction.

    Returns:
        An empty dict (``{}``).
    """
    return {}


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


def _extract_ollama(text: str) -> dict:
    """Classify text using a local Ollama chat model.

    Sends the first 2000 characters of *text* to Ollama's
    ``/api/generate`` endpoint and asks the model to return a single
    category label.  Falls back to ``"uncategorised"`` on any error.

    Args:
        text: The full document text (only the first 2000 chars are sent).

    Returns:
        A dict with key ``"category"``, e.g. ``{"category": "AI"}`` or
        ``{"category": "uncategorised"}``.
    """
    try:
        # Use urllib.request (stdlib) to avoid adding a new dependency.
        import urllib.request

        prompt = (
            "Classify the following document into exactly one of these "
            "categories: AI, Philosophy, Biology, Marketing, Programming, "
            "or uncategorised. Reply with only the category name, nothing "
            f"else.\n\nDocument:\n{text[:2000]}"
        )

        data = json.dumps({
            "model": OLLAMA_CLASSIFY_MODEL,
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")

        url = f"{OLLAMA_BASE_URL}/api/generate"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            result = body.get("response", "").strip().rstrip(".")

        # Normalise: take the first line, strip quotes/whitespace.
        result = result.split("\n")[0].strip().strip('"').strip("'")
        if not result:
            result = "uncategorised"

        logger.info("Ollama classified document as: %s", result)
        return {"category": result}

    except Exception as exc:
        logger.warning(
            "Ollama classification failed — falling back to uncategorised: %s",
            exc,
        )
        return {"category": "uncategorised"}


def _extract_llamaindex(text: str, file_name: str) -> dict:
    """Stub for future LlamaIndex MetadataExtractor integration.

    In v1 this mode is not yet implemented.  It logs an INFO message
    and falls back to keyword mode.

    Args:
        text: The full document text.
        file_name: Name of the file being processed (reserved for future use).

    Returns:
        A dict from ``_extract_keyword()``.
    """
    logger.info(
        "MetadataExtractor not yet implemented — falling back to keyword mode"
    )
    return _extract_keyword(text)


# ── Public API ──────────────────────────────────────────────────────────


def extract_metadata(file_text: str, file_name: str = "") -> dict:
    """Extract metadata from document text using the configured mode.

    Dispatches to the appropriate extraction function based on the
    ``METADATA_EXTRACTION_MODE`` environment variable.

    Args:
        file_text: The full text content of the document.
        file_name: Name of the file (used by llamaindex mode, reserved).

    Returns:
        A dict of metadata key-value pairs.  Currently always contains
        at least ``"category"`` (unless mode is ``"disabled"``, which
        returns ``{}``).  Future modes may add additional keys.
    """
    mode = METADATA_EXTRACTION_MODE.lower()

    if mode == "disabled":
        return _extract_disabled()
    elif mode == "keyword":
        return _extract_keyword(file_text)
    elif mode == "ollama":
        return _extract_ollama(file_text)
    elif mode == "llamaindex":
        return _extract_llamaindex(file_text, file_name)
    else:
        logger.warning(
            "Unknown METADATA_EXTRACTION_MODE '%s' — falling back to keyword",
            METADATA_EXTRACTION_MODE,
        )
        return _extract_keyword(file_text)
