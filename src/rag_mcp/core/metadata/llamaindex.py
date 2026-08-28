"""LlamaIndex metadata extraction backend.

Runs LlamaIndex ``TitleExtractor``, ``KeywordExtractor`` and
``SummaryExtractor`` over a bounded set of temporary document chunks.  The
per-node extractor output is aggregated back to one file-level metadata dict;
the ingestion chunker currently copies that file-level dict onto final stored
chunks.  This is therefore not persisted per-chunk LLM metadata enrichment.
"""

from __future__ import annotations

import asyncio
import logging

from ..settings import resolve_effective_settings
from ._common import (
    _normalise_category,
    _resolve_pipeline_timeout,
    _signal_degraded,
    _strip_llm_prefix,
    _truncate_keywords,
    _truncate_summary,
    logger,
)


def _get_max_chunks() -> int:
    """Return the maximum split nodes sent to expensive LLM extractors."""
    import os

    return int(os.getenv("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", "10"))


def _parse_keywords_from_meta(kws: str) -> list[str]:
    """Parse a keywords string into cleaned, lower-cased keywords."""
    kws_clean = _strip_llm_prefix(kws)
    return [
        stripped.lower()
        for kw in kws_clean.replace("\n", ",").split(",")
        if (stripped := _strip_llm_prefix(kw.strip()))
    ]


def _derive_category(keywords_all: list[str], title: str) -> str:
    """Derive a category from keywords or title."""
    for kw in keywords_all:
        candidate = _normalise_category(kw)
        if candidate != "uncategorised":
            return candidate
    if title:
        return _normalise_category(" ".join(title.split()[:2]))
    return "uncategorised"


def _first_nonempty_str_field(meta: dict, key: str) -> str:
    """Get the first non-empty string value for a metadata key."""
    val = meta.get(key, "")
    if isinstance(val, str) and val.strip():
        return _strip_llm_prefix(val.strip())
    return ""


def _aggregate_llamaindex_metadata(nodes: list) -> dict:
    """Aggregate temporary per-node extractor metadata to file-level metadata."""
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
        category,
        len(result.get("keywords", [])),
        len(summary),
    )
    return result


async def _extract_llamaindex_async(
    text: str, file_name: str = "", settings: object | None = None
) -> dict:
    """Extract bounded file-level metadata via LlamaIndex extractors.

    The full input is first split with the configured ``SentenceSplitter``.
    Only the first ``LLAMANDEX_EXTRACTOR_MAX_CHUNKS`` nodes are then sent to
    the expensive LLM-backed extractors.  This makes the setting a real chunk
    budget instead of the previous ``max_chunks * chunk_size`` character
    approximation.
    """
    resolved = resolve_effective_settings(settings)
    try:
        from ..providers.llm.registry import get as _llm_get

        backend = (
            resolved.local_backend
            if resolved.metadata_llm_provider == "local"
            else resolved.cloud_backend
        )
        llm = _llm_get(backend)(resolved, timeout=_resolve_pipeline_timeout(resolved, backend))
    except ImportError:
        logger.warning(
            "Required LLM package not installed for METADATA_LLM_PROVIDER=%s "
            "(backend=%s) — falling back to local mode",
            resolved.metadata_llm_provider,
            resolved.local_backend
            if resolved.metadata_llm_provider == "local"
            else resolved.cloud_backend,
        )
        _signal_degraded()
        from .extractor import _dispatch_local_extraction

        return await _dispatch_local_extraction(text, resolved, file_name)

    try:
        from llama_index.core import Document
        from llama_index.core.extractors import (
            KeywordExtractor,
            SummaryExtractor,
            TitleExtractor,
        )
        from llama_index.core.ingestion import IngestionPipeline
        from llama_index.core.node_parser import SentenceSplitter

        max_chunks = _get_max_chunks()
        if max_chunks <= 0:
            raise ValueError("LLAMANDEX_EXTRACTOR_MAX_CHUNKS must be greater than 0")

        doc = Document(text=text, metadata={"file_name": file_name})
        splitter = SentenceSplitter(
            chunk_size=resolved.chunking.chunk_size,
            chunk_overlap=resolved.chunking.chunk_overlap,
        )
        split_nodes = await asyncio.to_thread(lambda: splitter.get_nodes_from_documents([doc]))
        capped_nodes = split_nodes[:max_chunks]

        if not capped_nodes:
            logger.debug("LlamaIndex metadata extraction produced no split nodes")
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        # Splitting is complete before this pipeline begins, so every
        # transformation below is an expensive metadata extractor and the
        # max-chunks bound is exact.
        pipeline = IngestionPipeline(
            transformations=[
                TitleExtractor(nodes=min(5, len(capped_nodes)), llm=llm),
                KeywordExtractor(keywords=10, llm=llm),
                SummaryExtractor(summaries=["self"], llm=llm),
            ],
        )
        enriched_nodes = await pipeline.arun(nodes=capped_nodes)

        result = _aggregate_llamaindex_metadata(enriched_nodes)
        if result["category"] == "uncategorised":
            _signal_degraded()
        return result

    except Exception as exc:
        logger.warning(
            "LlamaIndex async metadata extraction failed: %s: %s — falling back to %s mode",
            type(exc).__name__,
            exc,
            resolved.metadata_llm_provider,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        _signal_degraded()
        from .extractor import _dispatch_local_extraction

        return await _dispatch_local_extraction(text, resolved, file_name)
