"""llama.cpp metadata extraction backend.

Classifies text using llama.cpp's OpenAI-compatible
``/v1/chat/completions`` endpoint.  Mirrors the Ollama backend but uses
the OpenAI chat format.  Shares the same prompt-builder, JSON parser,
and retry/backoff helpers from the Ollama backend.  Extracted from the
original ``metadata_extractor.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging

from ...config import settings
from ._common import logger
from .ollama import (
    _build_ollama_prompt,
    _get_ollama_max_attempts,
    _get_ollama_timeout,
    _parse_ollama_json_response,
    _retry_sleep,
)


async def _extract_llamacpp_chat_async(text: str) -> dict:
    """Classify text using llama.cpp's OpenAI-compatible /v1/chat/completions.

    Mirrors ``_extract_ollama_async`` but uses the OpenAI chat format instead
    of Ollama's /api/generate.  Shares the same retry/backoff logic and
    fallback behaviour.

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
            "llama.cpp classification failed — could not build prompt: %s",
            exc,
        )
        return fallback

    data = {
        "model": settings.llamacpp_chat_model,
        "messages": [
            {"role": "system", "content": "You are a document classification assistant. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    url = f"{settings.llamacpp_chat_url}/chat/completions"

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
                        "Authorization": "Bearer no-key",
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                raw = body["choices"][0]["message"]["content"].strip()

            result = _parse_ollama_json_response(raw)

            logger.info(
                "llama.cpp classified document as: %s (keywords=%d, "
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
                "llama.cpp classification attempt %d/%d failed: %s: %s",
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                exc,
            )

            if attempt + 1 < max_attempts:
                backoff = 2 ** attempt
                await _retry_sleep(backoff)

    logger.warning(
        "llama.cpp classification failed after %d attempt(s) — "
        "falling back to uncategorised: %s: %s",
        max_attempts,
        type(last_error).__name__ if last_error else "Unknown",
        last_error,
    )
    return fallback
