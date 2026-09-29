"""Tests for complete pdf-inspector OCR evidence (change full-page-ocr-evidence).

pdf-inspector detects OCR need from at most 8 sample pages. For a
``text_based`` PDF longer than that, the adapter must count OCR pages from
a full page scan (``extract_pages_markdown``), or image-only pages outside
the sample never reach the routing gate (Experiment 33 boundary probe,
TDR-026).

The package is stubbed in ``sys.modules``; nothing parses a real PDF.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


def _stub(
    monkeypatch,
    *,
    pdf_type: str = "text_based",
    page_count: int = 20,
    markdown: str = "# Body\n\nhealthy text",
    sampled: list[int] | None = None,
    full_scan: list[int] | None = None,
    full_scan_error: Exception | None = None,
) -> MagicMock:
    """Install a fake ``pdf_inspector`` with sampled and full-scan evidence."""
    stub = MagicMock()
    result = stub.process_pdf.return_value
    result.markdown = markdown
    result.pdf_type = pdf_type
    result.confidence = 1.0
    result.page_count = page_count
    result.pages_needing_ocr = sampled or []
    if full_scan_error is not None:
        stub.extract_pages_markdown.side_effect = full_scan_error
    else:
        stub.extract_pages_markdown.return_value.pages_needing_ocr = full_scan or []
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    return stub


def _read(tmp_path):
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    return PdfInspectorReader().load_data(file=fake_pdf)[0]


def test_full_scan_counts_pages_the_sample_missed(monkeypatch, tmp_path):
    """Image-only pages outside the 8-page sample reach pages_needing_ocr."""
    stub = _stub(monkeypatch, sampled=[], full_scan=[2, 10, 14])

    document = _read(tmp_path)

    stub.extract_pages_markdown.assert_called_once()
    assert document.metadata["pages_needing_ocr"] == 3
    # Classification and extraction are the library's, unchanged.
    assert document.metadata["pdf_type"] == "text_based"
    assert document.metadata["pdf_confidence"] == 1.0
    assert "healthy text" in document.text


@pytest.mark.parametrize("page_count", [1, 8])
def test_short_text_pdf_gets_no_full_scan(monkeypatch, tmp_path, page_count):
    """Eight pages or fewer are fully covered by the detection sample."""
    stub = _stub(monkeypatch, page_count=page_count, sampled=[], full_scan=[0])

    document = _read(tmp_path)

    stub.extract_pages_markdown.assert_not_called()
    assert document.metadata["pages_needing_ocr"] == 0


@pytest.mark.parametrize("pdf_type", ["scanned", "image_based", "mixed"])
def test_non_text_classifications_get_no_full_scan(monkeypatch, tmp_path, pdf_type):
    """Scanned and image PDFs route anyway; mixed results are already complete."""
    stub = _stub(monkeypatch, pdf_type=pdf_type, sampled=[4, 9], full_scan=[1, 4, 9])

    document = _read(tmp_path)

    stub.extract_pages_markdown.assert_not_called()
    assert document.metadata["pages_needing_ocr"] == 2


def test_full_scan_failure_keeps_sampled_evidence(monkeypatch, tmp_path, caplog):
    """A failing full scan never fails the read and keeps the sampled count."""
    _stub(monkeypatch, sampled=[0], full_scan_error=RuntimeError("parse failed"))

    with caplog.at_level("WARNING"):
        document = _read(tmp_path)

    assert document.metadata["pages_needing_ocr"] == 1
    assert any("full page scan" in record.getMessage() for record in caplog.records)


def test_silent_empty_rescue_records_full_scan_count(monkeypatch, tmp_path):
    """The rescue keeps its contract, with the complete pre-fallback count."""
    from llama_index.core import Document

    from omrg.integrations.pdf import registry

    class _Rescue:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            pass

        def load_data(self, file, *args, **kwargs):
            return [Document(text="recovered text")]

    monkeypatch.setitem(registry._cache, "liteparse", _Rescue)
    _stub(monkeypatch, markdown="", sampled=list(range(8)), full_scan=list(range(20)))

    metadata = _read(tmp_path).metadata

    assert metadata["pages_needing_ocr"] == 0
    assert metadata["pages_needing_ocr_before_fallback"] == 20
    assert metadata["extraction_fallback_backend"] == "liteparse"
