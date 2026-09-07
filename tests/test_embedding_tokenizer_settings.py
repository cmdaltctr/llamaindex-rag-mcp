"""OpenSpec: improve-rag-input-quality-5, task 3.2."""

from __future__ import annotations

import pytest


def test_tokenizer_fields_default_to_empty_on_settings_and_frozen_block() -> None:
    """Task 3.2: both pure embedding models keep tokenizer selection opt-in."""
    from pydantic import ValidationError

    from omrg.core.settings import EmbeddingBlock, EmbeddingSettings

    settings = EmbeddingSettings()
    block = EmbeddingBlock()

    assert settings.tokenizer_model == ""
    assert settings.tokenizer_revision == ""
    assert block.tokenizer_model == ""
    assert block.tokenizer_revision == ""

    with pytest.raises(ValidationError):
        block.tokenizer_model = "mutated-tokenizer"


def test_tokenizer_fields_resolve_from_nested_environment_and_effective_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 3.2: nested tokenizer environment values reach core settings."""
    from omrg.compose import settings_to_effective
    from omrg.config import Settings

    monkeypatch.setenv("EMBEDDING__TOKENIZER_MODEL", "Qwen/Qwen3-Embedding-4B")
    monkeypatch.setenv("EMBEDDING__TOKENIZER_REVISION", "test-revision")

    configured = Settings(_env_file=None, pdf_reader="pypdf")
    assert configured.embedding.tokenizer_model == "Qwen/Qwen3-Embedding-4B"
    assert configured.embedding.tokenizer_revision == "test-revision"

    effective = settings_to_effective(configured)
    assert effective.embedding.tokenizer_model == "Qwen/Qwen3-Embedding-4B"
    assert effective.embedding.tokenizer_revision == "test-revision"
