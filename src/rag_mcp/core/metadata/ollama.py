"""Ollama LLM metadata extraction backend.

Classifies text using Ollama's ``/api/generate`` endpoint with a bounded
retry loop and exponential backoff.  Also hosts the shared prompt-builder
and JSON-response parser used by the llama.cpp and OpenRouter chat
backends (which share the same classification prompt and response format).
Extracted from the original ``metadata_extractor.py`` monolith as part
of Phase 1.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from ..settings import resolve_effective_settings
from ._common import _normalise_category, _truncate_keywords, _truncate_summary, logger
from .taxonomy import _gather_existing_categories, _get_seed_categories


def _build_ollama_prompt(text: str, settings: object | None = None) -> str:
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
    seed = _get_seed_categories(settings)
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
    cleaned = _strip_markdown_fence(raw_response)

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")
    except ValueError:
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


def _get_ollama_max_attempts(resolved) -> int:
    """Return the bounded retry budget for Ollama metadata classification.

    Reads ``OLLAMA_CLASSIFY_MAX_ATTEMPTS`` at call time so tests can
    override it via ``monkeypatch.setenv`` without re-importing.

    Returns:
        Maximum number of attempts (>= 1).  Falls back to 3.
    """
    import os
    raw = os.getenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS")
    if raw is None:
        return resolved.metadata.ollama_classify_max_attempts
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return resolved.metadata.ollama_classify_max_attempts
    return max(1, value)


def _get_ollama_timeout(resolved) -> float:
    """Return the per-attempt HTTP timeout (seconds) for Ollama classification.

    Reads ``OLLAMA_CLASSIFY_TIMEOUT`` at call time so tests can override
    it via ``monkeypatch.setenv`` without re-importing.

    Returns:
        Per-attempt timeout in seconds.  Falls back to 30.0.
    """
    import os
    raw = os.getenv("OLLAMA_CLASSIFY_TIMEOUT")
    if raw is None:
        return resolved.metadata.ollama_classify_timeout
    try:
        return float(raw)
    except (TypeError, ValueError):
        return resolved.metadata.ollama_classify_timeout


# Sleep hook used between Ollama retry attempts.  Module-level so tests
# can replace it with a no-op without touching ``asyncio`` globally.
_retry_sleep = asyncio.sleep


async def _extract_ollama_async(
    text: str, file_name: str = "", settings: object | None = None
) -> dict:
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
    resolved = resolve_effective_settings(settings)
    import httpx

    fallback = {"category": "uncategorised", "keywords": [], "summary": ""}

    try:
        prompt = _build_ollama_prompt(text, resolved)
    except Exception as exc:
        logger.warning(
            "Ollama classification failed — could not build prompt: %s",
            exc,
        )
        return fallback

    data = {
        "model": resolved.metadata.ollama_classify_model,
        "prompt": prompt,
        "stream": False,
    }
    url = f"{resolved.ollama_base_url}/api/generate"

    max_attempts = _get_ollama_max_attempts(resolved)
    timeout_s = _get_ollama_timeout(resolved)
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
