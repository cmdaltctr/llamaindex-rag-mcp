"""Per-source ingestion seams (add-local-web-pipeline-workspace, task 3.3).

Graph adapters will call the source, read, normalise, enrich and split
seams one source at a time. These tests pin each seam on its own, prove
that ``ingest_path_async`` composes the same seams, and keep the reader
declaration and bounded-processing guarantees. No model, network or
remote store is used: the store is the per-test embedded LanceDB from
``tests/conftest.py`` and metadata extraction is faked or disabled.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Document
from llama_index.core.schema import TextNode

from omrs.core.chunking import registry as chunking_registry
from omrs.core.ingestion import chunker, pipeline
from omrs.core.ingestion.backends.orchestrator import BackendRead
from omrs.core.ingestion.normalise import normalise_reader_text

SENTINEL_TEXT = "SEAM-SENTINEL-OUTPUT"
_sentinel_calls: list[dict[str, Any]] = []


async def _sentinel_sentence(
    documents: list,
    file_path: str,
    is_markdown: bool,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: object | None = None,
    markdown_chunking: object | None = None,
) -> list:
    """Record one registry dispatch and return a recognisable node."""
    _sentinel_calls.append(
        {
            "documents": documents,
            "is_markdown": is_markdown,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "settings": settings,
        }
    )
    return [TextNode(text=SENTINEL_TEXT, metadata={})]


@pytest.fixture
def sentinel_sentence(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Register the sentinel as the ``sentence`` strategy through the registry."""
    _sentinel_calls.clear()
    monkeypatch.setitem(chunking_registry._registry, "sentence", f"{__name__}:_sentinel_sentence")
    monkeypatch.delitem(chunking_registry._cache, "sentence", raising=False)
    yield _sentinel_calls
    chunking_registry._cache.pop("sentence", None)


def _offline(effective_settings, **overrides) -> Any:
    """Return deterministic offline settings for seam tests."""
    base = {"extraction_mode": "disabled", "pdf_reader": "pypdf", "ocr_fallback_enabled": False}
    return effective_settings(**{**base, **overrides})


# ── Source preparation ───────────────────────────────────────────────────


def test_iter_source_units_is_lazy_and_keeps_content_types(tmp_path: Path) -> None:
    """Units are yielded one at a time with their detected content type."""
    from omrs.core.ingestion.sources import SourceUnit, iter_source_units

    first, second = tmp_path / "a.txt", tmp_path / "sub" / "b.md"
    units = iter_source_units(tmp_path, [first, second], {"sub/b.md": "text/markdown"})

    assert inspect.isgenerator(units)
    assert list(units) == [
        SourceUnit(index=0, file_path=first, rel_path="a.txt", content_type=None),
        SourceUnit(
            index=1, file_path=second, rel_path=str(Path("sub/b.md")), content_type="text/markdown"
        ),
    ]


def test_detect_content_types_degrades_to_empty_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """A detector failure keeps extension routing, exactly as before."""
    from omrs.core.codebase import codebase_map
    from omrs.core.ingestion.sources import detect_content_types

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("detector unavailable")

    monkeypatch.setattr(codebase_map, "detect_file_types", _boom)

    assert detect_content_types(tmp_path, settings=_offline(effective_settings)) == {}


def test_detect_content_types_forwards_injected_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """Detection receives the operation's settings, never a process default."""
    from types import SimpleNamespace

    from omrs.core.codebase import codebase_map
    from omrs.core.ingestion.sources import detect_content_types

    seen: list[Any] = []

    def _detect(path: str, *, settings: Any) -> Any:
        seen.append(settings)
        entry = SimpleNamespace(path="a.md", group="text", label="markdown")
        return SimpleNamespace(entries=[entry])

    monkeypatch.setattr(codebase_map, "detect_file_types", _detect)
    settings = _offline(effective_settings)

    assert detect_content_types(tmp_path, settings=settings) == {"a.md": "text/markdown"}
    assert seen == [settings]


