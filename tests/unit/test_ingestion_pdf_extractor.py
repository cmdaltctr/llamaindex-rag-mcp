"""Integration test: _read_and_chunk_file_async uses the PDF reader factory.

Verifies the factory is wired into SimpleDirectoryReader via
file_extractor, and that bbox metadata propagates to Node.metadata
for the LiteParse path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/vaswani2017_attention.pdf"
)


@pytest.fixture
def liteparse_default(effective_settings):
    """Set liteparse as the process-wide PDF reader, restored after the test.

    The chunker now passes ``resolved.pdf_reader`` to the factory (spec:
    settings-dependency-injection), but the LiteParse *adapter* still reads
    worker/OCR defaults from the composition-root default when constructed
    without arguments — this fixture keeps those values deterministic.
    Explicit save/restore rather than relying on the autouse fixture's
    blanket reset.
    """
    from rag_mcp.core.settings import (
        get_default_effective_settings,
        set_default_effective_settings,
    )

    original = get_default_effective_settings()
    settings = effective_settings(extraction_mode="disabled", pdf_reader="liteparse")
    set_default_effective_settings(settings)
    yield settings
    set_default_effective_settings(original)


class TestIngestionPDFExtractor:
    """Integration tests for the factory wiring in ingestion.py."""

    def test_pypdf_path_produces_nodes(self, effective_settings):
        """_read_and_chunk_file_async uses the factory; pypdf path unchanged."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        import asyncio

        from rag_mcp.core.ingestion.chunker import (
            read_and_chunk_file_async as _read_and_chunk_file_async,
        )

        settings = effective_settings(extraction_mode="disabled", pdf_reader="pypdf")
        nodes = asyncio.run(_read_and_chunk_file_async(CORPUS_PDF, settings=settings))

        assert len(nodes) > 0
        # Every node should have metadata
        for node in nodes:
            assert hasattr(node, "metadata") or hasattr(node, "node")


@pytest.mark.slow
class TestIngestionLiteParsePath:
    """Integration tests requiring [pdf-liteparse] extra."""

    def test_liteparse_path_propagates_bbox_metadata(self, monkeypatch, liteparse_default):
        """When PDF_READER=liteparse, nodes carry bbox metadata."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        settings = liteparse_default

        import rag_mcp.integrations.pdf.factory as factory_mod

        monkeypatch.setattr(factory_mod, "_pdf_reader_logged", set())

        import asyncio

        from rag_mcp.core.ingestion.chunker import (
            read_and_chunk_file_async as _read_and_chunk_file_async,
        )

        nodes = asyncio.run(_read_and_chunk_file_async(CORPUS_PDF, settings=settings))

        assert len(nodes) > 0
        # Check that at least some nodes have liteparse metadata
        liteparse_nodes = [
            n
            for n in nodes
            if getattr(getattr(n, "metadata", {}), "get", lambda *a: None)("pdf_reader")
            == "liteparse"
        ]
        assert len(liteparse_nodes) > 0, "Expected nodes with pdf_reader=liteparse"


class TestChunkerThreadsReaderName:
    """The chunker passes resolved.pdf_reader to the factory (spec delta)."""

    def test_chunker_passes_resolved_reader_to_factory(
        self, tmp_path, effective_settings, monkeypatch
    ):
        """_read_sync calls get_pdf_reader with the injected settings' name."""
        import asyncio

        from llama_index.core.schema import Document

        import rag_mcp.integrations.pdf as pdf_pkg
        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

        requested_names: list[str] = []

        class StubExtractor:
            def load_data(self, *args, **kwargs):
                return [Document(text="stub pdf text for chunking")]

        def fake_get_pdf_reader(name):
            requested_names.append(name)
            return StubExtractor

        monkeypatch.setattr(pdf_pkg, "get_pdf_reader", fake_get_pdf_reader)

        fake_pdf = tmp_path / "stub.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 stub")
        settings = effective_settings(extraction_mode="disabled", pdf_reader="pypdf")

        nodes = asyncio.run(read_and_chunk_file_async(fake_pdf, settings=settings))

        assert requested_names == ["pypdf"]
        assert len(nodes) > 0
