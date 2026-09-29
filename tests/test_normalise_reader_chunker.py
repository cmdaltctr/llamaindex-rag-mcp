"""PDF-only normalisation at the document-backend boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from llama_index.core import Document

from omrg.core.ingestion.backends.orchestrator import BackendRead
from omrg.core.ingestion.chunker import read_and_chunk_file_async


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "enabled", "structured", "content_type", "source", "expected"),
    [
        ("sample.pdf", True, False, None, "<u>HEADER</u>", "HEADER"),
        ("sample.pdf", False, False, None, "<u>HEADER</u>", "<u>HEADER</u>"),
        (
            "sample.md",
            True,
            False,
            None,
            '<div align="center"><img src="logo.png"></div>',
            '<div align="center"><img src="logo.png"></div>',
        ),
        ("sample.bin", True, False, "application/pdf", "<u>HEADER</u>", "HEADER"),
        ("sample.pdf", True, True, None, "<u>HEADER</u>", "HEADER"),
    ],
)
async def test_normalisation_precedes_both_chunking_paths(
    monkeypatch: pytest.MonkeyPatch,
    effective_settings,
    name: str,
    enabled: bool,
    structured: bool,
    content_type: str | None,
    source: str,
    expected: str,
) -> None:
    from omrg.core.chunking import sentence
    from omrg.core.ingestion import chunker
    from omrg.core.metadata import extractor

    async def read(*args, **kwargs) -> BackendRead:
        return BackendRead([Document(text=source)], structured, "plain")

    seen: list[str] = []

    async def metadata(text, *args, **kwargs):
        seen.append(text)
        return {}, False

    monkeypatch.setattr(chunker, "read_document", read)
    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", metadata)
    monkeypatch.setattr(sentence, "_split_documents_sync", lambda docs, *args: docs)
    monkeypatch.setattr(sentence, "_postprocess_markdown_nodes", lambda docs, *args: docs)
    settings = effective_settings(normalise_reader_output=enabled)
    nodes = await read_and_chunk_file_async(
        Path(name), content_type=content_type, settings=settings, markdown_chunking=object()
    )
    assert nodes[0].text == expected
    assert seen == ([] if structured else [expected])
