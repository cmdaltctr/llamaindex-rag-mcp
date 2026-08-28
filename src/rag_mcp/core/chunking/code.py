"""Code chunking strategy using LlamaIndex's CodeSplitter.

Uses tree-sitter function/class boundaries for semantically coherent
chunks. Falls back to SentenceSplitter if CodeSplitter fails.
Extracted from the original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from llama_index.core.node_parser import SentenceSplitter

logger = logging.getLogger(__name__)


async def chunk_code_file_async(
    file_path: Path,
    language: str,
    chunk_size: int,
    chunk_overlap: int,
    content_type: str,
) -> list:
    """Chunk a code file using LlamaIndex's CodeSplitter.

    Uses tree-sitter function/class boundaries for semantically coherent
    chunks. Falls back to SentenceSplitter if CodeSplitter fails.

    Args:
        file_path: Path to the code file.
        language: Tree-sitter language identifier (e.g., "python").
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        content_type: Magika content-type string for metadata.

    Returns:
        List of LlamaIndex Node objects with content_type metadata.
    """
    from llama_index.core.node_parser import CodeSplitter

    def _read_and_split() -> list:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        splitter = CodeSplitter(
            language=language,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        from llama_index.core import Document
        doc = Document(text=content, metadata={"file_path": str(file_path)})
        return splitter.get_nodes_from_documents([doc])

    try:
        nodes = await asyncio.to_thread(_read_and_split)
    except Exception as exc:
        logger.warning(
            "CodeSplitter failed for %s (language=%s): %s — falling back to SentenceSplitter",
            file_path.name, language, exc,
        )
        # Fall back to SentenceSplitter.
        content = file_path.read_text(encoding="utf-8", errors="replace")
        from llama_index.core import Document
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        doc = Document(text=content, metadata={"file_path": str(file_path)})
        nodes = splitter.get_nodes_from_documents([doc])

    for node in nodes:
        node.metadata.setdefault("content_type", content_type)
        node.metadata.setdefault("file_path", str(file_path))

    return nodes
