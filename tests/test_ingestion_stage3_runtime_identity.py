"""Focused Stage 3A regression for process-scoped embedding identity."""

from __future__ import annotations

import pytest

from omrg.core.ingestion import source_state
from omrg.core.settings import EffectiveSettings, MetadataBlock


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


def test_index_identity_tracks_metadata_budgets() -> None:
    """Timeouts and retry budgets must invalidate the identity.

    A timeout or retry change flips real ingestions between degraded
    fallback metadata and successful extraction, and extracted metadata
    participates in embedded text. If these budgets stay out of the
    identity, a source indexed under a degraded budget is skipped as
    current after the operator raises the budget — permanently pinning
    the degraded output. Spec: async-ingestion, complete index-shaping
    identity.
    """
    base = EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))
    raised = base.model_copy(
        update={
            "metadata": MetadataBlock(
                extraction_mode="disabled",
                classify_timeout=120.0,
            )
        }
    )
    more_attempts = base.model_copy(
        update={
            "metadata": MetadataBlock(
                extraction_mode="disabled",
                classify_max_attempts=7,
            )
        }
    )
    longer_pipeline = base.model_copy(
        update={
            "metadata": MetadataBlock(
                extraction_mode="disabled",
                pipeline_timeout=600.0,
            )
        }
    )
    provider_override = base.model_copy(
        update={
            "metadata": MetadataBlock(
                extraction_mode="disabled",
                ollama_pipeline_timeout_override=240.0,
            )
        }
    )

    def identity(settings: EffectiveSettings) -> str:
        return source_state.build_index_identity(
            settings,
            content_type="text/plain",
            chunk_size=512,
            chunk_overlap=100,
        )

    baseline = identity(base)
    assert baseline != identity(raised)
    assert baseline != identity(more_attempts)
    assert baseline != identity(longer_pipeline)
    assert baseline != identity(provider_override)
