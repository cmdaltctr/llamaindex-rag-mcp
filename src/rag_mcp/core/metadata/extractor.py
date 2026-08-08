"""Metadata extraction orchestrator.

Dispatches to the configured extraction backend based on
``METADATA__EXTRACTION_MODE``.  Also hosts the ``disabled`` sentinel and
the local-mode provider dispatch.  Extracted from the original
``metadata_extractor.py`` monolith as part of Phase 1.

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

from ._common import _degradation_flag, logger
from .registry import available as _metadata_available, get as _metadata_get
from ..settings import resolve_effective_settings

# Extraction modes for which the system promises an LLM-produced
# classification.  Only these can "degrade" — keyword/disabled never
# attempt an LLM call, so there is nothing to fall back from.
_LLM_BACKED_MODES = frozenset({"llamaindex", "local"})


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
        return settings.cloud_backend
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


async def extract_metadata_async(
    file_text: str, file_name: str = "", settings: object | None = None
) -> dict:
    """Async counterpart of ``extract_metadata()``.

    Dispatches to the appropriate async extraction function based on
    ``METADATA__EXTRACTION_MODE``.

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


async def extract_metadata_with_status_async(
    file_text: str, file_name: str = "", settings: object | None = None
) -> tuple[dict, bool]:
    """Extract metadata and report whether it degraded from the configured mode.

    Wraps :func:`extract_metadata_async` with a degradation signal: when
    the configured mode is LLM-backed (``llamaindex`` or ``local``) but
    extraction fell back to a lower tier — missing package, unreachable
    backend, a timed-out call, or an unparseable response — the second
    tuple element is ``True``. ``extract_metadata_async`` remains the
    dict-only public entry point; this wrapper is for callers (the
    ingestion chunker) that need to surface degradation to the caller
    instead of only logging it (see
    ``openspec/changes/fix-silent-metadata-degradation/design.md`` D3).

    Args:
        file_text: The full text content of the document.
        file_name: Name of the file (used by llamaindex mode).
        settings: Optional resolved ``EffectiveSettings``.

    Returns:
        A ``(metadata, degraded)`` tuple. ``metadata`` has the same shape
        ``extract_metadata_async`` returns. ``degraded`` is ``True`` only
        when the configured mode is LLM-backed and the result came from a
        lower tier; successful extraction in the configured mode, and
        keyword/disabled as the configured mode, always report ``False``.
    """
    resolved = resolve_effective_settings(settings)
    is_llm_backed = resolved.metadata.extraction_mode.lower() in _LLM_BACKED_MODES

    token = _degradation_flag.set(False)
    try:
        result = await extract_metadata_async(file_text, file_name, resolved)
        degraded = is_llm_backed and _degradation_flag.get()
        return result, degraded
    finally:
        _degradation_flag.reset(token)
