"""Whole-file config chunking strategy.

Config files (YAML, JSON, TOML, INI) are small enough to be a single
chunk.  Extracted from the original ``ingestion.py`` monolith as part
of Phase 1.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def chunk_config_file(
    file_path: Path,
    content_type: str,
) -> list:
    """Chunk a config file as a single whole-file chunk.

    Config files (YAML, JSON, TOML, INI) are small enough to be a single chunk.

    Args:
        file_path: Path to the config file.
        content_type: Magika content-type string for metadata.

    Returns:
        List containing a single LlamaIndex Node with the full file content.
    """
    from llama_index.core.schema import TextNode

    content = file_path.read_text(encoding="utf-8", errors="replace")
    node = TextNode(
        text=content,
        metadata={
            "content_type": content_type,
            "file_path": str(file_path),
            "file_name": file_path.name,
        },
    )
    return [node]
