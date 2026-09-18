"""Per-page OCR evidence for the ``page`` routing unit (task 4.1).

``page`` mode decides OCR need per page from a scan of every page, with no
8-page sample and no page-fraction threshold. The scan is the only source of
that evidence, so its page numbering has to be right: pdf-inspector numbers
``extract_pages_markdown`` pages from 0 and ``process_pdf_with_ocr`` pages
from 1, and a document routed on the wrong index would OCR its neighbour.

The package is stubbed in ``sys.modules``; nothing parses a real PDF.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


def _page(index: int, markdown: str, needs_ocr: bool, reason: str | None = None):
    """Return one ``extract_pages_markdown`` page, numbered from 0 as the library does."""
    return SimpleNamespace(page=index, markdown=markdown, needs_ocr=needs_ocr, ocr_reason=reason)


def _stub(monkeypatch, pages):
    """Install a pdf_inspector stub whose full scan returns *pages*."""
    stub = SimpleNamespace(
        extract_pages_markdown=lambda _path: SimpleNamespace(pages=list(pages)),
    )
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    return stub


def test_page_numbers_are_one_based(monkeypatch, tmp_path):
    """The library numbers from 0; the evidence must speak the OCR API's language."""
    from omrg.integrations.pdf.page_routing import page_evidence

    _stub(monkeypatch, [_page(0, "first", False), _page(1, "second", True, "image_only")])

    evidence = page_evidence(tmp_path / "doc.pdf")

    assert [entry.page for entry in evidence] == [1, 2]


def test_evidence_carries_native_text_and_flags(monkeypatch, tmp_path):
    """Each page reports its own Markdown, its OCR need and the stated reason."""
    from omrg.integrations.pdf.page_routing import page_evidence

    _stub(monkeypatch, [_page(0, "clean", False), _page(1, "", True, "image_only")])

    evidence = page_evidence(tmp_path / "doc.pdf")

    assert [(e.markdown, e.needs_ocr, e.reason) for e in evidence] == [
        ("clean", False, None),
        ("", True, "image_only"),
    ]


def test_every_flagged_page_is_reported(monkeypatch, tmp_path):
    """No sample and no threshold: a flagged page anywhere in the file is evidence."""
    from omrg.integrations.pdf.page_routing import page_evidence

    pages = [_page(index, "text", index == 19) for index in range(20)]
    _stub(monkeypatch, pages)

    flagged = [entry.page for entry in page_evidence(tmp_path / "doc.pdf") if entry.needs_ocr]

    assert flagged == [20]


def test_missing_markdown_is_empty_not_none(monkeypatch, tmp_path):
    """A page with no text contributes an empty string, never ``None``."""
    from omrg.integrations.pdf.page_routing import page_evidence

    _stub(monkeypatch, [_page(0, None, True, "image_only")])

    assert page_evidence(tmp_path / "doc.pdf")[0].markdown == ""


def test_scan_failure_raises(monkeypatch, tmp_path):
    """A failed scan is not silently an empty document.

    In ``document`` mode a failed full scan falls back to the sampled count,
    because sampled evidence still exists. In ``page`` mode the scan is the
    only evidence there is, so swallowing the failure would route nothing and
    claim the file was clean.
    """
    from omrg.integrations.pdf.page_routing import page_evidence

    def _boom(_path):
        raise RuntimeError("pdfium refused the file")

    monkeypatch.setitem(sys.modules, "pdf_inspector", SimpleNamespace(extract_pages_markdown=_boom))

    with pytest.raises(RuntimeError):
        page_evidence(tmp_path / "doc.pdf")
