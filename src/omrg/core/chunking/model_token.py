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
_CODE_FENCE = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_MAX_FIT_DEPTH = 8


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
        heading_prepend: Whether the heading path joins the embedded text.

    Returns:
        Text nodes with source-derived ``header_path`` metadata.

    Raises:
        ValueError: If no tokenizer is resolved, if the requested overlap
            does not fit the capacity, or if a chunk cannot be reduced
            below the finalised token cap.
    """
    if not resolution.model_token_aware:
        raise ValueError("Model-token-aware splitting requires a resolved tokenizer")
    _require_splitter_budget(chunk_size, chunk_overlap)

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
                _verify_final_size(
                    tokenizer,
                    final_text,
                    header_path,
                    heading_prepend=heading_prepend,
                    chunk_size=chunk_size,
                )
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
    """Build a Markdown splitter with the configured tokenizer-unit overlap."""
    return splitter_type.from_huggingface_tokenizer(
        tokenizer,
        capacity,
        overlap=overlap,
    )


def _require_splitter_budget(chunk_size: int, chunk_overlap: int) -> None:
    """Fail when the configured capacity cannot hold the configured overlap.

    Raises:
        ValueError: If the capacity is not positive or does not exceed the
            requested overlap.
    """
    if chunk_size <= 0:
        raise ValueError(f"CHUNKING__MARKDOWN_CHUNK_SIZE ({chunk_size}) must be greater than zero.")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"CHUNKING__CHUNK_OVERLAP ({chunk_overlap}) must be less than "
            f"CHUNKING__MARKDOWN_CHUNK_SIZE ({chunk_size})."
        )


def _require_content_budget(
    capacity: int,
    *,
    chunk_size: int,
    chunk_overlap: int,
    header_path: str,
    prefix_tokens: int,
) -> None:
    """Fail when a reserved heading prefix leaves no workable content budget.

    Raises:
        ValueError: If the reduced capacity cannot hold the requested
            overlap, naming the settings that produced the combination.
    """
    if capacity > 0 and capacity > chunk_overlap:
        return
    reserved = (
        f"Heading prepend reserves {prefix_tokens} of {chunk_size} tokenizer "
        f"units for the heading path {header_path!r}, leaving {capacity} unit(s) "
        f"for chunk text."
    )
    shortfall = (
        "That leaves no room for the text itself."
        if capacity <= 0
        else f"That budget cannot hold the requested CHUNKING__CHUNK_OVERLAP of {chunk_overlap}."
    )
    raise ValueError(
        f"{reserved} {shortfall} Raise CHUNKING__MARKDOWN_CHUNK_SIZE, lower "
        f"CHUNKING__CHUNK_OVERLAP, or disable CHUNKING__MARKDOWN_HEADING_PREPEND."
    )


def _verify_final_size(
    tokenizer: Any,
    text: str,
    header_path: str,
    *,
    heading_prepend: bool,
    chunk_size: int,
) -> None:
    """Check one finalised chunk against the configured token cap.

    Raises:
        ValueError: If the chunk text, including any heading prefix that
            will be prepended, exceeds the cap.
    """
    finalised = f"[{header_path}] {text}" if heading_prepend and header_path else text
    count = _token_count(tokenizer, finalised)
    if count <= chunk_size:
        return
    raise ValueError(
        f"Markdown chunk is {count} tokenizer units once finalised for "
        f"embedding, above the CHUNKING__MARKDOWN_CHUNK_SIZE cap of "
        f"{chunk_size}. Raise CHUNKING__MARKDOWN_CHUNK_SIZE or disable "
        f"CHUNKING__MARKDOWN_HEADING_PREPEND for this source."
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
    """Fit one source chunk after reserving its heading prefix.

    Raises:
        ValueError: If the chunk cannot be reduced below the finalised cap.
    """
    header_path = _header_path_at(headings, offset)
    prefix = f"[{header_path}] " if header_path else ""
    if _token_count(tokenizer, prefix + chunk) <= chunk_size:
        return [(offset, chunk, header_path)]

    prefix_tokens = _token_count(tokenizer, prefix)
    capacity = chunk_size - prefix_tokens
    _require_content_budget(
        capacity,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        header_path=header_path,
        prefix_tokens=prefix_tokens,
    )
    if depth >= _MAX_FIT_DEPTH:
        raise ValueError(
            f"Markdown chunk under heading path {header_path!r} did not fit "
            f"the CHUNKING__MARKDOWN_CHUNK_SIZE cap of {chunk_size} tokenizer "
            f"units after {_MAX_FIT_DEPTH} splitting rounds. Raise "
            f"CHUNKING__MARKDOWN_CHUNK_SIZE or disable "
            f"CHUNKING__MARKDOWN_HEADING_PREPEND for this source."
        )

    children = _split_smaller(
        markdown_splitter,
        tokenizer,
        chunk,
        capacity=capacity,
        overlap=chunk_overlap,
    )
    if not children:
        raise ValueError(
            f"Markdown chunk under heading path {header_path!r} cannot be split "
            f"below {capacity} tokenizer unit(s) while keeping the requested "
            f"CHUNKING__CHUNK_OVERLAP of {chunk_overlap}. Raise "
            f"CHUNKING__MARKDOWN_CHUNK_SIZE, lower CHUNKING__CHUNK_OVERLAP, or "
            f"disable CHUNKING__MARKDOWN_HEADING_PREPEND."
        )

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


def _split_smaller(
    splitter_type: Any,
    tokenizer: Any,
    chunk: str,
    *,
    capacity: int,
    overlap: int,
) -> list[tuple[int, str]]:
    """Split one chunk into strictly smaller pieces at the requested overlap.

    The capacity shrinks until the splitter makes progress, so a chunk that
    already fits the reduced capacity but still overflows once its heading
    prefix is added is broken up instead of escaping oversized. The requested
    overlap is never reduced.

    Args:
        splitter_type: The ``MarkdownSplitter`` class.
        tokenizer: Resolved embedding tokenizer.
        chunk: Source chunk text to split.
        capacity: Starting capacity in tokenizer units.
        overlap: Requested overlap in tokenizer units, held constant.

    Returns:
        Offset/text pairs strictly smaller than *chunk*, or an empty list
        when no capacity above the requested overlap makes progress.
    """
    while capacity > overlap:
        splitter = _markdown_splitter(splitter_type, tokenizer, capacity, overlap)
        children = splitter.chunk_indices(chunk)
        if len(children) > 1 or (children and children[0][1] != chunk):
            return children
        capacity -= 1
    return []


def _heading_positions(text: str) -> list[tuple[int, int, str]]:
    """Return ATX heading positions, levels, and normalised titles.

    Lines inside fenced code blocks are code, not document structure, so
    they never contribute a heading.

    Args:
        text: Source Markdown.

    Returns:
        One ``(offset, level, title)`` entry per heading, in source order.
    """
    positions: list[tuple[int, int, str]] = []
    offset = 0
    fence: tuple[str, int] | None = None
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        fence = _fence_state(fence, line)
        if fence is None:
            match = _ATX_HEADING.match(line)
            if match:
                title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
                positions.append((offset, len(match.group(1)), title))
        offset += len(raw_line)
    return positions


def _fence_state(fence: tuple[str, int] | None, line: str) -> tuple[str, int] | None:
    """Return the fenced-code state after one Markdown line.

    Args:
        fence: The open fence marker and its length, or ``None`` outside a
            fenced block.
        line: One source line without its newline.

    Returns:
        The fence state that applies to the next line.
    """
    match = _CODE_FENCE.match(line)
    if match is None:
        return fence
    marker = match.group("fence")
    info = match.group("info")
    if fence is None:
        if marker[0] == "`" and "`" in info:
            return None
        return (marker[0], len(marker))
    character, length = fence
    if marker[0] == character and len(marker) >= length and not info.strip():
        return None
    return fence


def _header_path_at(headings: list[tuple[int, int, str]], offset: int) -> str:
    """Return the ATX heading chain enclosing a source character offset.

    Each ancestry entry keeps its heading level, so a skipped level makes
    the next same-or-shallower heading a sibling rather than a child.

    Args:
        headings: Heading positions from :func:`_heading_positions`.
        offset: Character offset of the chunk in the source Markdown.

    Returns:
        A slash-delimited heading path, or an empty string before the first
        heading.
    """
    chain: list[tuple[int, str]] = []
    for heading_offset, level, title in headings:
        if heading_offset > offset:
            break
        while chain and chain[-1][0] >= level:
            chain.pop()
        chain.append((level, title))
    return f"/{'/'.join(title for _, title in chain)}/" if chain else ""


def _token_count(tokenizer: Any, text: str) -> int:
    """Count tokens without allowing tokenizer truncation to affect sizing."""
    return len(tokenizer.encode(text).ids)
