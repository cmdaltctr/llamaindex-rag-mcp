"""Markdown chunking strategy (heading-aware, small-chunk dropping, heading prepend).

Experiment 6c recovery hooks: heading metadata propagation, optional
heading-prepend, and optional small-chunk dropping.  Extracted from the
original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging

from ...config import MARKDOWN_HEADING_PREPEND, MARKDOWN_MIN_CHUNK_FRACTION

logger = logging.getLogger(__name__)


def ensure_heading_metadata(nodes: list) -> None:
    """Defensively copy source heading metadata onto emitted child nodes.

    Experiment 6c recovery hook.  LlamaIndex splitters can emit child nodes
    whose own metadata omits heading information even though their
    ``source_node`` still has it.  This idempotently preserves that metadata
    for evidence/section evaluators and downstream search results.

    Args:
        nodes: Nodes emitted by the Markdown parser / splitter pipeline.
    """
    for node in nodes:
        source_node = getattr(node, "source_node", None)
        source_meta = getattr(source_node, "metadata", {}) if source_node else {}
        header_path = source_meta.get("header_path") or source_meta.get("heading_path")
        if header_path:
            node.metadata.setdefault("header_path", header_path)


def apply_heading_prepend(nodes: list) -> None:
    """Optionally prepend heading path to Markdown chunk text.

    Experiment 6c recovery knob controlled by ``MARKDOWN_HEADING_PREPEND``.
    Disabled by default.  When enabled, heading context becomes part of the
    embedded text while a double-prepend guard keeps repeated processing safe.

    Args:
        nodes: Markdown nodes after heading metadata propagation.
    """
    if not MARKDOWN_HEADING_PREPEND:
        return
    for node in nodes:
        header_path = node.metadata.get("header_path") or node.metadata.get("heading_path")
        if not header_path:
            continue
        prefix = f"[{header_path}] "
        text = getattr(node, "text", "")
        if text.startswith(prefix):
            continue
        node.text = prefix + text


def drop_small_markdown_chunks(nodes: list, chunk_size: int) -> list:
    """Optionally drop tiny Markdown chunks before embedding.

    Experiment 6c recovery knob controlled by
    ``MARKDOWN_MIN_CHUNK_FRACTION``.  Disabled by default.  Uses the same
    four-characters-per-token estimate used in the 6b/6c chunk-size reports.

    Args:
        nodes: Markdown nodes to filter.
        chunk_size: Effective Markdown chunk size for this ingestion run.

    Returns:
        The original node list when disabled, otherwise only nodes meeting
        the configured minimum estimated size.
    """
    if MARKDOWN_MIN_CHUNK_FRACTION <= 0:
        return nodes
    min_chars = int(chunk_size * 4 * MARKDOWN_MIN_CHUNK_FRACTION)
    kept = [node for node in nodes if len(getattr(node, "text", "")) >= min_chars]
    dropped = len(nodes) - len(kept)
    if dropped:
        logger.info("Dropped %d Markdown chunk(s) below min-size floor", dropped)
    return kept
