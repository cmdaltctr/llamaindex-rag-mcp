"""Metadata extraction settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the metadata
subpackage.  Consumed by the root ``Settings`` resolver in
``rag_mcp.config``.  MUST NOT import from ``config``, ``compose``, or
any other ``core/`` module (enforced by import-linter).
"""

from __future__ import annotations

from pydantic import BaseModel


class MetadataSettings(BaseModel):
    """Configuration knobs for document metadata extraction.

    Defaults mirror the pre-refactor ``config.py`` values exactly.
    """

    # Metadata extraction mode: "disabled", "keyword", "local",
    # "llamaindex".  "ollama" is mapped to "local" for back-compat.
    metadata_extraction_mode: str = "llamaindex"

    # Optional JSON string of keyword rules overriding the built-in set.
    metadata_keyword_rules: str | None = None

    # Chat model used for Ollama-based classification.
    ollama_classify_model: str = "qwen3:0.6b"

    # Bounded retry count for Ollama metadata extraction.
    ollama_classify_max_attempts: int = 3

    # Per-attempt timeout (seconds) for Ollama metadata extraction.
    ollama_classify_timeout: float = 30.0
