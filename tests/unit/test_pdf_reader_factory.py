"""Tests for the PDF reader factory resolution.

Covers spec requirements: each reader name resolves correctly, the
factory-local ``auto`` probe matches the composition-root preference order
(``liteparse → pypdfium2 → pypdf``), unknown values raise, and the factory
receives the reader name as a parameter instead of fetching the
composition-root default.
"""

from __future__ import annotations

import sys

import pytest

from rag_mcp.integrations.pdf.factory import get_pdf_reader


@pytest.fixture(autouse=True)
def _reset_logged(monkeypatch):
    """Start each test with an empty log-once set."""
    import rag_mcp.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", set())


def test_factory_returns_pypdf_when_passed():
    """pdf_reader=pypdf passed by the caller returns PyPDFReader."""
    from rag_mcp.integrations.pdf.pypdf import PyPDFReader

    assert isinstance(get_pdf_reader("pypdf"), PyPDFReader)


def test_factory_returns_liteparse_when_passed():
    """pdf_reader=liteparse passed by the caller returns LiteParseReader."""
    from rag_mcp.integrations.pdf.liteparse import LiteParseReader

    assert isinstance(get_pdf_reader("liteparse"), LiteParseReader)


def test_factory_returns_pypdfium2_when_passed():
    """pdf_reader=pypdfium2 passed by the caller returns PyPDFium2Reader."""
    from rag_mcp.integrations.pdf.pypdfium import PyPDFium2Reader

    assert isinstance(get_pdf_reader("pypdfium2"), PyPDFium2Reader)


def test_factory_requires_reader_argument():
    """The reader name is a required parameter — no default pull."""
    with pytest.raises(TypeError):
        get_pdf_reader()


def test_factory_module_has_no_default_settings_lookup():
    """Contract: factory.py contains no composition-root default fetch."""
    from pathlib import Path

    import rag_mcp.integrations.pdf.factory as factory_mod

    source = Path(factory_mod.__file__).read_text(encoding="utf-8")
    assert "get_default_effective_settings" not in source


def test_factory_raises_on_unknown_value():
    """Unknown reader name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown reader"):
        get_pdf_reader("fastparser")


def test_factory_auto_prefers_pypdfium2_when_liteparse_missing(monkeypatch):
    """auto resolves to pypdfium2 when liteparse is not importable."""
    import types

    from rag_mcp.integrations.pdf.pypdfium import PyPDFium2Reader

    # Poisoning sys.modules with None makes `import liteparse` raise
    # ImportError; a stub module makes `import pypdfium2` succeed. The
    # adapter imports pypdfium2 lazily, so construction never touches it.
    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", types.ModuleType("pypdfium2"))
    assert isinstance(get_pdf_reader("auto"), PyPDFium2Reader)


def test_factory_auto_falls_back_to_pypdf_when_no_optional_installed(monkeypatch):
    """auto resolves to pypdf when neither optional backend imports."""
    from rag_mcp.integrations.pdf.pypdf import PyPDFReader

    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    assert isinstance(get_pdf_reader("auto"), PyPDFReader)


def test_factory_auto_matches_compose_resolution(monkeypatch):
    """Contract: factory-local auto and compose resolve identically.

    Spec: pdf-reader — factory-local auto resolution SHALL match what the
    composition root would resolve for the same installed packages.
    """
    import types

    from rag_mcp.compose import resolve_pdf_reader
    from rag_mcp.integrations.pdf.factory import get_pdf_reader as factory_get

    class_by_name = {
        "pypdf": "PyPDFReader",
        "pypdfium2": "PyPDFium2Reader",
        "liteparse": "LiteParseReader",
    }

    settings_ns = types.SimpleNamespace(pdf_reader="auto")

    # World 1: environment as-is.
    expected = resolve_pdf_reader(settings_ns)
    reader_cls = factory_get("auto")
    assert type(reader_cls).__name__ == class_by_name[expected]

    # World 2: liteparse missing, pypdfium2 importable.
    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", types.ModuleType("pypdfium2"))
    expected = resolve_pdf_reader(settings_ns)
    reader_cls = factory_get("auto")
    assert type(reader_cls).__name__ == class_by_name[expected]

    # World 3: both optional backends missing.
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    expected = resolve_pdf_reader(settings_ns)
    reader_cls = factory_get("auto")
    assert type(reader_cls).__name__ == class_by_name[expected]


def test_factory_logs_backend_once_per_name(caplog):
    """The backend log line fires once per distinct reader name."""
    import logging

    with caplog.at_level(logging.INFO, logger="rag_mcp.integrations.pdf.factory"):
        get_pdf_reader("pypdf")
        get_pdf_reader("pypdf")
    backend_lines = [r for r in caplog.records if "PDF reader backend" in r.message]
    assert len(backend_lines) == 1
