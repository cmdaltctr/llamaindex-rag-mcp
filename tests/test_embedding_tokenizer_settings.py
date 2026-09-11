"""OpenSpec: improve-rag-input-quality-5, task 3.2."""

from __future__ import annotations

import pytest


def test_tokenizer_fields_default_to_the_promoted_qwen_identity() -> None:
    """Task 5.5 promotion (exp 25 PASS, ADR-063): the packaged default is
    the evaluated Qwen tokenizer on both pure embedding models, and the
    frozen block still rejects mutation."""
    from pydantic import ValidationError

    from omrg.core.settings import EmbeddingBlock, EmbeddingSettings

    settings = EmbeddingSettings()
    block = EmbeddingBlock()

    assert settings.tokenizer_model == "Qwen/Qwen3-Embedding-4B"
    assert settings.tokenizer_revision == "5cf2132abc99cad020ac570b19d031efec650f2b"
    assert block.tokenizer_model == "Qwen/Qwen3-Embedding-4B"
    assert block.tokenizer_revision == "5cf2132abc99cad020ac570b19d031efec650f2b"

    with pytest.raises(ValidationError):
        block.tokenizer_model = "mutated-tokenizer"


def test_empty_tokenizer_environment_opts_back_into_legacy_chunking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The promotion stays operator-reversible: explicit empty environment
    values return both models to the legacy character-budgeted path."""
    from omrg.compose import settings_to_effective
    from omrg.config import Settings

    monkeypatch.setenv("EMBEDDING__TOKENIZER_MODEL", "")
    monkeypatch.setenv("EMBEDDING__TOKENIZER_REVISION", "")

    configured = Settings(_env_file=None, pdf_reader="pypdf")
    assert configured.embedding.tokenizer_model == ""
    assert configured.embedding.tokenizer_revision == ""

    effective = settings_to_effective(configured)
    assert effective.embedding.tokenizer_model == ""
    assert effective.embedding.tokenizer_revision == ""


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
