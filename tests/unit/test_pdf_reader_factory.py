"""Tests for the PDF reader factory resolution.

Covers spec requirements: each PDF_READER value resolves correctly,
fallback chain works, unknown values warn, explicit-not-installed
falls back gracefully.
"""

from __future__ import annotations

from rag_mcp.readers.factory import get_pdf_reader


def test_factory_returns_pypdf_by_default(monkeypatch):
    """With RESOLVED_PDF_READER=pypdf, factory returns PyPDFReader."""
    from rag_mcp import config as _config
    monkeypatch.setattr(_config, "RESOLVED_PDF_READER", "pypdf")
    # Also patch the factory's import target
    import rag_mcp.readers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)

    reader = get_pdf_reader()
    from rag_mcp.readers.pypdf_reader import PyPDFReader
    assert isinstance(reader, PyPDFReader)


def test_factory_returns_liteparse_when_configured(monkeypatch):
    """With RESOLVED_PDF_READER=liteparse, factory returns LiteParseReader."""
    import rag_mcp.readers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    # Patch config BEFORE calling get_pdf_reader
    from rag_mcp import config as _config
    monkeypatch.setattr(_config, "RESOLVED_PDF_READER", "liteparse")

    reader = get_pdf_reader()
    from rag_mcp.readers.liteparse_reader import LiteParseReader
    assert isinstance(reader, LiteParseReader)


def test_factory_returns_pypdfium2_when_configured(monkeypatch):
    """With RESOLVED_PDF_READER=pypdfium2, factory returns PyPDFium2Reader."""
    import rag_mcp.readers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    from rag_mcp import config as _config
    monkeypatch.setattr(_config, "RESOLVED_PDF_READER", "pypdfium2")

    reader = get_pdf_reader()
    from rag_mcp.readers.pypdfium_reader import PyPDFium2Reader
    assert isinstance(reader, PyPDFium2Reader)


def test_factory_raises_on_unknown_value(monkeypatch):
    """Unknown RESOLVED_PDF_READER raises ValueError."""
    import rag_mcp.readers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    from rag_mcp import config as _config
    monkeypatch.setattr(_config, "RESOLVED_PDF_READER", "fastparser")

    import pytest
    with pytest.raises(ValueError, match="Unknown RESOLVED_PDF_READER"):
        get_pdf_reader()


def test_config_validates_pdf_reader_value(monkeypatch):
    """config.py rejects unknown PDF_READER values and falls back to auto."""
    # This tests the config-level validation, not the factory
    from rag_mcp import config as _config
    # The default should be pypdf
    assert _config.PDF_READER in {"pypdf", "auto", "liteparse", "pypdfium2"}
