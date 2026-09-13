"""Tests for the pdf_inspector reader adapter.

Contract for the new ``pdf-inspector`` backend (PyPI extra
``pdf-inspector``, Python module ``pdf_inspector``): factory resolution,
lazy import of the optional package, markdown extraction passthrough, and
an actionable ImportError when the extra is missing.

The package is NOT installed in the test venv. No test performs real PDF
parsing and nothing touches the network: the import path is either stubbed
in ``sys.modules`` or forced to fail, following the mocking pattern used
for optional backends elsewhere in this suite.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from omrg.integrations.pdf.factory import get_pdf_reader
from omrg.integrations.pdf.registry import available as available_readers


def _stub_pdf_inspector(
    monkeypatch,
    markdown: str,
    *,
    pdf_type: str = "text_based",
    confidence: float = 1.0,
    page_count: int = 1,
    pages_needing_ocr: list[int] | None = None,
) -> None:
    """Install a fake ``pdf_inspector`` module in ``sys.modules``.

    The stub mirrors the real package API: ``process_pdf(path)`` returns
    an object carrying ``markdown``, ``pdf_type``, ``confidence``,
    ``page_count`` and the ``pages_needing_ocr`` page list. A
    MagicMock backs the module so any import shape the adapter uses
    resolves without the package installed.
    """
    stub = MagicMock()
    result = stub.process_pdf.return_value
    result.markdown = markdown
    result.pdf_type = pdf_type
    result.confidence = confidence
    result.page_count = page_count
    result.pages_needing_ocr = pages_needing_ocr or []
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)


def _stub_pypdf_retry(monkeypatch, page_texts: list[str]) -> None:
    """Seed the reader registry cache with a stub pypdf fallback reader.

    The guard resolves the retry through ``registry.get("pypdf")``, which
    consults ``_cache`` first, so seeding the cache stubs the fallback
    without touching the real reader or the network.
    """
    from llama_index.core import Document

    from omrg.integrations.pdf import registry

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text=text) for text in page_texts]

    monkeypatch.setitem(registry._cache, "pypdf", _StubPypdfReader)


def _stub_pypdf_exploding(monkeypatch) -> None:
    """Seed a fallback reader that fails the test if it is ever invoked."""
    from omrg.integrations.pdf import registry

    class _ExplodingReader:
        def load_data(self, file, *args, **kwargs):
            raise AssertionError("pypdf retry must not run on this path")

    monkeypatch.setitem(registry._cache, "pypdf", _ExplodingReader)


def test_factory_registers_pdf_inspector_name():
    """The registry advertises pdf_inspector as a concrete reader."""
    assert "pdf_inspector" in available_readers()


def test_factory_resolves_pdf_inspector_reader():
    """get_pdf_reader('pdf_inspector') returns an object with load_data."""
    reader = get_pdf_reader("pdf_inspector")
    assert callable(reader.load_data)


def test_adapter_module_imports_pdf_inspector_lazily(monkeypatch):
    """Importing the adapter module must not import the optional package."""
    # delitem (not a bare pop) so teardown restores the module: a permanent
    # eviction leaves the cached ``pdf_inspector.pdf_inspector`` submodule
    # parentless, and the next real import half-initialises with a
    # NameError inside the package ``__init__`` (surfaced when an
    # earlier-running test exercises the real reader).
    monkeypatch.delitem(sys.modules, "pdf_inspector", raising=False)

    importlib.import_module("omrg.integrations.pdf.pdf_inspector")

    assert "pdf_inspector" not in sys.modules


def test_load_data_passthroughs_mock_markdown(monkeypatch, tmp_path):
    """With pdf_inspector stubbed, load_data returns Documents carrying the markdown."""
    markdown = "# Title\n\nBody text extracted by pdf-inspector."
    _stub_pdf_inspector(monkeypatch, markdown)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert isinstance(documents, list)
    assert len(documents) > 0
    for doc in documents:
        assert isinstance(doc.text, str)
        assert markdown in doc.text
        assert doc.metadata.get("pdf_reader") == "pdf_inspector"


def test_missing_package_raises_actionable_importerror(monkeypatch, tmp_path):
    """Without pdf_inspector installed, load_data raises an ImportError naming the fix."""
    monkeypatch.setitem(sys.modules, "pdf_inspector", None)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ImportError) as excinfo:
        PdfInspectorReader().load_data(file=fake_pdf)

    message = str(excinfo.value)
    assert "pdf_inspector" in message
    assert "install" in message.lower()
    assert "uv sync" in message


def test_real_pdf_end_to_end_smoke(fixtures_dir):
    """The packaged default reader parses a real fixture PDF end to end.

    CI forces ``PDF_READER=pypdf`` for the deterministic suite, so the
    promoted default has no real-execution coverage unless a test invokes
    the adapter against an actual PDF. This is that test: the real
    ``pdf_inspector`` package, a real text PDF (hand-built minimal
    fixture — the five ``pdf_dir`` fixtures are synthetic shells that
    classify as scanned with no text layer), real markdown output.
    """
    from pathlib import Path

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    pdf = fixtures_dir / "smoke_text.pdf"
    assert isinstance(pdf, Path)

    docs = PdfInspectorReader().load_data(file=pdf)

    assert len(docs) == 1
    meta = docs[0].metadata
    assert meta["pdf_reader"] == "pdf_inspector"
    assert meta["pdf_type"] == "text_based"
    assert meta["page_count"] == 1
    content = docs[0].get_content()
    assert "Smoke Test Document" in content, content[:200]


# ── Sloman guard: text_based-but-empty contradiction retries via pypdf ──


def test_contradiction_retries_with_pypdf_and_recovers_text(monkeypatch, tmp_path):
    """text_based + empty markdown + pages > 0 retries through the registry.

    The Sloman class: pdf-inspector classifies text_based at full
    confidence yet extracts nothing. The adapter must retry with the
    registered pypdf reader and join the per-page text into one document.
    """
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_pypdf_retry(monkeypatch, ["page one text", "page two text", "page three text"])

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == ("page one text\n\npage two text\n\npage three text")


def test_recovered_text_corrects_the_routing_evidence(monkeypatch, tmp_path):
    """A successful retry zeroes the flagged count and keeps the original."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_pypdf_retry(monkeypatch, ["recovered text"] * 3)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    meta = PdfInspectorReader().load_data(file=fake_pdf)[0].metadata

    # Corrected scalar evidence: the pages were flagged only because the
    # pdf-inspector extraction was empty.
    assert meta["pages_needing_ocr"] == 0
    assert meta["pages_needing_ocr_before_fallback"] == 3
    assert meta["extraction_fallback_backend"] == "pypdf"
    # The classification was right; only the extraction failed.
    assert meta["pdf_type"] == "text_based"
    assert meta["pdf_confidence"] == 1.0
    assert meta["page_count"] == 3
    assert meta["pdf_reader"] == "pdf_inspector"


