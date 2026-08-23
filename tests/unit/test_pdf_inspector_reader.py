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


def test_adapter_module_imports_pdf_inspector_lazily():
    """Importing the adapter module must not import the optional package."""
    sys.modules.pop("pdf_inspector", None)

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
    """Without pdf_inspector installed, load_data raises an ImportError naming the extra."""
    monkeypatch.setitem(sys.modules, "pdf_inspector", None)

    from rag_mcp.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ImportError) as excinfo:
        PdfInspectorReader().load_data(file=fake_pdf)

    message = str(excinfo.value)
    assert "pdf-inspector" in message
    assert "install" in message.lower()
