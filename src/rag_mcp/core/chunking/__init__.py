"""Chunking strategy subpackage.

Provides the four chunking strategies (code, markdown, sentence, config)
used by the ingestion pipeline.  Extracted from the original
``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

from .code import chunk_code_file_async
from .config_file import chunk_config_file
from .markdown import (
    apply_heading_prepend,
    drop_small_markdown_chunks,
    ensure_heading_metadata,
)
from .sentence import chunk_sentence_file_async

__all__ = [
    "chunk_code_file_async",
    "chunk_config_file",
    "chunk_sentence_file_async",
    "ensure_heading_metadata",
    "apply_heading_prepend",
    "drop_small_markdown_chunks",
]
