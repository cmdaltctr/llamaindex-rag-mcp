"""Tests for the LiteParse reader adapter.

The settings test uses a stubbed parser and runs in the fast suite. The
real-parser tests are marked ``slow`` because they require the native
PDFium binary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/vaswani2017_attention.pdf"
)


def test_default_constructor_reads_effective_settings(monkeypatch, tmp_path, effective_settings):
    """Normal LiteParse use still reads both injected parser settings."""
    from omrg.core.settings import set_default_effective_settings
    from omrg.integrations.pdf.liteparse import LiteParseReader

    observed: list[tuple[bool, int | None, bool]] = []

    class _StubLiteParse:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None, quiet: bool) -> None:
            observed.append((ocr_enabled, num_workers, quiet))

        def parse(self, file):
            item = SimpleNamespace(text="configured parse", x=0, y=0, width=1, height=1)
            page = SimpleNamespace(page_num=1, text_items=[item])
            return SimpleNamespace(pages=[page])

    monkeypatch.setitem(sys.modules, "liteparse", SimpleNamespace(LiteParse=_StubLiteParse))
    set_default_effective_settings(
        effective_settings(liteparse_ocr_enabled=True, liteparse_num_workers=4)
    )

    documents = LiteParseReader().load_data(tmp_path / "configured.pdf")

    assert observed == [(True, 4, True)]
    assert documents[0].get_content() == "configured parse"


@pytest.mark.slow
class TestLiteParseReader:
    """Tests requiring [pdf-liteparse] extra."""

    def test_emits_documents_with_bbox_metadata(self):
        """Successful parse emits Documents with pdf_reader=liteparse and bbox fields."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from omrg.integrations.pdf.liteparse import LiteParseReader

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

        from omrg.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        columns = {doc.metadata.get("column") for doc in documents}
        # At least some pages should have left or right column labels
        assert columns & {"left", "right"}, f"Expected column labels but got: {columns}"

    def test_section_bbox_is_json_string(self):
        """section_bbox must be a JSON-encoded string (ChromaDB scalar requirement)."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from omrg.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        for doc in documents:
            bbox_str = doc.metadata.get("section_bbox")
            assert isinstance(bbox_str, str), "section_bbox must be a string"
            bbox = json.loads(bbox_str)
            assert len(bbox) == 4, "section_bbox must have 4 coordinates"
