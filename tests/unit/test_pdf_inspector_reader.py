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

from rag_mcp.integrations.pdf.factory import get_pdf_reader
from rag_mcp.integrations.pdf.registry import available as available_readers


def _stub_pdf_inspector(monkeypatch, markdown: str) -> None:
    """Install a fake ``pdf_inspector`` module in ``sys.modules``.

    The stub mirrors the real package API: ``process_pdf(path)`` returns
    an object carrying ``markdown`` and ``pdf_type`` attributes. A
    MagicMock backs the module so any import shape the adapter uses
    resolves without the package installed.
    """
    stub = MagicMock()
    result = stub.process_pdf.return_value
    result.markdown = markdown
    result.pdf_type = "text_based"
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)


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

    importlib.import_module("rag_mcp.integrations.pdf.pdf_inspector")

    assert "pdf_inspector" not in sys.modules


def test_load_data_passthroughs_mock_markdown(monkeypatch, tmp_path):
    """With pdf_inspector stubbed, load_data returns Documents carrying the markdown."""
    markdown = "# Title\n\nBody text extracted by pdf-inspector."
    _stub_pdf_inspector(monkeypatch, markdown)

    from rag_mcp.integrations.pdf.pdf_inspector import PdfInspectorReader

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

    from rag_mcp.integrations.pdf.pdf_inspector import PdfInspectorReader

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

    from rag_mcp.integrations.pdf.pdf_inspector import PdfInspectorReader

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