@pytest.mark.asyncio
async def test_prepare_source_matches_source_state_identity(
    tmp_path: Path, effective_settings
) -> None:
    """The prepared identity uses the shared source_state formulas."""
    from omrs.core.chunking.model_token import resolve_markdown_chunking
    from omrs.core.ingestion.hashing import sha256_file
    from omrs.core.ingestion.source_state import (
        build_source_id,
        build_source_version,
        canonical_source_path,
    )
    from omrs.core.ingestion.sources import (
        build_ingestion_context,
        prepare_source,
    )

    source = tmp_path / "doc.txt"
    source.write_text("Identity body.", encoding="utf-8")
    settings = _offline(effective_settings)
    context = build_ingestion_context(
        settings, markdown_chunking=resolve_markdown_chunking(settings)
    )

    identity = await prepare_source(source, content_type=None, context=context)

    assert context.chunk_size == settings.chunking.chunk_size
    assert context.chunk_overlap == settings.chunking.chunk_overlap
    assert identity.canonical_file_path == canonical_source_path(source)
    assert identity.source_id == build_source_id(canonical_source_path(source))
    assert identity.content_hash == sha256_file(source)
    assert identity.text_format == "plain"
    assert identity.source_version == build_source_version(
        identity.content_hash, identity.index_identity
    )


@pytest.mark.asyncio
async def test_check_source_state_rejects_pre_lineage_rows(
    tmp_path: Path, effective_settings
) -> None:
    """The compatibility guard runs before any parse or mutation."""
    from omrs.core.chunking.model_token import resolve_markdown_chunking
    from omrs.core.ingestion.source_state import IncompatibleSourceLineageError
    from omrs.core.ingestion.sources import (
        build_ingestion_context,
        check_source_state,
        prepare_source,
    )
    from omrs.core.vectordb import get_default_store

    source = tmp_path / "legacy.txt"
    source.write_text("Legacy body.", encoding="utf-8")
    settings = _offline(effective_settings)
    store = get_default_store()
    context = build_ingestion_context(
        settings, markdown_chunking=resolve_markdown_chunking(settings)
    )
    identity = await prepare_source(source, content_type=None, context=context)
    store.write_nodes(
        [TextNode(text="legacy", metadata={"file_path": identity.canonical_file_path})],
        "seam_legacy",
    )

    with pytest.raises(IncompatibleSourceLineageError):
        await check_source_state(identity, store=store, collection_name="seam_legacy")


# ── Read, normalise, enrich, split ───────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "text_format", "expected"),
    [
        ("plain.txt", "plain", False),
        ("notes.md", "plain", True),
        ("paper.pdf", "markdown", True),
        ("paper.pdf", "plain", False),
    ],
)
def test_declares_markdown_follows_reader_declaration(
    name: str, text_format: str, expected: bool
) -> None:
    """Markdown routing follows ``.md`` or the reader's declaration only."""
    read = BackendRead(documents=[], structured=False, text_format=text_format)

    assert chunker.declares_markdown(Path(name), read) is expected


@pytest.mark.parametrize(
    ("name", "content_type", "enabled", "normalised"),
    [
        ("paper.pdf", None, True, True),
        ("upload.bin", "document/pdf", True, True),
        ("plain.txt", None, True, False),
        ("paper.pdf", None, False, False),
    ],
)
def test_normalise_backend_read_scope(
    effective_settings, name: str, content_type: str | None, enabled: bool, normalised: bool
) -> None:
    """Normalisation applies to PDF reads only, and only when enabled."""
    raw = 'Intro <span style="x">word</span> and <b>bold</b><br>end'
    read = BackendRead(documents=[Document(text=raw)], structured=False, text_format="plain")
    settings = _offline(effective_settings, normalise_reader_output=enabled)

    result = chunker.normalise_backend_read(
        read, Path(name), content_type=content_type, settings=settings
    )

    expected = normalise_reader_text(raw) if normalised else raw
    assert expected != raw or not normalised
    assert result.documents[0].text == expected
    assert result.text_format == "plain"


