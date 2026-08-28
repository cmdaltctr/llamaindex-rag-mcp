"""Tests for the LiteParse reader adapter.

All tests are marked @pytest.mark.slow because they require the
[pdf-liteparse] extra and the native PDFium binary. Default
``pytest -m "not slow"`` skips them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/"
    "vaswani2017_attention.pdf"
)


@pytest.mark.slow
class TestLiteParseReader:
    """Tests requiring [pdf-liteparse] extra."""

    def test_emits_documents_with_bbox_metadata(self):
        """Successful parse emits Documents with pdf_reader=liteparse and bbox fields."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from rag_mcp.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        assert len(documents) > 0
        for doc in documents:
            meta = doc.metadata
            assert meta.get("pdf_reader") == "liteparse"
            assert "page" in meta
            assert meta.get("column") in ("left", "right", "single")
            assert "section_bbox" in meta
            assert meta.get("bbox_schema_version") == 1

    def test_two_column_pdf_produces_column_metadata(self):
        """Two-column academic PDF should produce left/right column labels."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from rag_mcp.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        columns = {doc.metadata.get("column") for doc in documents}
        # At least some pages should have left or right column labels
        assert columns & {"left", "right"}, (
            f"Expected column labels but got: {columns}"
        )

    def test_section_bbox_is_json_string(self):
        """section_bbox must be a JSON-encoded string (ChromaDB scalar requirement)."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from rag_mcp.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        for doc in documents:
            bbox_str = doc.metadata.get("section_bbox")
            assert isinstance(bbox_str, str), "section_bbox must be a string"
            bbox = json.loads(bbox_str)
            assert len(bbox) == 4, "section_bbox must have 4 coordinates"
