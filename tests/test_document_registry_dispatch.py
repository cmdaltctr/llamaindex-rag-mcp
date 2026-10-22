"""Production document dispatch honours the chunking registry.

Covers the ``repair-modular-core-boundaries`` change, tasks 2.1, 2.2 and
the ingestion half of 3.1 (``modular-core-extraction`` spec: "Registered
replacement reaches production dispatch", "Reader-produced Markdown
remains intact", "Metadata degradation survives dispatch").

The sentinel is registered through the real chunking registry, so a
chunker branch that calls private sentence helpers directly fails these
tests. Reads, metadata and store writes are faked; no model, network or
real vector store is used.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Document
from llama_index.core.schema import TextNode

from omrs.core.chunking import registry as chunking_registry
from omrs.core.ingestion import chunker
from omrs.core.ingestion.backends.orchestrator import BackendRead

SENTINEL_TEXT = "SENTINEL-STRATEGY-OUTPUT"
_calls: list[dict[str, Any]] = []


async def _sentinel_sentence_strategy(
    documents: list,
    file_path: str,
    is_markdown: bool,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: object | None = None,
    markdown_chunking: object | None = None,
) -> list:
    """Record the call and return one recognisable node."""
    _calls.append(
        {
            "documents": documents,
            "file_path": file_path,
            "is_markdown": is_markdown,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "settings": settings,
            "markdown_chunking": markdown_chunking,
        }
    )
    return [TextNode(text=SENTINEL_TEXT, metadata={})]


@pytest.fixture
def sentinel_strategy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Register the sentinel as the ``sentence`` strategy via the registry."""
    _calls.clear()
    monkeypatch.setitem(
        chunking_registry._registry, "sentence", f"{__name__}:_sentinel_sentence_strategy"
    )
    monkeypatch.delitem(chunking_registry._cache, "sentence", raising=False)
    yield _calls
    chunking_registry._cache.pop("sentence", None)


def _fake_metadata(captured: list[dict[str, Any]], degraded: bool = False):
    async def _extract(text, filename, settings=None, *args, **kwargs):
        captured.append({"filename": filename, "settings": settings, **kwargs})
        return {"category": "fake", "keywords": ["a", "b"]}, degraded

    return _extract


# (file name, structured, reader text format, expected Markdown declaration)
_BRANCHES = [
    ("plain.txt", True, "plain", False),
    ("notes.md", True, "plain", True),
    ("plain.txt", False, "plain", False),
    ("notes.md", False, "plain", True),
    ("scan.pdf", False, "markdown", True),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "structured", "text_format", "is_markdown"), _BRANCHES)
async def test_both_document_branches_invoke_registered_sentence_strategy(
    monkeypatch: pytest.MonkeyPatch,
    effective_settings,
    sentinel_strategy,
    name: str,
    structured: bool,
    text_format: str,
    is_markdown: bool,
) -> None:
    """Scenario: registered replacement reaches production dispatch."""
    from omrs.core.metadata import extractor

    documents = [Document(text="# Heading\n\nBody text.")]

    async def _read(*args, **kwargs) -> BackendRead:
        return BackendRead(documents, structured, text_format)

    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(chunker, "read_document", _read)
    monkeypatch.setattr(
        extractor, "extract_metadata_with_status_async", _fake_metadata(captured, degraded=True)
    )
    settings = effective_settings(chunk_size=300, chunk_overlap=20, markdown_chunk_size=700)
    resolution = object()

    nodes = await chunker.read_and_chunk_file_async(
        Path(name),
        content_type="text/plain",
        settings=settings,
        markdown_chunking=resolution,
    )

    assert [node.text for node in nodes] == [SENTINEL_TEXT]
    assert len(sentinel_strategy) == 1
    call = sentinel_strategy[0]
    assert call["documents"] is documents
    assert call["file_path"] == name
    assert call["is_markdown"] is is_markdown
    assert call["chunk_size"] == (700 if is_markdown else 300)
    assert call["chunk_overlap"] == 20
    assert call["settings"] is settings
    assert call["markdown_chunking"] is (resolution if is_markdown else None)
    assert nodes[0].metadata["content_type"] == "text/plain"
    if structured:
        assert captured == []
    else:
        # Scenario: metadata degradation survives dispatch.
        assert nodes.metadata_degraded is True
        assert nodes[0].metadata["category"] == "fake"
        assert nodes[0].metadata["keywords"] == "a, b"


