"""Chunking settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the chunking subpackage.
This model is consumed by the root ``Settings`` resolver in
``rag_mcp.config``.  It MUST NOT import from ``config``, ``compose``, or
any other ``core/`` module (enforced by import-linter).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans using the legacy ``.lower() == "true"`` semantics.

    Only the literal string ``"true"`` (case-insensitive) is ``True``.
    Every other string — including ``"1"``, ``"yes"``, ``"on"`` — is
    ``False``.  This matches the pre-refactor ``os.getenv`` parsing.
    """
    if isinstance(value, str):
        return value.lower() == "true"
    return value


# Drop-in replacement for ``bool`` that preserves legacy env-var parsing.
LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]


class ChunkingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """Configuration knobs for the document chunking pipeline.

    Defaults mirror the pre-refactor ``config.py`` values unless the setting
    is explicitly code-specific.  Sentence and code splitters deliberately
    use separate unit vocabularies so a token count can never be passed to a
    line/character API by accident.
    """

    # SentenceSplitter chunk size in tokenizer units (tokens).
    chunk_size: int = 512

    # SentenceSplitter overlap in tokenizer units (tokens). Raised from
    # 64 → 100 after Stäbler et al. 2025 (see ADR-018).
    chunk_overlap: int = 100

    # CodeSplitter parameters.  LlamaIndex 0.14.x exposes code chunking in
    # lines plus an explicit character ceiling; these are NOT token counts.
    code_chunk_lines: int = 40
    code_chunk_lines_overlap: int = 15
    code_max_chars: int = 1500

    # Markdown-specific SentenceSplitter chunk size (tokens, Experiment 6c).
    # Non-markdown document files continue to use ``chunk_size``.
    markdown_chunk_size: int = 1024

    # Experimental: prepend heading text to each markdown chunk.
    markdown_heading_prepend: LegacyBool = False

    # Experimental: minimum chunk size as a fraction of ``markdown_chunk_size``.
    # Chunks below this fraction are merged with neighbours.
    markdown_min_chunk_fraction: float = 0.0

    # Fallback chunking strategy for ambiguous file types (Phase 4 profiles).
    # Known file types always use content-type dispatch (code → CodeSplitter,
    # config → whole-file, etc.).  This value is the strategy name used when
    # Magika cannot classify the file confidently.  Documents profile uses
    # "markdown"; codebase profile uses "code".
    strategy_fallback: str = "markdown"
