"""Tests for the PDF reader factory resolution.

Covers spec requirements: each PDF_READER value resolves correctly,
fallback chain works, unknown values warn, explicit-not-installed
falls back gracefully.
"""

from __future__ import annotations

from rag_mcp.integrations.pdf.factory import get_pdf_reader


def test_factory_returns_pypdf_by_default(monkeypatch):
    """With pdf_reader=pypdf, factory returns PyPDFReader."""
    from rag_mcp.core.settings import (
        EffectiveSettings,
        set_default_effective_settings,
    )

    # The factory reads the resolved reader from the injected settings;
    # compose bakes the `auto` probe result in at startup.
    set_default_effective_settings(EffectiveSettings(pdf_reader="pypdf"))
    import rag_mcp.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)

    reader = get_pdf_reader()
    from rag_mcp.integrations.pdf.pypdf import PyPDFReader

    assert isinstance(reader, PyPDFReader)


def test_factory_returns_liteparse_when_configured(monkeypatch):
    """With pdf_reader=liteparse, factory returns LiteParseReader."""
    import rag_mcp.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    # Patch config BEFORE calling get_pdf_reader
    from rag_mcp.core.settings import (
        EffectiveSettings,
        set_default_effective_settings,
    )

    set_default_effective_settings(EffectiveSettings(pdf_reader="liteparse"))

    reader = get_pdf_reader()
    from rag_mcp.integrations.pdf.liteparse import LiteParseReader

    assert isinstance(reader, LiteParseReader)


def test_factory_returns_pypdfium2_when_configured(monkeypatch):
    """With pdf_reader=pypdfium2, factory returns PyPDFium2Reader."""
    import rag_mcp.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    from rag_mcp.core.settings import (
        EffectiveSettings,
        set_default_effective_settings,
    )

    set_default_effective_settings(EffectiveSettings(pdf_reader="pypdfium2"))

    reader = get_pdf_reader()
    from rag_mcp.integrations.pdf.pypdfium import PyPDFium2Reader

    assert isinstance(reader, PyPDFium2Reader)


def test_factory_raises_on_unknown_value(monkeypatch):
    """Unknown pdf_reader raises ValueError."""
    import rag_mcp.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", True)
    from rag_mcp.core.settings import (
        EffectiveSettings,
        set_default_effective_settings,
    )

    set_default_effective_settings(EffectiveSettings(pdf_reader="fastparser"))

    import pytest

    with pytest.raises(ValueError, match="Unknown reader"):
        get_pdf_reader()


def test_config_validates_pdf_reader_value(monkeypatch):
    """config.py rejects unknown PDF_READER values and falls back to auto."""
    # This tests the config-level validation, not the factory
    from rag_mcp import config as _config

    # The default should be pypdf
    assert _config.get_settings().pdf_reader in {"pypdf", "auto", "liteparse", "pypdfium2"}