@pytest.mark.asyncio
async def test_enrich_documents_requires_explicit_store_and_settings(effective_settings) -> None:
    """Omitting ``store`` or ``settings`` is a call error, never a default."""
    documents = [Document(text="body")]
    with pytest.raises(TypeError):
        await chunker.enrich_documents(  # type: ignore[call-arg]
            documents,
            Path("a.txt"),
            content_type=None,
            taxonomy_mode=None,
            settings=_offline(effective_settings),
        )
    with pytest.raises(TypeError):
        await chunker.enrich_documents(  # type: ignore[call-arg]
            documents, Path("a.txt"), content_type=None, taxonomy_mode=None, store=None
        )


@pytest.mark.asyncio
async def test_enrich_documents_forwards_store_settings_and_taxonomy(
    monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """Metadata extraction sees the owning store and the injected settings."""
    from omrs.core.metadata import extractor

    captured: list[dict[str, Any]] = []

    async def _extract(text: str, filename: str, settings: Any = None, **kwargs: Any) -> Any:
        captured.append({"text": text, "settings": settings, **kwargs})
        return {"category": "model", "keywords": ["k1", "k2"]}, True

    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _extract)
    settings = _offline(effective_settings)
    owning_store = object()

    metadata, degraded = await chunker.enrich_documents(
        [Document(text="one"), Document(text="two")],
        Path("a.txt"),
        content_type="text/plain",
        taxonomy_mode="file_type",
        settings=settings,
        store=owning_store,
    )

    assert captured == [
        {"text": "one\ntwo", "settings": settings, "store": owning_store},
    ]
    assert degraded is True
    assert metadata == {"category": "plain", "keywords": ["k1", "k2"]}


@pytest.mark.asyncio
async def test_enrich_documents_without_documents_skips_extraction(effective_settings) -> None:
    """No documents means no extraction call and no degradation."""
    metadata, degraded = await chunker.enrich_documents(
        [],
        Path("a.txt"),
        content_type=None,
        taxonomy_mode=None,
        settings=_offline(effective_settings),
        store=None,
    )

    assert (metadata, degraded) == ({}, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [True, False])
async def test_split_documents_uses_registry_and_stamps_metadata(
    sentinel_sentence: list[dict[str, Any]], effective_settings, structured: bool
) -> None:
    """Splitting resolves the registered strategy and applies shared stamps."""
    settings = _offline(effective_settings)
    documents = [Document(text="body")]

    nodes = await chunker.split_documents(
        documents,
        Path("paper.pdf"),
        structured=structured,
        is_markdown=True,
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
        content_type="document/pdf",
        settings=settings,
        doc_metadata={"keywords": ["a", "b"]},
    )

    assert [node.text for node in nodes] == [SENTINEL_TEXT]
    call = sentinel_sentence[0]
    assert call["is_markdown"] is True
    assert call["chunk_size"] == settings.chunking.markdown_chunk_size
    assert call["settings"] is settings
    assert nodes[0].metadata["content_type"] == "document/pdf"
    assert nodes[0].metadata["keywords"] == "a, b"
    # Only pre-structured reads stamp the documents before splitting.
    assert ("content_type" in documents[0].metadata) is structured


@pytest.mark.asyncio
async def test_chunk_specialised_source_returns_none_for_document_reads(
    tmp_path: Path, effective_settings
) -> None:
    """Sources without a code/config route go to the document reader."""
    source = tmp_path / "notes.txt"
    source.write_text("Plain body.", encoding="utf-8")
    settings = _offline(effective_settings)

    result = await chunker.chunk_specialised_source(
        source,
        content_type="text/plain",
        fallback_strategy=None,
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
        settings=settings,
    )

    assert result is None


