"""LlamaIndex Extractor metadata extraction backend.

Extracts metadata using LlamaIndex's ``IngestionPipeline.arun()`` with
``TitleExtractor``, ``KeywordExtractor``, and ``SummaryExtractor``
(per-chunk enrichment via LLM).  Falls back to local mode if the LLM
package is not installed.  Extracted from the original
``metadata_extractor.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging

from ..settings import resolve_effective_settings
from ._common import (
    _normalise_category,
    _strip_llm_prefix,
    _truncate_keywords,
    _truncate_summary,
    logger,
)


def _get_max_chunks() -> int:
    """Return the max number of chunks for llamaindex extraction.

    Reads the env var at call time so tests can override it via
    ``monkeypatch.setenv`` after module load.
    """
    import os
    return int(os.getenv("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", "10"))


def _parse_keywords_from_meta(kws: str) -> list[str]:
    """Parse a keywords string into a list of cleaned, lowercased keywords.

    Strips LLM-emitted prefixes, splits on commas/newlines, and filters
    out empty values.

    Args:
        kws: Raw keywords string from LlamaIndex metadata.

    Returns:
        List of cleaned keyword strings.
    """
    kws_clean = _strip_llm_prefix(kws)
    return [
        stripped.lower()
        for kw in kws_clean.replace("\n", ",").split(",")
        if (stripped := _strip_llm_prefix(kw.strip()))
    ]


def _derive_category(keywords_all: list[str], title: str) -> str:
    """Derive a category from keywords or title.

    Tries each keyword in order, falling back to the first 1-2 words
    of the title.

    Args:
        keywords_all: List of keyword strings.
        title: Document title string (may be empty).

    Returns:
        Normalised category string, or "uncategorised".
    """
    for kw in keywords_all:
        candidate = _normalise_category(kw)
        if candidate != "uncategorised":
            return candidate
    if title:
        return _normalise_category(" ".join(title.split()[:2]))
    return "uncategorised"


def _first_nonempty_str_field(meta: dict, key: str) -> str:
    """Get the first non-empty string value for a metadata key.

    Args:
        meta: Node metadata dict.
        key: Metadata field name.

    Returns:
        Stripped value with LLM prefix removed, or empty string.
    """
    val = meta.get(key, "")
    if isinstance(val, str) and val.strip():
        return _strip_llm_prefix(val.strip())
    return ""


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

    for node in nodes:
        meta = getattr(node, "metadata", {}) if hasattr(node, "metadata") else {}
        if not meta:
            continue

        if not keywords_all:
            kws = _first_nonempty_str_field(meta, "excerpt_keywords")
            if kws:
                keywords_all = _parse_keywords_from_meta(kws)

        if not summary:
            summary = _first_nonempty_str_field(meta, "section_summary")

        if not title:
            title = _first_nonempty_str_field(meta, "document_title")

    category = _derive_category(keywords_all, title)

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


async def _extract_llamaindex_async(
    text: str, file_name: str = "", settings: object | None = None
) -> dict:
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
    resolved = resolve_effective_settings(settings)
    try:
        if resolved.metadata_llm_provider == "local":
            if resolved.local_backend == "llamacpp":
                from llama_index.llms.openai_like import OpenAILike
                llm = OpenAILike(
                    model=resolved.llamacpp_chat_model,
                    api_base=resolved.llamacpp_chat_url,
                    api_key="no-key",
                    request_timeout=180.0,
                )
            else:
                from llama_index.llms.ollama import Ollama
                llm = Ollama(
                    model=resolved.metadata.ollama_classify_model,
                    base_url=resolved.ollama_base_url,
                    request_timeout=180.0,
                )
        else:
            from ..providers.llm.registry import get as _llm_get
            llm = _llm_get(resolved.cloud_backend)(resolved)
    except ImportError:
        logger.warning(
            "Required LLM package not installed for METADATA_LLM_PROVIDER=%s "
            "(backend=%s) — falling back to local mode",
            resolved.metadata_llm_provider,
            resolved.local_backend if resolved.metadata_llm_provider == "local" else resolved.cloud_backend,
        )
        # Lazy import to avoid a circular dependency: extractor.py imports
        # this module at load time, but the fallback dispatch lives in
        # extractor.py.  The import only runs at call time.
        from .extractor import _dispatch_local_extraction
        return await _dispatch_local_extraction(text, resolved, file_name)

    try:
        from llama_index.core import Document
        from llama_index.core.ingestion import IngestionPipeline
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.core.extractors import (
            KeywordExtractor,
            SummaryExtractor,
            TitleExtractor,
        )

        max_chunks = _get_max_chunks()
        capped_text = text[:max_chunks * resolved.chunk_size]

        doc = Document(text=capped_text, metadata={"file_name": file_name})

        pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(
                    chunk_size=resolved.chunk_size,
                    chunk_overlap=resolved.chunk_overlap,
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
            "falling back to %s mode",
            type(exc).__name__,
            exc,
            resolved.metadata_llm_provider,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        # Lazy import — see note above.
        from .extractor import _dispatch_local_extraction
        return await _dispatch_local_extraction(text, resolved, file_name)
