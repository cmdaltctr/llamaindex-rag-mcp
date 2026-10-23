"""Code chunking strategy using LlamaIndex's CodeSplitter.

Uses tree-sitter function/class boundaries for semantically coherent chunks.
The CodeSplitter API is line/character based in LlamaIndex 0.14.x, while the
SentenceSplitter fallback is token based; the two unit systems are kept
explicitly separate here.  Fallback remains available for malformed or
unsupported code, but it is observable on the returned list-like result.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from llama_index.core.node_parser import SentenceSplitter

logger = logging.getLogger(__name__)


class CodeChunkResult(list):
    """List-like code chunk result with requested/effective strategy diagnostics."""

    def __init__(
        self,
        nodes=(),
        *,
        effective_strategy: str,
        fallback_reason: str | None = None,
    ) -> None:
        super().__init__(nodes)
        self.chunk_strategy_requested = "code"
        self.chunk_strategy_effective = effective_strategy
        self.fallback_reason = fallback_reason


async def chunk_code_file_async(
    file_path: Path,
    language: str,
    fallback_chunk_size: int,
    fallback_chunk_overlap: int,
    content_type: str | None,
    *,
    code_chunk_lines: int = 40,
    code_chunk_lines_overlap: int = 15,
    code_max_chars: int = 1500,
) -> CodeChunkResult:
    """Chunk a code file using LlamaIndex's AST-aware ``CodeSplitter``.

    ``CodeSplitter`` uses lines plus a character ceiling.  The generic
    document ``fallback_chunk_size`` / ``fallback_chunk_overlap`` values are
    tokenizer units and are used only if AST-aware splitting fails.

    Args:
        file_path: Path to the code file.
        language: Tree-sitter language identifier (for example ``"python"``).
        fallback_chunk_size: SentenceSplitter fallback size in tokens.
        fallback_chunk_overlap: SentenceSplitter fallback overlap in tokens.
        content_type: Magika content-type string for metadata, when known.
        code_chunk_lines: Target number of code lines per AST chunk.
        code_chunk_lines_overlap: Code-line overlap between adjacent chunks.
        code_max_chars: Maximum characters in one AST-aware code chunk.

    Returns:
        A list-like :class:`CodeChunkResult` whose nodes carry source metadata
        and whose attributes record whether AST-aware splitting actually ran.
    """
    from llama_index.core.node_parser import CodeSplitter

    def _read_and_split() -> list:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        splitter = CodeSplitter(
            language=language,
            chunk_lines=code_chunk_lines,
            chunk_lines_overlap=code_chunk_lines_overlap,
            max_chars=code_max_chars,
        )
        from llama_index.core import Document

        doc = Document(text=content, metadata={"file_path": str(file_path)})
        return splitter.get_nodes_from_documents([doc])

    fallback_reason: str | None = None
    effective_strategy = "code"
    try:
        nodes = await asyncio.to_thread(_read_and_split)
    except Exception as exc:
        fallback_reason = f"{type(exc).__name__}: {exc}"
        effective_strategy = "sentence"
        logger.warning(
            "Code chunking fallback for %s: requested=code effective=sentence "
            "language=%s reason=%s",
            file_path.name,
            language,
            fallback_reason,
        )
        content = file_path.read_text(encoding="utf-8", errors="replace")
        from llama_index.core import Document

        splitter = SentenceSplitter(
            chunk_size=fallback_chunk_size,
            chunk_overlap=fallback_chunk_overlap,
        )
        doc = Document(text=content, metadata={"file_path": str(file_path)})
        nodes = splitter.get_nodes_from_documents([doc])

    for node in nodes:
        if content_type:
            node.metadata.setdefault("content_type", content_type)
        node.metadata.setdefault("file_path", str(file_path))

    return CodeChunkResult(
        nodes,
        effective_strategy=effective_strategy,
        fallback_reason=fallback_reason,
    )
