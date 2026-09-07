"""Model-token-aware Markdown splitting and source heading derivation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from llama_index.core.schema import MetadataMode, TextNode

from ...integrations.tokenizer import load_tokenizer

logger = logging.getLogger(__name__)

MODEL_AWARE_PATH = "model_token_aware"
LEGACY_PATH = "legacy_fallback"
_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


@dataclass(frozen=True)
class MarkdownChunkingResolution:
    """Resolved Markdown tokenizer state for one ingestion operation."""

    tokenizer: Any | None
    tokenizer_identity: dict[str, str]
    resolved_splitter: str

    @property
    def model_token_aware(self) -> bool:
        """Return whether exact model-token splitting is available."""
        return self.tokenizer is not None and self.resolved_splitter == MODEL_AWARE_PATH


def resolve_markdown_chunking(settings: Any) -> MarkdownChunkingResolution:
    """Resolve the configured Markdown tokenizer once at an operation boundary.

    Args:
        settings: Injected effective settings.

    Returns:
        The cached tokenizer, its configured identity, and the resolved path.
    """
    model = settings.embedding.tokenizer_model.strip()
    revision = settings.embedding.tokenizer_revision.strip()
    identity = {"model": model, "revision": revision}
    if not model or not revision:
        if model or revision:
            logger.warning(
                "Model-token-aware Markdown chunking is unavailable because "
                "both tokenizer model and revision are required. "
                "Using the legacy Markdown splitter."
            )
        return MarkdownChunkingResolution(None, identity, LEGACY_PATH)

    try:
        tokenizer = load_tokenizer(model, revision)
    except Exception as exc:
        logger.warning(
            "Model-token-aware Markdown chunking is unavailable for tokenizer %r "
            "revision %r: %s. Using the legacy Markdown splitter.",
            model,
            revision,
            exc,
        )
        return MarkdownChunkingResolution(None, identity, LEGACY_PATH)
    return MarkdownChunkingResolution(tokenizer, identity, MODEL_AWARE_PATH)


def split_markdown_documents(
    documents: list,
    *,
    chunk_size: int,
    chunk_overlap: int,
    resolution: MarkdownChunkingResolution,
    heading_prepend: bool = False,
) -> list:
    """Split Markdown documents with the resolved embedding tokenizer.

    Args:
        documents: LlamaIndex documents containing source Markdown.
        chunk_size: Maximum finalised chunk-text token count.
        chunk_overlap: Requested overlap in tokenizer units.
        resolution: Operation-scoped tokenizer resolution.

    Returns:
        Text nodes with source-derived ``header_path`` metadata.
    """
    if not resolution.model_token_aware:
        raise ValueError("Model-token-aware splitting requires a resolved tokenizer")

    from semantic_text_splitter import MarkdownSplitter

    tokenizer = resolution.tokenizer
    nodes: list[TextNode] = []
    for document in documents:
        source_text = document.get_content(metadata_mode=MetadataMode.NONE)
        if not source_text.strip():
            continue
        headings = _heading_positions(source_text)
        splitter = _markdown_splitter(
            MarkdownSplitter,
            tokenizer,
            chunk_size,
            chunk_overlap,
        )
        chunks = splitter.chunk_indices(source_text)
        for offset, chunk in chunks:
            if heading_prepend:
                fitted = _fit_chunk(
                    headings,
                    offset,
                    chunk,
                    tokenizer=tokenizer,
                    markdown_splitter=MarkdownSplitter,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            else:
                fitted = [(offset, chunk, _header_path_at(headings, offset))]
            for _final_offset, final_text, header_path in fitted:
                metadata = dict(getattr(document, "metadata", {}))
                metadata.pop("heading_path", None)
                metadata.pop("header_path", None)
                if header_path:
                    metadata["header_path"] = header_path
                node = TextNode(text=final_text, metadata=metadata)
                for attribute in (
                    "excluded_embed_metadata_keys",
                    "excluded_llm_metadata_keys",
                ):
                    values = getattr(document, attribute, None)
                    if values:
                        setattr(node, attribute, list(values))
                nodes.append(node)
    return nodes


def _markdown_splitter(
    splitter_type: Any,
    tokenizer: Any,
    capacity: int,
    overlap: int,
) -> Any:
    """Build a Markdown splitter with a valid tokenizer-unit overlap."""
    safe_capacity = max(1, capacity)
    safe_overlap = min(overlap, max(0, safe_capacity - 1))
    return splitter_type.from_huggingface_tokenizer(
        tokenizer,
        safe_capacity,
        overlap=safe_overlap,
    )


def _fit_chunk(
    headings: list[tuple[int, int, str]],
    offset: int,
    chunk: str,
    *,
    tokenizer: Any,
    markdown_splitter: Any,
    chunk_size: int,
    chunk_overlap: int,
    depth: int = 0,
) -> list[tuple[int, str, str]]:
    """Fit one source chunk after reserving its heading prefix."""
    header_path = _header_path_at(headings, offset)
    prefix = f"[{header_path}] " if header_path else ""
    prefix_tokens = _token_count(tokenizer, prefix)
    capacity = max(1, chunk_size - prefix_tokens)
    if (
        _token_count(tokenizer, chunk) <= capacity
        and _token_count(tokenizer, prefix + chunk) <= chunk_size
    ):
        return [(offset, chunk, header_path)]
    if depth >= 8:
        logger.warning(
            "Markdown chunk could not be reduced below the final token cap; "
            "keeping the smallest structural result"
        )
        return [(offset, chunk, header_path)]

    splitter = _markdown_splitter(markdown_splitter, tokenizer, capacity, chunk_overlap)
    children = splitter.chunk_indices(chunk)
    if len(children) == 1 and children[0][1] == chunk:
        return [(offset, chunk, header_path)]

    result: list[tuple[int, str, str]] = []
    for child_offset, child in children:
        result.extend(
            _fit_chunk(
                headings,
                offset + child_offset,
                child,
                tokenizer=tokenizer,
                markdown_splitter=markdown_splitter,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                depth=depth + 1,
            )
        )
    return result


def _heading_positions(text: str) -> list[tuple[int, int, str]]:
    """Return ATX heading positions, levels, and normalised titles."""
    positions: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        match = _ATX_HEADING.match(line.rstrip("\r\n"))
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
            positions.append((offset, len(match.group(1)), title))
        offset += len(line)
    return positions


def _header_path_at(headings: list[tuple[int, int, str]], offset: int) -> str:
    """Return the ATX heading chain enclosing a source character offset."""
    chain: list[str] = []
    for heading_offset, level, title in headings:
        if heading_offset > offset:
            break
        chain = chain[: level - 1]
        chain.append(title)
    return f"/{'/'.join(chain)}/" if chain else ""


def _token_count(tokenizer: Any, text: str) -> int:
    """Count tokens without allowing tokenizer truncation to affect sizing."""
    return len(tokenizer.encode(text).ids)
