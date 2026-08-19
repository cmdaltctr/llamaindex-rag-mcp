"""Focused Stage 3A regression for process-scoped embedding identity."""

from __future__ import annotations

import pytest

from rag_mcp.core.ingestion import source_state
from rag_mcp.core.settings import EffectiveSettings, MetadataBlock


def test_index_identity_tracks_actual_process_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing the runtime embedder must invalidate an otherwise equal source."""
    settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))

    monkeypatch.setattr(
        source_state,
        "_runtime_embedding_identity",
        lambda: {"class": "tests.Embedder", "model": "runtime-a"},
    )
    first = source_state.build_index_identity(
        settings,
        content_type="text/plain",
        chunk_size=512,
        chunk_overlap=100,
    )

    monkeypatch.setattr(
        source_state,
        "_runtime_embedding_identity",
        lambda: {"class": "tests.Embedder", "model": "runtime-b"},
    )
    second = source_state.build_index_identity(
        settings,
        content_type="text/plain",
        chunk_size=512,
        chunk_overlap=100,
    )

    assert first != second
