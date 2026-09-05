"""Tests for the PDF reader factory resolution.

Covers spec requirements: each reader name resolves correctly, the
factory-local ``auto`` probe matches the composition-root preference order
(``liteparse → pypdfium2 → pypdf``), unknown values raise, and the factory
receives the reader name as a parameter instead of fetching the
composition-root default. The registry-metadata section covers the
modularity contract that a registered selector resolves through the
registry's own import-path metadata, whatever its name spells.
"""

from __future__ import annotations

import sys

import pytest

from omrg.integrations.pdf.factory import get_pdf_reader


@pytest.fixture(autouse=True)
def _reset_logged(monkeypatch):
    """Start each test with an empty log-once set."""
    import omrg.integrations.pdf.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_pdf_reader_logged", set())


def test_factory_returns_pypdf_when_passed():
    """pdf_reader=pypdf passed by the caller returns PyPDFReader."""
    from omrg.integrations.pdf.pypdf import PyPDFReader

    assert isinstance(get_pdf_reader("pypdf"), PyPDFReader)


def test_factory_returns_liteparse_when_passed():
    """pdf_reader=liteparse passed by the caller returns LiteParseReader."""
    from omrg.integrations.pdf.liteparse import LiteParseReader

    assert isinstance(get_pdf_reader("liteparse"), LiteParseReader)


def test_factory_returns_pypdfium2_when_passed():
    """pdf_reader=pypdfium2 passed by the caller returns PyPDFium2Reader."""
    from omrg.integrations.pdf.pypdfium import PyPDFium2Reader

    assert isinstance(get_pdf_reader("pypdfium2"), PyPDFium2Reader)


def test_factory_returns_pdf_inspector_when_passed():
    """pdf_reader=pdf_inspector passed by the caller returns PdfInspectorReader.

    Spec: pdf-reader delta (promote-pdf-inspector-default-reader), scenario
    "Explicit pdf-inspector selection via env var" — the adapter half: the
    resolved name SHALL dispatch to its adapter. The adapter import is lazy
    (ADR-024 pattern), so construction does not require the pdf-inspector
    distribution — same shape as the pypdfium2 test above.
    """
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    assert isinstance(get_pdf_reader("pdf_inspector"), PdfInspectorReader)


def test_factory_requires_reader_argument():
    """The reader name is a required parameter — no default pull."""
    with pytest.raises(TypeError):
        get_pdf_reader()


def test_factory_module_has_no_default_settings_lookup():
    """Contract: factory.py contains no composition-root default fetch."""
    from pathlib import Path

    import omrg.integrations.pdf.factory as factory_mod

    source = Path(factory_mod.__file__).read_text(encoding="utf-8")
    assert "get_default_effective_settings" not in source


