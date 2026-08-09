"""Metadata extraction settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the metadata
subpackage.  Consumed by the root ``Settings`` resolver in
``rag_mcp.config``.  MUST NOT import from ``config``, ``compose``, or
any other ``core/`` module (enforced by import-linter).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetadataSettings(BaseModel):
    """Configuration knobs for document metadata extraction.

    Defaults mirror the pre-refactor ``config.py`` values exactly.
    """

    # Declared after the docstring: a string literal following an
    # assignment is a bare expression, not ``__doc__``.
    model_config = ConfigDict(extra="forbid")

    # Metadata extraction mode: "disabled", "keyword", "local",
    # "llamaindex".  "ollama" is mapped to "local" for back-compat.
    extraction_mode: str = "llamaindex"

    # Optional JSON string of keyword rules overriding the built-in set.
    keyword_rules: str | None = None

    # Chat model used for Ollama-based classification.
    ollama_classify_model: str = "qwen3:0.6b"

    # Bounded retry count for metadata classification (all backends).
    # Rejected rather than clamped when non-positive: silently rewriting an
    # operator's 0 to 1 hides the misconfiguration.
    classify_max_attempts: int = Field(default=3, gt=0)

    # Per-attempt timeout (seconds) for metadata classification (all backends).
    # Non-positive values would reach httpx as a nonsensical deadline.
    classify_timeout: float = Field(default=30.0, gt=0)

    # Timeout (seconds) for the llamaindex extraction pipeline, which runs
    # three extractors over every chunk rather than asking one classification
    # question.  Deliberately separate from ``classify_timeout``: that path
    # retries, so it wants a short deadline and a fast failure, while this one
    # makes a single long attempt.  Merging them would force classification to
    # wait 3x this value before falling back.  Was a hardcoded 180.0 in two
    # call sites before it was named.
    pipeline_timeout: float = Field(default=180.0, gt=0)

    # Per-provider overrides for the two shared timeouts above.  ``None``
    # means "unset, use the shared value" — see the resolvers in
    # ``core/metadata/_common.py``.  A machine running a slow local model
    # wants a longer pipeline budget without loosening the fast-fail
    # classify budget, and vice versa, so each timeout gets its own set
    # of three overrides rather than sharing one.  A float default would
    # make "did the operator set this?" unanswerable.
    llamacpp_classify_timeout_override: float | None = Field(default=None, gt=0)
    ollama_classify_timeout_override: float | None = Field(default=None, gt=0)
    openrouter_classify_timeout_override: float | None = Field(default=None, gt=0)
    llamacpp_pipeline_timeout_override: float | None = Field(default=None, gt=0)
    ollama_pipeline_timeout_override: float | None = Field(default=None, gt=0)
    openrouter_pipeline_timeout_override: float | None = Field(default=None, gt=0)

    # Taxonomy mode for metadata classification (Phase 4 profiles).
    # "category" uses the ADR-013 hybrid category taxonomy (documents profile).
    # "file_type" classifies by Magika-detected file type (codebase profile).
    taxonomy_mode: str = "category"
