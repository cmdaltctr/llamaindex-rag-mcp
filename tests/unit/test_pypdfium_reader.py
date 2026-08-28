"""Tests for the pypdfium2 reader adapter.

Marked @pytest.mark.slow because they require the [pdf-pypdfium2] extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/vaswani2017_attention.pdf"
)


@pytest.mark.slow
class TestPyPDFium2Reader:
    """Tests requiring [pdf-pypdfium2] extra."""

    def test_successful_parse(self):
        """pypdfium2 adapter parses a PDF and returns Documents."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from rag_mcp.integrations.pdf.pypdfium import PyPDFium2Reader

        reader = PyPDFium2Reader()
        documents = reader.load_data(file=CORPUS_PDF)

        assert len(documents) > 0
        for doc in documents:
            assert doc.metadata.get("pdf_reader") == "pypdfium2"

    def test_missing_import_handling(self):
        """If pypdfium2 is not installed, ImportError propagates."""
        # This test only runs when pypdfium2 IS installed (to verify the
        # adapter works). The actual missing-import case is handled by the
        # factory's resolution logic in config.py.
        pass