@pytest.mark.asyncio
async def test_read_and_chunk_composes_the_seams(
    monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """The standard chunk path calls the same normalise/enrich/split seams."""
    calls: list[str] = []
    real = {
        name: getattr(chunker, name)
        for name in ("normalise_backend_read", "enrich_documents", "split_documents")
    }

    def _spy(name: str) -> Any:
        target = real[name]
        if inspect.iscoroutinefunction(target):

            async def _async_spy(*args: Any, **kwargs: Any) -> Any:
                calls.append(name)
                return await target(*args, **kwargs)

            return _async_spy

        def _sync_spy(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return target(*args, **kwargs)

        return _sync_spy

    async def _read(file_path: Path, *, settings: Any, ocr_client: Any = None) -> BackendRead:
        return BackendRead([Document(text="Body text.")], structured=False, text_format="plain")

    monkeypatch.setattr(chunker, "read_document", _read)
    for name in real:
        monkeypatch.setattr(chunker, name, _spy(name))

    nodes = await chunker.read_and_chunk_file_async(
        Path("plain.txt"), settings=_offline(effective_settings), store=None
    )

    assert calls == ["normalise_backend_read", "enrich_documents", "split_documents"]
    assert nodes and nodes.metadata_degraded is False


# ── Bounded per-source processing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_directory_ingestion_finishes_each_source_before_the_next(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """One source is read, chunked and committed before the next is read."""
    from omrs.core.codebase import codebase_map
    from omrs.core.ingestion.replacement import ReplaceSourceOutcome, WriteTimings

    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(f"Body of {name}.", encoding="utf-8")
    events: list[str] = []

    async def _read(file_path: Path, **kwargs: Any) -> list:
        events.append(f"read:{file_path.name}")
        return [TextNode(text=file_path.name)]

    async def _replace(nodes: list, **kwargs: Any) -> ReplaceSourceOutcome:
        events.append(f"commit:{Path(kwargs['file_path']).name}")
        return ReplaceSourceOutcome(len(nodes), 0, "attempt", WriteTimings())

    def _no_detection(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("detection disabled")

    monkeypatch.setattr(codebase_map, "detect_file_types", _no_detection)
    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", _read)
    monkeypatch.setattr(pipeline, "replace_source_nodes_async", _replace)

    result = await pipeline.ingest_path_async(
        str(tmp_path),
        collection_name="seam_bounded",
        effective_settings=_offline(effective_settings),
    )

    assert result["status"] == "ok", result
    assert result["files_indexed"] == 3
    # Discovery order is the loader's; each read is followed by its own commit.
    reads, commits = events[0::2], events[1::2]
    assert [event.split(":")[1] for event in reads] == [e.split(":")[1] for e in commits]
    assert all(event.startswith("read:") for event in reads)
    assert all(event.startswith("commit:") for event in commits)
    assert sorted(event.split(":")[1] for event in reads) == ["a.txt", "b.txt", "c.txt"]


@pytest.mark.asyncio
async def test_failed_source_keeps_sibling_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """A per-file failure is reported while sibling commits survive."""
    from omrs.core.codebase import codebase_map

    (tmp_path / "good.txt").write_text("Good body text.", encoding="utf-8")
    (tmp_path / "zbad.txt").write_text("Bad body text.", encoding="utf-8")
    real_read = pipeline.read_and_chunk_file_async

    async def _read(file_path: Path, **kwargs: Any) -> Any:
        if file_path.name == "zbad.txt":
            raise ValueError("reader exploded")
        return await real_read(file_path, **kwargs)

    def _no_detection(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("detection disabled")

    monkeypatch.setattr(codebase_map, "detect_file_types", _no_detection)
    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", _read)

    result = await pipeline.ingest_path_async(
        str(tmp_path),
        collection_name="seam_partial",
        effective_settings=_offline(effective_settings),
    )

    assert result["status"] == "ok", result
    assert result["files_indexed"] == 1
    statuses = {detail["file"]: detail["status"] for detail in result["file_details"]}
    assert statuses == {"good.txt": "indexed", "zbad.txt": "failed"}
    failed = next(d for d in result["file_details"] if d["status"] == "failed")
    assert failed["failure_stage"] == "file"
    assert "source_version" in failed