def test_failed_retry_emits_the_unchanged_inspector_result(monkeypatch, tmp_path):
    """When pypdf also yields no text, the original flagged result stands."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_pypdf_retry(monkeypatch, ["", "", ""])

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == ""
    meta = documents[0].metadata
    assert meta["pages_needing_ocr"] == 3
    assert "pages_needing_ocr_before_fallback" not in meta
    assert "extraction_fallback_backend" not in meta


def test_retry_exception_propagates_to_the_error_boundary(monkeypatch, tmp_path):
    """A pypdf crash on a file pdf-inspector opened is genuinely broken input."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )

    from omrg.integrations.pdf import registry

    class _CrashingReader:
        def load_data(self, file, *args, **kwargs):
            raise ValueError("encrypted or malformed PDF")

    monkeypatch.setitem(registry._cache, "pypdf", _CrashingReader)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ValueError, match="encrypted or malformed"):
        PdfInspectorReader().load_data(file=fake_pdf)


# ── No-retry paths: the guard must never fire outside the contradiction ──


def test_non_empty_markdown_never_retries(monkeypatch, tmp_path):
    """A normal text_based extraction carries no fallback diagnostics."""
    markdown = "# Title\n\nBody text extracted by pdf-inspector."
    _stub_pdf_inspector(
        monkeypatch,
        markdown,
        page_count=3,
        pages_needing_ocr=[1],
    )
    _stub_pypdf_exploding(monkeypatch)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == markdown
    meta = documents[0].metadata
    assert meta["pages_needing_ocr"] == 1
    assert "extraction_fallback_backend" not in meta
    assert "pages_needing_ocr_before_fallback" not in meta


def test_scanned_classification_never_retries(monkeypatch, tmp_path):
    """Non-text_based classifications keep their empty markdown as-is."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        pdf_type="scanned",
        confidence=0.9,
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_pypdf_exploding(monkeypatch)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "scanned.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == ""
    meta = documents[0].metadata
    assert meta["pdf_type"] == "scanned"
    assert meta["pages_needing_ocr"] == 3
    assert "extraction_fallback_backend" not in meta


def test_zero_page_count_never_retries(monkeypatch, tmp_path):
    """An empty file emits no contradiction — nothing was there to read."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=0,
        pages_needing_ocr=[],
    )
    _stub_pypdf_exploding(monkeypatch)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    meta = documents[0].metadata
    assert meta["page_count"] == 0
    assert "extraction_fallback_backend" not in meta
