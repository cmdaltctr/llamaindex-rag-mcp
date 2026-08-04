"""Metadata extraction orchestrator.

Dispatches to the configured extraction backend based on
``METADATA_EXTRACTION_MODE``.  Also hosts the ``disabled`` sentinel, the
local-mode provider dispatch, and the OpenRouter cloud chat backend
(OpenRouter is not a standalone backend module — it routes through the
local/llamaindex mode via the provider registry; see PROPOSAL §5.2).
Extracted from the original ``metadata_extractor.py`` monolith as part
of Phase 1.

Modes
-----
- ``"disabled"`` — returns an empty dict (no metadata).
- ``"keyword"`` — regex pattern matching against user-overridable rules.
- ``"local"`` — LLM chat API call per file with hybrid category taxonomy.
  Uses Ollama's /api/generate, llama.cpp's /v1/chat/completions, or
  OpenRouter's /v1/chat/completions depending on METADATA_LLM_PROVIDER.
- ``"llamaindex"`` — LlamaIndex IngestionPipeline with TitleExtractor,
  KeywordExtractor, and SummaryExtractor (per-chunk enrichment via LLM).
  Falls back to local mode if the LLM package is not installed, then to
  keyword mode if the backend is also unreachable.

Degradation ladder
------------------
``llamaindex`` (richest — per-chunk extractors) →
``local`` (middle — per-file LLM classification) →
``keyword`` (last resort — regex only, no LLM required)
"""

from __future__ import annotations

import logging

from ...config import settings
from ._common import logger
from .keyword import _extract_keyword_async
from .llamacpp import _extract_llamacpp_chat_async
from .llamaindex import _extract_llamaindex_async
from .ollama import (
    _build_ollama_prompt,
    _extract_ollama_async,
    _get_ollama_max_attempts,
    _get_ollama_timeout,
    _parse_ollama_json_response,
    _retry_sleep,
)


def _extract_disabled() -> dict:
    """Return an empty dict — no metadata extraction.

    Returns:
        An empty dict (``{}``).
    """
    return {}


async def _dispatch_local_extraction(text: str) -> dict:
    """Dispatch to the appropriate extraction function based on provider config.

    Routes based on ``METADATA_LLM_PROVIDER`` (local|cloud) and the
    corresponding ``LOCAL_BACKEND`` or ``CLOUD_BACKEND`` sub-provider.

    Args:
        text: The full document text.

    Returns:
        A dict with ``category``, ``keywords``, ``summary``.
    """
    if settings.metadata_llm_provider == "cloud":
        if settings.cloud_backend == "openrouter":
            return await _extract_openrouter_chat_async(text)
        # Future cloud sub-providers would dispatch here.
        return await _extract_openrouter_chat_async(text)
    elif settings.local_backend == "llamacpp":
        return await _extract_llamacpp_chat_async(text)
    else:
        return await _extract_ollama_async(text)


async def _extract_openrouter_chat_async(text: str) -> dict:
    """Classify text using OpenRouter's OpenAI-compatible /v1/chat/completions.

    Mirrors ``_extract_llamacpp_chat_async`` but targets OpenRouter's API
    with ``OPENROUTER_API_KEY`` auth and ``OPENROUTER_LLM_MODEL``.

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
            "OpenRouter classification failed — could not build prompt: %s",
            exc,
        )
        return fallback

    data = {
        "model": settings.openrouter_llm_model,
        "messages": [
            {"role": "system", "content": "You are a document classification assistant. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    max_attempts = _get_ollama_max_attempts()
    timeout_s = _get_ollama_timeout()
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    url,
                    json=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                raw = body["choices"][0]["message"]["content"].strip()

            result = _parse_ollama_json_response(raw)

            logger.info(
                "OpenRouter classified document as: %s (keywords=%d, "
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
                "OpenRouter classification attempt %d/%d failed: %s: %s",
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                exc,
            )

            if attempt + 1 < max_attempts:
                backoff = 2 ** attempt
                await _retry_sleep(backoff)

    logger.warning(
        "OpenRouter classification failed after %d attempt(s) — "
        "falling back to uncategorised: %s: %s",
        max_attempts,
        type(last_error).__name__ if last_error else "Unknown",
        last_error,
    )
    return fallback


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
    mode = settings.metadata_extraction_mode.lower()

    if mode == "disabled":
        return _extract_disabled()
    elif mode == "keyword":
        return await _extract_keyword_async(file_text)
    elif mode == "local":
        return await _dispatch_local_extraction(file_text)
    elif mode == "llamaindex":
        return await _extract_llamaindex_async(file_text, file_name)
    else:
        logger.warning(
            "Unknown METADATA_EXTRACTION_MODE '%s' — falling back to keyword",
            settings.metadata_extraction_mode,
        )
        return await _extract_keyword_async(file_text)
