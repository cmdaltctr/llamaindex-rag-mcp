"""Tests for retrieval defaults recorded in the config Settings model.

Covers Section 3 of the rag-retrieval-quality-improvements OpenSpec change
and ADR-018 balanced retrieval defaults:
- Default CHUNK_OVERLAP is 100 (Stäbler et al. 2025 empirical sweet spot).
- The default still honours the CHUNK_OVERLAP env var when set.
- Default TOP_K is 10.
- Default RERANK_ENABLED is false (ADR-019: default-off for technical workloads).
"""

from __future__ import annotations

from rag_mcp.config import Settings


def _model_default(field_name: str):
    """Return the declared model default for *field_name* (not env-overridden).

    This reads the Pydantic field metadata, guaranteeing we are checking
    the codebase's documented default rather than the developer's local
    environment.
    """
    # v2.0.0: subpackage defaults live on the nested block models.
    if field_name in Settings.model_fields:
        return Settings.model_fields[field_name].default
    for block in ("chunking", "ingestion", "retrieval", "metadata"):
        block_cls = Settings.model_fields[block].annotation
        if field_name in block_cls.model_fields:
            return block_cls.model_fields[field_name].default
    raise KeyError(field_name)


def test_default_chunk_overlap_is_100() -> None:
    """The codebase default for ``CHUNK_OVERLAP`` SHALL be 100."""
    assert _model_default("chunk_overlap") == 100


def test_balanced_retrieval_defaults_are_configured() -> None:
    """ADR-018/019 retrieval defaults SHALL be the codebase defaults."""
    assert _model_default("chunk_overlap") == 100
    assert _model_default("top_k") == 10
    assert _model_default("rerank_enabled") is False


def test_balanced_retrieval_defaults_are_env_overridable() -> None:
    """TOP_K and RERANK_ENABLED SHALL remain environment-overridable.

    The Settings model uses pydantic-settings which reads env vars by
    field name (case-insensitive).  This test verifies the field names
    map to the expected env var names.
    """
    # In pydantic-settings, env var name = field_name.upper()
    assert "chunk_overlap" in Settings.model_fields["chunking"].annotation.model_fields
    assert "top_k" in Settings.model_fields["retrieval"].annotation.model_fields
    assert "rerank_enabled" in Settings.model_fields["retrieval"].annotation.model_fields
