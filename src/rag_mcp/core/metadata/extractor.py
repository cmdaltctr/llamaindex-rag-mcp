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

from ._common import logger
from .registry import available as _metadata_available, get as _metadata_get
from ..settings import resolve_effective_settings


def _extract_disabled() -> dict:
    """Return an empty dict — no metadata extraction.

    Returns:
        An empty dict (``{}``).
    """
    return {}


def _local_strategy_name(settings) -> str:
    """Map provider configuration to the registered strategy name.

    This is provider *selection* (which backend this deployment is
    configured for), not strategy dispatch: it yields a name that the
    registry then resolves. Adding a backend means registering it and
    naming it here — no import and no branch over strategy behaviour.
    """
    if settings.metadata_llm_provider == "cloud":
        return _CLOUD_BACKENDS.get(settings.cloud_backend, "openrouter")
    return _LOCAL_BACKENDS.get(settings.local_backend, "ollama")


async def _dispatch_local_extraction(
    text: str, settings: object | None = None, file_name: str = ""
) -> dict:
    """Resolve the configured local/cloud backend and run it.

    Kept as a named entry point because ``llamaindex.py`` degrades to it when
    the LlamaIndex extractor is unavailable. Dispatch itself goes through the
    registry — this only maps provider configuration to a strategy name.
    """
    resolved = resolve_effective_settings(settings)
    return await _metadata_get(_local_strategy_name(resolved))(
        text, file_name, resolved
    )


# Provider config value → registered strategy name.
_LOCAL_BACKENDS = {"llamacpp": "llamacpp", "ollama": "ollama"}
_CLOUD_BACKENDS = {"openrouter": "openrouter"}


# JSON Schema for the classification response, mirroring the three keys
# ``_parse_ollama_json_response`` expects.  Only the OpenRouter backend sends
# a full schema — Ollama and llama.cpp use the cheaper JSON-mode flags
# (``format`` / ``response_format``), which their local servers implement
# uniformly.  OpenRouter fans out to many upstream providers, so the schema
# buys field-level guarantees that plain JSON mode does not.
_CLASSIFY_JSON_SCHEMA = {
    "name": "document_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "The best category label for the document.",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 relevant keywords drawn from the document.",
            },
            "summary": {
                "type": "string",
                "description": "Single-sentence summary, max 300 characters.",
            },
        },
        "required": ["category", "keywords", "summary"],
        "additionalProperties": False,
    },
}

# HTTP statuses that mean "OpenRouter will never accept this payload".  429 is
# deliberately absent — rate limiting is transient and belongs on the normal
# backoff path.  401/403 are absent too: a bad API key is not fixed by
# dropping structured outputs.
_UNSUPPORTED_PARAM_STATUSES = frozenset({400, 404, 422})


def _is_unsupported_params_error(exc: Exception) -> bool:
    """True if *exc* is OpenRouter rejecting the request parameters outright.

    Used to distinguish "no endpoint for this model supports structured
    outputs" from a transient fault, so the caller can drop the constraint
    instead of burning its retry budget on a payload that cannot succeed.

    Args:
        exc: The exception raised by the classification attempt.

    Returns:
        ``True`` if the request should be downgraded and retried.
    """
    import httpx

    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _UNSUPPORTED_PARAM_STATUSES
    )


async def _extract_openrouter_chat_async(
    text: str, file_name: str = "", settings: object | None = None
) -> dict:
    """Classify text using OpenRouter's OpenAI-compatible /v1/chat/completions.

    Mirrors ``_extract_llamacpp_chat_async`` but targets OpenRouter's API
    with ``OPENROUTER_API_KEY`` auth and ``OPENROUTER_LLM_MODEL``.

    Args:
        text: The full document text (only the first 3000 chars are sent).

    Returns:
        A dict with ``category``, ``keywords``, ``summary``.
    """
    import httpx

    from ._common import _get_classify_max_attempts, _get_classify_timeout, _retry_sleep
    from .ollama import (
        _build_ollama_prompt,
        _parse_ollama_json_response,
    )

    fallback = {"category": "uncategorised", "keywords": [], "summary": ""}

    resolved = resolve_effective_settings(settings)
    try:
        prompt = _build_ollama_prompt(text, resolved)
    except Exception as exc:
        logger.warning(
            "OpenRouter classification failed — could not build prompt: %s",
            exc,
        )
        return fallback

    data = {
        "model": resolved.openrouter_llm_model,
        "messages": [
            {"role": "system", "content": "You are a document classification assistant. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        # Constrain generation to the classification schema.  Structured-output
        # support is per-ENDPOINT, not per-model — the same model served by two
        # upstream providers may support it on only one — so `require_parameters`
        # keeps the request off endpoints that would ignore the schema.  If that
        # leaves nothing to route to, the retry loop below drops both fields and
        # falls back to prompt-only JSON (ADR-024: cloud degrades gracefully).
        "response_format": {
            "type": "json_schema",
            "json_schema": _CLASSIFY_JSON_SCHEMA,
        },
        "provider": {"require_parameters": True},
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    max_attempts = _get_classify_max_attempts(resolved)
    timeout_s = _get_classify_timeout(resolved)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    url,
                    json=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {resolved.openrouter_api_key}",
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

            # A hard 4xx here almost always means `require_parameters` left no
            # routable endpoint for this model, or the upstream rejected the
            # schema.  Repeating the identical payload cannot succeed, so drop
            # the constraint once and continue on the prompt-only path — the
            # same one Ollama and llama.cpp use.  No backoff: this is a
            # payload fault, not a transient one.
            if _is_unsupported_params_error(exc) and "response_format" in data:
                logger.info(
                    "OpenRouter rejected structured outputs for model %s "
                    "(HTTP %s) — retrying without response_format.",
                    data["model"],
                    exc.response.status_code,  # type: ignore[attr-defined]
                )
                data.pop("response_format", None)
                data.pop("provider", None)
                continue

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


async def extract_metadata_async(
    file_text: str, file_name: str = "", settings: object | None = None
) -> dict:
    """Async counterpart of ``extract_metadata()``.

    Dispatches to the appropriate async extraction function based on
    ``METADATA_EXTRACTION_MODE``.

    Args:
        file_text: The full text content of the document.
        file_name: Name of the file (used by llamaindex mode).

    Returns:
        A dict of metadata key-value pairs (same shape as sync version).
    """
    resolved = resolve_effective_settings(settings)
    mode = resolved.metadata.extraction_mode.lower()

    if mode == "disabled":
        return _extract_disabled()

    # ``local`` is a provider-selection alias, not a strategy name.
    name = _local_strategy_name(resolved) if mode == "local" else mode

    if name not in _metadata_available():
        logger.warning(
            "Unknown metadata extraction mode %r — falling back to keyword. "
            "Registered strategies: %s",
            resolved.metadata.extraction_mode,
            ", ".join(_metadata_available()),
        )
        name = "keyword"

    return await _metadata_get(name)(file_text, file_name, resolved)
