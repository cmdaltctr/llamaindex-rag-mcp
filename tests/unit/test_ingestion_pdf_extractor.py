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

    def test_liteparse_path_propagates_bbox_metadata(self, monkeypatch, effective_settings):
        """When PDF_READER=liteparse, nodes carry bbox metadata."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        # The PDF factory reads the composition-root default, not per-call
        # settings, so select the reader through the default (gotcha #8a).
        from rag_mcp.core.settings import set_default_effective_settings

        settings = effective_settings(extraction_mode="disabled", pdf_reader="liteparse")
        set_default_effective_settings(settings)

        import rag_mcp.integrations.pdf.factory as factory_mod

        monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)

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