def test_factory_raises_on_unknown_value():
    """Unknown reader name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown reader"):
        get_pdf_reader("fastparser")


def test_factory_auto_prefers_pypdfium2_when_liteparse_missing(monkeypatch):
    """auto resolves to pypdfium2 when liteparse is not importable."""
    import types

    from omrg.integrations.pdf.pypdfium import PyPDFium2Reader

    # Poisoning sys.modules with None makes `import liteparse` raise
    # ImportError; a stub module makes `import pypdfium2` succeed. The
    # adapter imports pypdfium2 lazily, so construction never touches it.
    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", types.ModuleType("pypdfium2"))
    assert isinstance(get_pdf_reader("auto"), PyPDFium2Reader)


def test_factory_auto_prefers_liteparse_when_pdf_inspector_available(monkeypatch):
    """auto stays liteparse-first even when pdf_inspector is importable.

    Spec: pdf-reader delta (promote-pdf-inspector-default-reader) — the
    promotion changes the packaged default only. The factory-local auto
    policy SHALL NOT gain pdf_inspector in its preference order.
    """
    import types

    from omrg.integrations.pdf.liteparse import LiteParseReader

    monkeypatch.setitem(sys.modules, "liteparse", types.ModuleType("liteparse"))
    monkeypatch.setitem(sys.modules, "pdf_inspector", types.ModuleType("pdf_inspector"))
    assert isinstance(get_pdf_reader("auto"), LiteParseReader)


def test_factory_auto_ignores_pdf_inspector_when_optionals_missing(monkeypatch):
    """auto must not fall back to pdf_inspector when the probed optionals are absent.

    Spec: pdf-reader delta (promote-pdf-inspector-default-reader) —
    design non-goal: ``auto`` keeps the LiteParse → pypdfium2 → pypdf
    capability policy. The sharpest probe for that non-goal is this
    world: pdf_inspector importable while liteparse and pypdfium2 are
    absent must still yield pypdf, never PdfInspectorReader.
    """
    import types

    from omrg.integrations.pdf.pypdf import PyPDFReader

    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    monkeypatch.setitem(sys.modules, "pdf_inspector", types.ModuleType("pdf_inspector"))
    assert isinstance(get_pdf_reader("auto"), PyPDFReader)


def test_factory_auto_falls_back_to_pypdf_when_no_optional_installed(monkeypatch):
    """auto resolves to pypdf when neither optional backend imports."""
    from omrg.integrations.pdf.pypdf import PyPDFReader

    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    assert isinstance(get_pdf_reader("auto"), PyPDFReader)


def test_factory_auto_matches_compose_resolution(monkeypatch):
    """Contract: factory-local auto and compose resolve identically.

    Spec: pdf-reader — factory-local auto resolution SHALL match what the
    composition root would resolve for the same installed packages.
    """
    import types

    from omrg.compose import resolve_pdf_reader
    from omrg.integrations.pdf.factory import get_pdf_reader as factory_get

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

    with caplog.at_level(logging.INFO, logger="omrg.integrations.pdf.factory"):
        get_pdf_reader("pypdf")
        get_pdf_reader("pypdf")
    backend_lines = [r for r in caplog.records if "PDF reader backend" in r.message]
    assert len(backend_lines) == 1


# ── Registry-owned resolution (CodeRabbit modularity finding) ──────────────
#
# compose.resolve_pdf_reader probes concrete readers with
# ``__import__(reader)`` — importing a module named identically to the
# registry key. Every shipped reader satisfies that coupling by accident
# (selector name == pip package name == registry key). The spec contract
# ("Reader factory SHALL be extensible without modifying ingestion code",
# scenario "Adding a new adapter") promises that one ``register()`` call
# makes ``PDF_READER=<name>`` functional for ANY name: the registry's
# ``"module:ClassName"`` entry is the resolution metadata, and selection
# SHALL consult it rather than importing the selector's name.
#
# The aliases below deliberately break the name/module coincidence to pin
# that contract. These tests are the failing coverage for the finding.

_ALIAS = "enterprise_pdf"  # no importable top-level module shares this name
_ALIAS_PATH = "omrg.integrations.pdf.pypdf:PyPDFReader"
_GHOST = "ghost_pdf_alias"  # imports fine; its registry module does not exist
_GHOST_PATH = "omrg.integrations.pdf.ghost_module:GhostReader"


@pytest.fixture
def pdf_registry_sandbox():
    """Isolate global pdf-registry mutations to the requesting test.

    ``registry._registry``/``_cache`` are module-level dicts shared with
    ``test_strategy_registration_inventory.py`` (which asserts the exact
    advertised name set), so alias registrations must never leak.
    """
    from omrg.integrations.pdf import registry as pdf_registry

    state_attrs = ("_registry", "_probe_modules", "_text_formats", "_page_provenance", "_cache")
    saved = {attr: dict(getattr(pdf_registry, attr)) for attr in state_attrs}
    yield pdf_registry
    for attr in state_attrs:
        mapping = getattr(pdf_registry, attr)
        mapping.clear()
        mapping.update(saved[attr])


def _reader_settings(name: str):
    """Minimal settings stand-in carrying only ``pdf_reader``."""
    import types

    return types.SimpleNamespace(pdf_reader=name)


def test_registered_alias_resolves_via_registry_metadata(pdf_registry_sandbox, monkeypatch):
    """A registered selector whose name differs from its import module resolves.

    Spec: pdf-reader, requirement "Reader factory SHALL be extensible
    without modifying ingestion code", scenario "Adding a new adapter":
    one ``register("spdf", ...)`` call SHALL make ``PDF_READER=spdf``
    functional with no other source change. The composition root SHALL
    therefore answer from the registry's import-path metadata — a selector
    name that is itself unimportable must still resolve when its
    registered adapter module exists.
    """
    import omrg.compose as compose

    pdf_registry_sandbox.register(_ALIAS, _ALIAS_PATH, text_format="plain", page_provenance=True)
    # Poison the name: `import enterprise_pdf` raises ImportError, while
    # the registry-owned path omrg.integrations.pdf.pypdf imports fine.
    monkeypatch.setitem(sys.modules, _ALIAS, None)

    assert compose.resolve_pdf_reader(_reader_settings(_ALIAS)) == _ALIAS


def test_alias_with_missing_registry_module_falls_back_to_pypdf_with_error(
    pdf_registry_sandbox, monkeypatch, caplog
):
    """A registered selector whose registry module is missing falls back safely.

    Spec: pdf-reader, scenario "Missing configured backend falls back
    safely": the system SHALL log an error naming the configured reader
    and fall back to pypdf rather than raising. The inversion here
    isolates the modularity bug: the selector NAME imports (so a
    name-coupled probe blesses it) but the registry-owned module does not
    exist — resolution guided by registry metadata is what must detect
    the loss and fall back.
    """
    import logging
    import types

    import omrg.compose as compose

    pdf_registry_sandbox.register(_GHOST, _GHOST_PATH, text_format="plain", page_provenance=True)
    monkeypatch.setitem(sys.modules, _GHOST, types.ModuleType(_GHOST))

    with caplog.at_level(logging.ERROR, logger="omrg.compose"):
        assert compose.resolve_pdf_reader(_reader_settings(_GHOST)) == "pypdf"
    assert any(_GHOST in record.message and "pypdf" in record.message for record in caplog.records)


def test_factory_dispatches_registered_alias_via_registry_metadata(
    pdf_registry_sandbox, monkeypatch
):
    """The factory half of the extensibility contract: alias dispatch works.

    Spec: pdf-reader, requirement "Reader factory SHALL be extensible
    without modifying ingestion code" — ``get_pdf_reader`` already
    resolves through ``registry.get`` (the registry-owned import path),
    so a registered alias must construct the class its metadata names
    even when the alias itself is not importable. Pins that the
    name-coupling violation is localised to the composition root.
    """
    from omrg.integrations.pdf.pypdf import PyPDFReader

    pdf_registry_sandbox.register(_ALIAS, _ALIAS_PATH, text_format="plain", page_provenance=True)
    monkeypatch.setitem(sys.modules, _ALIAS, None)

    reader = get_pdf_reader(_ALIAS)
    assert isinstance(reader, PyPDFReader)
    assert callable(reader.load_data)


def test_compose_auto_stays_liteparse_first_with_pypdfium2_available(monkeypatch):
    """Auto keeps the LiteParse-first preference while aliases exist.

    Spec: pdf-reader, requirement "Auto resolution SHALL probe backends in
    preference order", scenario "LiteParse installed and selected by
    auto". Guard for the registry-metadata fix: making explicit selectors
    resolve via registry metadata SHALL NOT touch the auto policy — with
    liteparse and pypdfium2 both importable, auto resolves to liteparse
    on both the composition-root and factory paths.
    """
    import types

    import omrg.compose as compose
    from omrg.integrations.pdf.liteparse import LiteParseReader

    monkeypatch.setitem(sys.modules, "liteparse", types.ModuleType("liteparse"))
    monkeypatch.setitem(sys.modules, "pypdfium2", types.ModuleType("pypdfium2"))

    assert compose.resolve_pdf_reader(_reader_settings("auto")) == "liteparse"
    assert isinstance(get_pdf_reader("auto"), LiteParseReader)
