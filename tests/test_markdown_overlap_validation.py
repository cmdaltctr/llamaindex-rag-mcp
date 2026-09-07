"""OpenSpec: improve-rag-input-quality-5, task 3.5a."""

from __future__ import annotations

import pytest


def _settings_with_markdown_overlap(chunk_overlap: int, markdown_chunk_size: int):
    """Build resolved settings with explicit Markdown splitter values."""
    from omrg.config import Settings
    from omrg.core.chunking.settings import ChunkingSettings

    return Settings(
        _env_file=None,
        pdf_reader="pypdf",
        chunking=ChunkingSettings(
            chunk_overlap=chunk_overlap,
            markdown_chunk_size=markdown_chunk_size,
        ),
    )


def test_settings_to_effective_accepts_overlap_below_markdown_capacity() -> None:
    """Task 3.5a: overlap below the Markdown capacity reaches core settings."""
    from omrg.compose import settings_to_effective

    effective = settings_to_effective(_settings_with_markdown_overlap(127, 128))

    assert effective.chunking.chunk_overlap == 127
    assert effective.chunking.markdown_chunk_size == 128


@pytest.mark.parametrize(
    ("chunk_overlap", "markdown_chunk_size"),
    [(128, 128), (129, 128)],
    ids=["equal-to-capacity", "greater-than-capacity"],
)
def test_settings_to_effective_rejects_markdown_overlap_at_or_above_capacity(
    chunk_overlap: int,
    markdown_chunk_size: int,
) -> None:
    """Task 3.5a: invalid overlap fails early and names both settings."""
    from omrg.compose import settings_to_effective

    settings = _settings_with_markdown_overlap(chunk_overlap, markdown_chunk_size)

    with pytest.raises(ValueError) as error:
        settings_to_effective(settings)

    assert "CHUNKING__CHUNK_OVERLAP" in str(error.value)
    assert "CHUNKING__MARKDOWN_CHUNK_SIZE" in str(error.value)
