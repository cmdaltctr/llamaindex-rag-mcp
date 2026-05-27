"""Metadata extraction during document ingestion.

Provides a single public entry point ``extract_metadata(file_text, file_name)``
that dispatches to the active extraction mode based on the
``METADATA_EXTRACTION_MODE`` environment variable.

Modes
-----
- ``"disabled"`` — returns an empty dict (no metadata).
- ``"keyword"`` — regex pattern matching against user-overridable rules.
- ``"ollama"`` — Ollama chat API call per file with hybrid category taxonomy
  (queries ChromaDB for existing categories, prefers reuse, allows new labels).
- ``"llamaindex"`` — LlamaIndex IngestionPipeline with TitleExtractor,
  KeywordExtractor, and SummaryExtractor (per-chunk enrichment via Ollama).
  Falls back to ollama mode if ``llama-index-llms-ollama`` is not installed,
  then to keyword mode if Ollama is also unreachable.

Degradation ladder
------------------
``llamaindex`` (richest — per-chunk extractors) →
``ollama`` (middle — per-file Ollama classification) →
``keyword`` (last resort — regex only, no Ollama required)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import TYPE_CHECKING

from .config import (
    CHROMA_PERSIST_DIR,
    METADATA_EXTRACTION_MODE,
    METADATA_KEYWORD_RULES,
    OLLAMA_BASE_URL,
    OLLAMA_CLASSIFY_MAX_ATTEMPTS,
    OLLAMA_CLASSIFY_MODEL,
    OLLAMA_CLASSIFY_TIMEOUT,
)
from .chroma_utils import iter_collection_metadatas

if TYPE_CHECKING:
    pass

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

# ── Category taxonomy (for ollama mode's hybrid lookup) ─────────────────

# Cached ChromaDB client for category lookups (avoids re-opening the
# database on every file during batch ingestion).
_chroma_client = None
_chroma_client_lock = threading.Lock()


def _get_chroma_client():
    """Return a cached PersistentClient for category taxonomy queries.

    Lazily initialises on first call.  Reuses the same client across
    all ``_gather_existing_categories()`` calls within a process.

    Returns:
        A ``chromadb.PersistentClient`` instance.
    """
    global _chroma_client
    if _chroma_client is None:
        with _chroma_client_lock:
            if _chroma_client is None:
                import chromadb
                _chroma_client = chromadb.PersistentClient(
                    path=CHROMA_PERSIST_DIR
                )
    return _chroma_client


def _get_seed_categories() -> frozenset[str]:
    """Extract unique category names from the current keyword rules.

    These serve as the initial taxonomy when ChromaDB is empty (first run).
    The categories are normalised (lowercase) for consistent comparison.

    Returns:
        Frozen set of normalised seed category names.
    """
    rules = _load_keyword_rules()
    seen: set[str] = set()
    for rule in rules:
        cat = rule.get("category", "").lower()
        if cat:
            seen.add(cat)
    seen.add("uncategorised")
    return frozenset(seen)


def _gather_existing_categories() -> list[str]:
    """Query ChromaDB across all collections for unique category values.

    Fetches metadata from every collection in the persistent ChromaDB,
    extracts the ``"category"`` field from each entry, deduplicates,
    and normalises to lowercase.  Returns an empty list on failure
    (no crash — callers fall back to seed categories).

    Returns:
        List of unique, normalised category strings currently stored
        in ChromaDB.  Empty list if ChromaDB is unreachable or has no
        category metadata yet.
    """
    try:
        client = _get_chroma_client()

        categories: set[str] = set()
        for collection in client.list_collections():
            try:
                for meta in iter_collection_metadatas(collection):
                    if isinstance(meta, dict):
                        cat = meta.get("category")
                        if cat and isinstance(cat, str):
                            # Normalise here so duplicates from different
                            # capitalisations merge.
                            normalised = _normalise_category(cat)
                            if normalised != "uncategorised":
                                categories.add(normalised)
            except Exception as col_exc:
                logger.debug(
                    "Skipping collection '%s' during category lookup: %s",
                    collection.name if hasattr(collection, "name") else "?",
                    col_exc,
                )
                continue

        result_list = sorted(categories)
        if result_list:
            logger.debug("Found %d existing categories in ChromaDB", len(result_list))
        return result_list

    except Exception as exc:
        logger.warning(
            "Failed to query ChromaDB for existing categories: %s — "
            "classification will use seed categories only",
            exc,
        )
        return []


def _build_ollama_prompt(text: str) -> str:
    """Build the Ollama classification prompt with hybrid category taxonomy.

    Merges existing ChromaDB categories with seed categories from keyword
    rules, deduplicates, and formats them into the prompt's "EXISTING
    CATEGORIES" list.  The prompt instructs the model to prefer existing
    labels but allows proposing a new concise label if nothing fits.

    Args:
        text: The document text (first ~3000 chars are sent).

    Returns:
        Full prompt string ready for Ollama's ``/api/generate`` endpoint.
    """
    # Gather categories: ChromaDB existing + seed from keyword rules.
    existing = _gather_existing_categories()
    seed = _get_seed_categories()
    merged = set(existing) | set(seed)
    merged.discard("uncategorised")  # added explicitly below

    if merged:
        category_lines = "\n".join(f"- {cat}" for cat in sorted(merged))
        category_section = (
            "EXISTING CATEGORIES (use one of these if applicable):\n"
            f"{category_lines}\n"
            "- uncategorised\n"
        )
    else:
        # ChromaDB empty and no seeds?  Only happens with empty custom rules.
        category_section = (
            "EXISTING CATEGORIES:\n"
            "- uncategorised\n"
        )

    return (
        "You are a document classifier. Analyse the document below and "
        "return ONLY a JSON object — no explanations, no markdown, no "
        "backticks.  The JSON must have exactly these keys:\n\n"
        "  - \"category\": The best category label (string).\n"
        "  - \"keywords\": 3-5 relevant keywords from the document "
        "(list of strings).\n"
        "  - \"summary\": A single-sentence summary of the document "
        "(string, max 300 chars).\n\n"
        "INSTRUCTIONS:\n"
        "1. First, determine if the document fits one of the "
        "EXISTING CATEGORIES below.\n"
        "2. If YES: use that exact category name.\n"
        "3. If NO existing category fits: propose ONE new concise "
        "category label — 1-3 words, lowercase, underscores for spaces "
        "(e.g., \"music_theory\", \"environmental_science\").\n"
        "4. Prefer existing categories over creating new ones.\n"
        "5. If genuinely uncertain, use \"uncategorised\".\n\n"
        f"{category_section}\n"
        f"Document:\n{text[:3000]}"
    )


def _strip_markdown_fence(text: str) -> str:
    """Strip surrounding markdown code fences from a text payload.

    Some Ollama-served models (notably ``qwen3:0.6b``) wrap their JSON
    output in a fenced code block such as::

        ```json
        {"category": "ai"}
        ```

    or simply::

        ```
        {"category": "ai"}
        ```

    This helper trims one such surrounding fence before downstream
    parsing.  It only removes the *outermost* fence — content with a
    leading whitespace fence followed by other inline backticks is left
    alone.  Returns the original text unchanged if no fence is found.

    Args:
        text: Raw text from the Ollama response.

    Returns:
        Text with the outermost markdown code fence stripped, if present.
    """
    if not text:
        return text
    stripped = text.strip()
    fence_pattern = re.compile(
        r"^```[A-Za-z0-9_+-]*\s*\n(?P<body>.*?)\n```\s*$",
        re.DOTALL,
    )
    m = fence_pattern.match(stripped)
    if m:
        return m.group("body").strip()
    return stripped


def _parse_ollama_json_response(raw_response: str) -> dict:
    """Safely parse the Ollama JSON response into a metadata dict.

    Strips a surrounding markdown code fence if present (qwen3:0.6b and
    other small models often wrap JSON in ```` ```json ... ``` ````),
    then attempts ``json.loads()`` on the remainder.  If parsing fails,
    treats the raw text as the category with empty keywords/summary.
    Always returns a dict with keys ``category``, ``keywords``,
    ``summary``.

    Args:
        raw_response: The raw ``"response"`` string from Ollama.

    Returns:
        A dict, e.g. ``{"category": "ai", "keywords": [...], "summary": "..."}``.
    """
    # Default fallback dict
    fallback = {
        "category": "uncategorised",
        "keywords": [],
        "summary": "",
    }

    cleaned = _strip_markdown_fence(raw_response)

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")
    except (json.JSONDecodeError, ValueError):
        # Couldn't parse JSON — use raw text as category.
        logger.warning(
            "Ollama returned non-JSON response. Using raw text as category. "
            "Response: %s",
            raw_response[:200],
        )
        return {
            "category": _normalise_category(raw_response) or "uncategorised",
            "keywords": [],
            "summary": "",
        }

    # Extract and sanitise each field.
    category = _normalise_category(str(parsed.get("category", "")))
    if not category:
        category = "uncategorised"

    raw_keywords = parsed.get("keywords", [])
    if isinstance(raw_keywords, list):
        keywords = _truncate_keywords([
            str(k).strip().lower()
            for k in raw_keywords
            if k and str(k).strip()
        ])
    else:
        keywords = []

    raw_summary = parsed.get("summary", "")
    summary = _truncate_summary(str(raw_summary).strip()) if raw_summary else ""

    return {
        "category": category,
        "keywords": keywords,
        "summary": summary,
    }


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



# NOTE: Sync _extract_ollama removed — use _extract_ollama_async instead.


# NOTE: Sync _extract_llamaindex removed — use _extract_llamaindex_async instead.


def _get_max_chunks() -> int:
    """Return the max number of chunks for llamaindex extraction.

    Reads the env var at call time so tests can override it via
    ``monkeypatch.setenv`` after module load.
    """
    import os
    return int(os.getenv("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", "10"))


def _get_ollama_max_attempts() -> int:
    """Return the bounded retry budget for Ollama metadata classification.

    Reads ``OLLAMA_CLASSIFY_MAX_ATTEMPTS`` at call time so tests can
    override it via ``monkeypatch.setenv`` without re-importing.

    Returns:
        Maximum number of attempts (>= 1).  Falls back to 3.
    """
    import os
    raw = os.getenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS")
    if raw is None:
        return OLLAMA_CLASSIFY_MAX_ATTEMPTS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return OLLAMA_CLASSIFY_MAX_ATTEMPTS
    return max(1, value)


def _get_ollama_timeout() -> float:
    """Return the per-attempt HTTP timeout (seconds) for Ollama classification.

    Reads ``OLLAMA_CLASSIFY_TIMEOUT`` at call time so tests can override
    it via ``monkeypatch.setenv`` without re-importing.

    Returns:
        Per-attempt timeout in seconds.  Falls back to 30.0.
    """
    import os
    raw = os.getenv("OLLAMA_CLASSIFY_TIMEOUT")
    if raw is None:
        return OLLAMA_CLASSIFY_TIMEOUT
    try:
        return float(raw)
    except (TypeError, ValueError):
        return OLLAMA_CLASSIFY_TIMEOUT


# Sleep hook used between Ollama retry attempts.  Module-level so tests
# can replace it with a no-op without touching ``asyncio`` globally.
_retry_sleep = asyncio.sleep


def _aggregate_llamaindex_metadata(nodes: list) -> dict:
    """Aggregate per-node metadata into a single metadata dict.

    Takes the first non-empty value for each field across all enriched
    nodes.  Normalises category using ``_normalise_category`` and
    truncates keywords/summary.

    Args:
        nodes: List of LlamaIndex ``BaseNode`` objects with extracted metadata.

    Returns:
        A dict with ``category``, ``keywords``, ``summary``, and
        optionally ``document_title``.
    """
    keywords_all: list[str] = []
    summary = ""
    title = ""
    category = ""

    for node in nodes:
        meta = getattr(node, "metadata", {}) if hasattr(node, "metadata") else {}
        if not meta:
            continue

        # Collect keywords from all nodes - strip any "Keywords:" prefix
        # the LLM may have emitted before splitting on commas, then strip
        # any per-keyword label prefix (LLMs sometimes embed sub-labels
        # like ``Title:`` or ``Summary:`` mid-list).
        if not keywords_all:
            kws = meta.get("excerpt_keywords", "")
            if isinstance(kws, str) and kws.strip():
                kws_clean = _strip_llm_prefix(kws)
                keywords_all = [
                    stripped.lower()
                    for kw in kws_clean.replace("\n", ",").split(",")
                    if (stripped := _strip_llm_prefix(kw.strip()))
                ]

        # Use the first non-empty summary, with prefix stripped.
        if not summary:
            s = meta.get("section_summary", "")
            if isinstance(s, str) and s.strip():
                summary = _strip_llm_prefix(s.strip())

        # Use the first non-empty title, with prefix stripped.
        if not title:
            t = meta.get("document_title", "")
            if isinstance(t, str) and t.strip():
                title = _strip_llm_prefix(t.strip())

    # Derive category from the first keyword that normalises cleanly -
    # keywords are short by design (1-3 words each).  Skip keywords that
    # are too long or contain markdown noise (e.g. table syntax) and
    # fall through to subsequent ones.  As a final fallback, try the
    # first 1-2 words of the title before declaring "uncategorised".
    category = "uncategorised"
    for kw in keywords_all:
        candidate = _normalise_category(kw)
        if candidate != "uncategorised":
            category = candidate
            break
    if category == "uncategorised" and title:
        category = _normalise_category(" ".join(title.split()[:2]))

    result: dict = {
        "category": category,
        "keywords": _truncate_keywords(keywords_all),
        "summary": _truncate_summary(summary),
    }
    if title:
        result["document_title"] = title

    logger.info(
        "LlamaIndex extraction: category=%s, keywords=%d, summary=%d chars",
        category, len(result.get("keywords", [])), len(summary),
    )
    return result


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


async def _extract_ollama_async(text: str) -> dict:
    """Classify text using Ollama via async HTTP (httpx).

    Uses ``httpx.AsyncClient`` for non-blocking HTTP to Ollama's
    ``/api/generate`` endpoint with a bounded retry loop.  On transient
    failures (timeouts, connection errors, network errors) the call is
    retried up to ``OLLAMA_CLASSIFY_MAX_ATTEMPTS`` times with
    exponential backoff (``2 ** attempt`` seconds between attempts).
    Per-attempt HTTP timeout is ``OLLAMA_CLASSIFY_TIMEOUT`` seconds.
    On retry exhaustion the function returns the ``uncategorised``
    fallback dict and logs a single WARNING summarising the failure
    chain.

    Args:
        text: The full document text (only the first 3000 chars are sent).

    Returns:
        A dict with ``category``, ``keywords``, ``summary``.
    """
    import httpx

    fallback = {"category": "uncategorised", "keywords": [], "summary": ""}

    try:
        prompt = _build_ollama_prompt(text)
    except Exception as exc:
        logger.warning(
            "Ollama classification failed — could not build prompt: %s",
            exc,
        )
        return fallback

    data = {
        "model": OLLAMA_CLASSIFY_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    url = f"{OLLAMA_BASE_URL}/api/generate"

    max_attempts = _get_ollama_max_attempts()
    timeout_s = _get_ollama_timeout()
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    url,
                    json=data,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                body = resp.json()
                raw = body.get("response", "").strip()

            result = _parse_ollama_json_response(raw)

            logger.info(
                "Ollama classified document as: %s (keywords=%d, "
                "summary=%d chars, attempt=%d/%d)",
                result["category"],
                len(result.get("keywords", [])),
                len(result.get("summary", "")),
                attempt + 1,
                max_attempts,
            )
            return result

        except Exception as exc:
            last_error = exc
            logger.debug(
                "Ollama classification attempt %d/%d failed: %s: %s",
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                exc,
            )

            # Don't sleep after the final attempt.
            if attempt + 1 < max_attempts:
                backoff = 2 ** attempt
                await _retry_sleep(backoff)

    logger.warning(
        "Ollama classification failed after %d attempt(s) — "
        "falling back to uncategorised: %s: %s",
        max_attempts,
        type(last_error).__name__ if last_error else "Unknown",
        last_error,
    )
    return fallback


async def _extract_llamaindex_async(text: str, file_name: str) -> dict:
    """Extract metadata using LlamaIndex's ``IngestionPipeline.arun()``.

    Calls ``pipeline.arun()`` directly — no ThreadPoolExecutor workaround
    needed since we are already in an async context.

    Args:
        text: The full document text.
        file_name: Name of the file being processed.

    Returns:
        A dict with ``category``, ``keywords``, ``summary``, and
        optionally ``document_title``.  Falls back to keyword mode on failure.
    """
    try:
        from llama_index.llms.ollama import Ollama
    except ImportError:
        logger.warning(
            "llama-index-llms-ollama not installed — "
            "falling back to ollama mode"
        )
        return await _extract_ollama_async(text)

    try:
        from llama_index.core import Document
        from llama_index.core.ingestion import IngestionPipeline
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.core.extractors import (
            KeywordExtractor,
            SummaryExtractor,
            TitleExtractor,
        )

        llm = Ollama(
            model=OLLAMA_CLASSIFY_MODEL,
            base_url=OLLAMA_BASE_URL,
            request_timeout=180.0,
        )

        max_chunks = _get_max_chunks()
        from .config import CHUNK_SIZE, CHUNK_OVERLAP
        capped_text = text[:max_chunks * CHUNK_SIZE]

        doc = Document(text=capped_text, metadata={"file_name": file_name})

        pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(
                    chunk_size=CHUNK_SIZE,
                    chunk_overlap=CHUNK_OVERLAP,
                ),
                TitleExtractor(nodes=5, llm=llm),
                KeywordExtractor(keywords=10, llm=llm),
                SummaryExtractor(summaries=["self"], llm=llm),
            ],
        )

        # Call arun() directly — no nested-loop workaround needed.
        enriched_nodes = await pipeline.arun(documents=[doc])

        return _aggregate_llamaindex_metadata(enriched_nodes)

    except Exception as exc:
        logger.warning(
            "LlamaIndex async metadata extraction failed: %s: %s — "
            "falling back to ollama mode",
            type(exc).__name__,
            exc,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        return await _extract_ollama_async(text)


async def extract_metadata_async(file_text: str, file_name: str = "") -> dict:
    """Async counterpart of ``extract_metadata()``.

    Dispatches to the appropriate async extraction function based on
    ``METADATA_EXTRACTION_MODE``.

    Args:
        file_text: The full text content of the document.
        file_name: Name of the file (used by llamaindex mode).

    Returns:
        A dict of metadata key-value pairs (same shape as sync version).
    """
    mode = METADATA_EXTRACTION_MODE.lower()

    if mode == "disabled":
        return _extract_disabled()
    elif mode == "keyword":
        return await _extract_keyword_async(file_text)
    elif mode == "ollama":
        return await _extract_ollama_async(file_text)
    elif mode == "llamaindex":
        return await _extract_llamaindex_async(file_text, file_name)
    else:
        logger.warning(
            "Unknown METADATA_EXTRACTION_MODE '%s' — falling back to keyword",
            METADATA_EXTRACTION_MODE,
        )
        return await _extract_keyword_async(file_text)



# NOTE: Sync extract_metadata removed — use extract_metadata_async instead.
# The public API section is now just the async dispatch.
