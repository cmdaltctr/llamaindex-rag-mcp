"""Metadata extraction settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the metadata
subpackage.  Consumed by the root ``Settings`` resolver in
``rag_mcp.config``.  MUST NOT import from ``config``, ``compose``, or
any other ``core/`` module (enforced by import-linter).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class MetadataSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """Configuration knobs for document metadata extraction.

    Defaults mirror the pre-refactor ``config.py`` values exactly.
    """

    # Metadata extraction mode: "disabled", "keyword", "local",
    # "llamaindex".  "ollama" is mapped to "local" for back-compat.
    extraction_mode: str = "llamaindex"

    # Optional JSON string of keyword rules overriding the built-in set.
    keyword_rules: str | None = None

    # Chat model used for Ollama-based classification.
    ollama_classify_model: str = "qwen3:0.6b"

    # Bounded retry count for metadata classification (all backends).
    classify_max_attempts: int = 3

    # Per-attempt timeout (seconds) for metadata classification (all backends).
    classify_timeout: float = 30.0

    @field_validator("classify_max_attempts")
    @classmethod
    def _clamp_max_attempts(cls, v: int) -> int:
        """Ensure at least one classification attempt is made."""
        return max(1, v)

    # Taxonomy mode for metadata classification (Phase 4 profiles).
    # "category" uses the ADR-013 hybrid category taxonomy (documents profile).
    # "file_type" classifies by Magika-detected file type (codebase profile).
    taxonomy_mode: str = "category"
