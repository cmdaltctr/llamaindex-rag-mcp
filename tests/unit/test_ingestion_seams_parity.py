"""Seam composition reproduces ``ingest_path_async`` (task 3.3/3.4 parity).

A graph runner will compose the extracted seams one source at a time. This
test performs that composition by hand over the synthetic fixture tree and
proves the stored chunk ids, texts and metadata equal those written by
``ingest_path_async``. It also pins the path-independent projection to the
committed ``expected_chunks.json`` so a later canonical-graph test has a
deterministic reference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    load_expected,
    pin_detection,
    portable_rows,
)

from omrs.core.ingestion import pipeline


def _offline(effective_settings) -> Any:
    """Return the offline settings the expected snapshot was built with."""
    return effective_settings(
        extraction_mode="disabled", pdf_reader="pypdf", ocr_fallback_enabled=False
    )


async def _ingest_through_seams(root: Path, settings: Any, store: Any, collection: str) -> int:
    """Compose the extracted seams the way a graph runner will."""
    from omrs.core.chunking.model_token import resolve_markdown_chunking
    from omrs.core.ingestion.loader import gather_supported_files
    from omrs.core.ingestion.sources import (
        build_ingestion_context,
        check_source_state,
        chunk_source,
        commit_source,
        detect_content_types,
        iter_source_units,
        prepare_source,
    )

    context = build_ingestion_context(
        settings, markdown_chunking=resolve_markdown_chunking(settings)
    )
    files, _skipped = gather_supported_files(root, extensions=settings.ingestion.ingest_extensions)
    content_types = detect_content_types(root, settings=settings)
    committed = 0
    for unit in iter_source_units(root, files, content_types):
        identity = await prepare_source(
            unit.file_path, content_type=unit.content_type, context=context
        )
        reuse = await check_source_state(identity, store=store, collection_name=collection)
        if reuse.unchanged:
            continue
        nodes = await chunk_source(identity, context=context, store=store)
        outcome = await commit_source(
            nodes, identity, context=context, store=store, collection_name=collection
        )
        committed += outcome.chunks_written
    return committed


@pytest.mark.asyncio
async def test_seam_composition_matches_ingest_path_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """Chunk ids, texts and metadata are identical on both paths."""
    from omrs.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = _offline(effective_settings)
    store = get_default_store()

    result = await pipeline.ingest_path_async(
        str(root), collection_name="parity_standard", effective_settings=settings, store=store
    )
    written = await _ingest_through_seams(root, settings, store, "parity_seams")

    assert result["status"] == "ok", result
    assert result["files_indexed"] == 3
    assert written == result["chunks_created"]
    standard = collect_rows(store, "parity_standard", root)
    composed = collect_rows(store, "parity_seams", root)
    assert composed == standard
    assert portable_rows(standard) == load_expected()


@pytest.mark.asyncio
async def test_seam_composition_reuses_complete_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """A second seam pass over unchanged sources skips every source."""
    from omrs.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = _offline(effective_settings)
    store = get_default_store()

    first = await pipeline.ingest_path_async(
        str(root), collection_name="parity_reuse", effective_settings=settings, store=store
    )
    second = await _ingest_through_seams(root, settings, store, "parity_reuse")

    assert first["files_indexed"] == 3
    assert second == 0


@pytest.mark.asyncio
async def test_seam_composition_never_reads_process_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings
) -> None:
    """With no process defaults installed, explicit seams still ingest."""
    from omrs.core.settings import reset_default_effective_settings
    from omrs.core.vectordb import get_default_store, reset_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = _offline(effective_settings)
    store = get_default_store()
    reset_default_effective_settings()
    reset_default_store()

    written = await _ingest_through_seams(root, settings, store, "parity_no_defaults")

    assert written == len(load_expected())
    rows = collect_rows(store, "parity_no_defaults", root)
    assert portable_rows(rows) == load_expected()
