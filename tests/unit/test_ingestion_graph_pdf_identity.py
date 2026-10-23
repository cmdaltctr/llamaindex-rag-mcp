"""The identify step uses the reader of the Read document step.

Task 3.3 and 3.4 of ``add-pdf-reader-step-setting``. The stored source
identity must name the reader that reads the source, and a reader change
must reprocess the source on the next explicit ingest.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import pin_detection
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    invoke,
    offline_settings,
    resources,
    run_by_hand,
)

from omrs.core.ingestion.graph_fingerprint import INGESTION_SHAPE_RESOURCE, IngestionShape
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.ingestion.sources import SourceUnit, build_ingestion_context

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"


@pytest.fixture
def pdf_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    pin_detection(monkeypatch)
    root = tmp_path / "pdfs"
    root.mkdir()
    shutil.copy(FIXTURE, root / "smoke_text.pdf")
    return root


def _identity_with(settings: Any, text_format: str, block: dict | None) -> str:
    ctx = build_ingestion_context(
        settings, embed_model=LlamaIndexSettings.embed_model, graph_shape=block
    )
    return build_index_identity(
        settings,
        content_type=None,
        chunk_size=ctx.chunk_size,
        chunk_overlap=ctx.chunk_overlap,
        text_format=text_format,
        embed_model=ctx.embed_model,
        ocr_routing=ctx.ocr_routing,
        ocr_worker_fingerprint=ctx.ocr_worker_fingerprint,
        ocr_fallback_fingerprint=ctx.ocr_fallback_fingerprint,
        tokenizer=ctx.markdown_chunking.tokenizer_identity,
        resolved_splitter=ctx.markdown_chunking.resolved_splitter,
        graph_shape=ctx.graph_shape,
    )


@pytest.mark.asyncio
async def test_identify_builds_the_identity_with_the_shape_reader(
    pdf_root: Path, effective_settings: Any
) -> None:
    """A shape reader of ``pdf_inspector`` wins over the host ``pypdf``."""
    from omrs.core.vectordb import get_default_store

    host = offline_settings(effective_settings)
    assert host.pdf_reader == "pypdf"
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("pdf_identity"), host, pdf_root, catalogue)
    shape = IngestionShape("f" * 64, standard=False, pdf_reader="pdf_inspector")
    run_resources = resources(
        snapshot, catalogue, get_default_store(), **{INGESTION_SHAPE_RESOURCE: shape}
    )
    unit = SourceUnit(0, pdf_root / "smoke_text.pdf", "smoke_text.pdf", None)

    out = await invoke(snapshot, catalogue, run_resources, "identify", {"sources": (unit,)})

    identity = out.values["sources"].identity
    step_host = host.model_copy(update={"pdf_reader": "pdf_inspector"})
    block = shape.identity_block()
    assert identity.index_identity == _identity_with(step_host, "markdown", block)
    assert identity.index_identity != _identity_with(host, "plain", block)
    assert identity.text_format == "markdown"


@pytest.mark.asyncio
async def test_reader_change_reprocesses_and_stores_the_step_identity(
    pdf_root: Path, effective_settings: Any
) -> None:
    """Indexed, unchanged, reader change (indexed again), unchanged again."""
    from tests.fixtures.pipeline_parity.ingestion.snapshot import collect_rows

    from omrs.core.ingestion.graph_fingerprint import ingestion_shape
    from omrs.core.vectordb import get_default_store

    host = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()

    async def run(**read_params: Any) -> list[str]:
        data = canonical_graph("pdf_reuse", read=read_params)
        snapshot = admit(data, host, pdf_root, catalogue)
        outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))
        return [o.values["summary"]["status"] for o in outputs]

    assert await run() == ["indexed"]
    assert await run() == ["skipped_unchanged"]
    assert await run(pdf_reader="pdf_inspector") == ["indexed"]

    rows = collect_rows(store, "pdf_reuse", pdf_root)
    assert rows
    assert {r["metadata"].get("pdf_reader") for r in rows} == {"pdf_inspector"}
    shape = ingestion_shape(
        admit(canonical_graph("pdf_reuse", read={"pdf_reader": "pdf_inspector"}), host, pdf_root),
        catalogue,
    )
    expected = _identity_with(
        host.model_copy(update={"pdf_reader": "pdf_inspector"}),
        "markdown",
        shape.identity_block(),
    )
    assert {r["metadata"]["source_index_identity"] for r in rows} == {expected}
    assert await run(pdf_reader="pdf_inspector") == ["skipped_unchanged"]