@pytest.mark.asyncio
async def test_chunk_overrides_reach_registered_strategy(
    monkeypatch: pytest.MonkeyPatch, effective_settings, sentinel_strategy
) -> None:
    """Explicit chunk overrides travel into the registered callable."""

    async def _read(*args, **kwargs) -> BackendRead:
        return BackendRead([Document(text="body")], True, "plain")

    monkeypatch.setattr(chunker, "read_document", _read)
    await chunker.read_and_chunk_file_async(
        Path("plain.txt"), chunk_size=123, chunk_overlap=7, settings=effective_settings()
    )
    assert sentinel_strategy[0]["chunk_size"] == 123
    assert sentinel_strategy[0]["chunk_overlap"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [True, False])
async def test_markdown_postprocessing_runs_exactly_once(
    monkeypatch: pytest.MonkeyPatch, effective_settings, structured: bool
) -> None:
    """Scenario: Markdown post-processing is applied exactly once per file."""
    from omrs.core.chunking import sentence
    from omrs.core.metadata import extractor

    original = sentence._postprocess_markdown_nodes
    counter = {"calls": 0}

    def _counting(*args, **kwargs):
        counter["calls"] += 1
        return original(*args, **kwargs)

    async def _read(*args, **kwargs) -> BackendRead:
        return BackendRead([Document(text="# Section\n\n" + "word " * 40)], structured, "plain")

    monkeypatch.setattr(sentence, "_postprocess_markdown_nodes", _counting)
    monkeypatch.setattr(chunker, "read_document", _read)
    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _fake_metadata([]))
    settings = effective_settings(markdown_heading_prepend=True)

    nodes = await chunker.read_and_chunk_file_async(Path("doc.md"), settings=settings)

    assert counter["calls"] == 1
    assert nodes
    for node in nodes:
        prefix = f"[{node.metadata['header_path']}] "
        assert node.text.startswith(prefix)
        assert not node.text.startswith(prefix * 2)


@pytest.mark.asyncio
async def test_store_keyword_reaches_metadata_extraction(
    monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """Task 3.1: the chunker forwards its ``store`` keyword to metadata."""
    from omrs.core.metadata import extractor

    async def _read(*args, **kwargs) -> BackendRead:
        return BackendRead([Document(text="body")], False, "plain")

    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(chunker, "read_document", _read)
    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _fake_metadata(captured))
    owning_store = object()

    await chunker.read_and_chunk_file_async(
        Path("plain.txt"), settings=effective_settings(), store=owning_store
    )

    assert len(captured) == 1
    assert captured[0]["store"] is owning_store


def _patch_pipeline_store_io(monkeypatch: pytest.MonkeyPatch, written: list[list]) -> None:
    """Fake every store interaction of ``ingest_path_async``."""
    from omrs.core.codebase import codebase_map
    from omrs.core.ingestion import pipeline
    from omrs.core.ingestion.replacement import WriteTimings

    def _no_detection(*args, **kwargs):
        raise RuntimeError("detection disabled in test")

    async def _replace(nodes, **kwargs):
        written.append(list(nodes))

        class _Outcome:
            chunks_written = len(nodes)
            chunks_removed = 0
            source_attempt = "test-attempt"
            timings = WriteTimings()

        return _Outcome()

    monkeypatch.setattr(codebase_map, "detect_file_types", _no_detection)
    monkeypatch.setattr(pipeline, "assert_source_lineage_compatible", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "is_complete_current_version", lambda *a, **k: (False, 0))
    monkeypatch.setattr(pipeline, "replace_source_nodes_async", _replace)


def test_ordinary_ingestion_invokes_registered_strategy_and_forwards_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effective_settings, sentinel_strategy
) -> None:
    """Ordinary ingestion reaches the sentinel and the owning store."""
    from omrs.core.ingestion import ingest_path_async
    from omrs.core.metadata import extractor

    (tmp_path / "plain.txt").write_text("Plain body text.", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n\nMarkdown body.", encoding="utf-8")
    captured: list[dict[str, Any]] = []
    written: list[list] = []
    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _fake_metadata(captured))
    _patch_pipeline_store_io(monkeypatch, written)
    owning_store = object()

    result = asyncio.run(
        ingest_path_async(
            str(tmp_path),
            collection_name="dispatch_test",
            effective_settings=effective_settings(),
            store=owning_store,
        )
    )

    assert result["status"] == "ok", result
    assert sorted(Path(c["file_path"]).name for c in sentinel_strategy) == [
        "notes.md",
        "plain.txt",
    ]
    by_name = {Path(c["file_path"]).name: c for c in sentinel_strategy}
    assert by_name["notes.md"]["is_markdown"] is True
    assert by_name["plain.txt"]["is_markdown"] is False
    assert all([n.text for n in nodes] == [SENTINEL_TEXT] for nodes in written)
    assert len(captured) == 2
    assert all(entry["store"] is owning_store for entry in captured)
