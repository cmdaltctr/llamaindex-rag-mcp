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


def _stub_liteparse_retry(monkeypatch, page_texts: list[str]) -> None:
    """Seed the registry cache with a stub LiteParse fallback reader."""
    from llama_index.core import Document

    from omrg.integrations.pdf import registry

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            self.ocr_enabled = ocr_enabled
            self.num_workers = num_workers

        def load_data(self, file, *args, **kwargs):
            return [Document(text=text) for text in page_texts]

    monkeypatch.setitem(registry._cache, "liteparse", _StubLiteParseReader)


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


def _stub_liteparse_exploding(monkeypatch) -> None:
    """Seed a LiteParse tier that fails if a no-retry path invokes it."""
    from omrg.integrations.pdf import registry

    class _ExplodingReader:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            self.ocr_enabled = ocr_enabled
            self.num_workers = num_workers

        def load_data(self, file, *args, **kwargs):
            raise AssertionError("liteparse retry must not run on this path")

    monkeypatch.setitem(registry._cache, "liteparse", _ExplodingReader)


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


# ── Sloman guard: text_based-but-empty contradiction retries by tier ──


def test_contradiction_retries_with_liteparse_before_pypdf_and_recovers_text(monkeypatch, tmp_path):
    """A contradiction joins the LiteParse tier and names it honestly."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, ["lite page one", "lite page two", "lite page three"])
    _stub_pypdf_retry(monkeypatch, ["pypdf must not be selected"])

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == "lite page one\n\nlite page two\n\nlite page three"
    assert documents[0].metadata["extraction_fallback_backend"] == "liteparse"


def test_unavailable_liteparse_falls_through_to_pypdf(monkeypatch, tmp_path):
    """An unavailable LiteParse tier hands over to the registered pypdf tier."""
    from llama_index.core import Document

    from omrg.integrations.pdf import registry
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=2, pages_needing_ocr=[0, 1])
    calls: list[str] = []

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf page one"), Document(text="pypdf page two")]

    def _get_reader(name: str):
        calls.append(name)
        if name == "liteparse":
            raise ImportError("liteparse is not installed")
        assert name == "pypdf"
        return _StubPypdfReader

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    document = PdfInspectorReader().load_data(file=fake_pdf)[0]

    assert calls == ["liteparse", "pypdf"]
    assert document.get_content() == "pypdf page one\n\npypdf page two"
    assert document.metadata["extraction_fallback_backend"] == "pypdf"


@pytest.mark.parametrize("liteparse_failure", ["raises", "empty"])
def test_failed_liteparse_tier_hands_over_to_pypdf(monkeypatch, tmp_path, liteparse_failure):
    """A LiteParse exception or empty result must not block the pypdf rescue."""
    from llama_index.core import Document

    from omrg.integrations.pdf import registry
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=2, pages_needing_ocr=[0, 1])
    calls: list[str] = []

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None) -> None:
            assert ocr_enabled is False
            assert num_workers is None

        def load_data(self, file, *args, **kwargs):
            if liteparse_failure == "raises":
                raise ValueError("LiteParse could not read this PDF")
            return [Document(text=""), Document(text="")]

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf rescue")]

    def _get_reader(name: str):
        calls.append(name)
        return {"liteparse": _StubLiteParseReader, "pypdf": _StubPypdfReader}[name]

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    document = PdfInspectorReader().load_data(file=fake_pdf)[0]

    assert calls == ["liteparse", "pypdf"]
    assert document.get_content() == "pypdf rescue"
    assert document.metadata["extraction_fallback_backend"] == "pypdf"


def test_recovered_text_corrects_the_routing_evidence(monkeypatch, tmp_path):
    """A successful retry zeroes the flagged count and keeps the original."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, [""] * 3)
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


def test_both_tiers_empty_emit_the_unchanged_inspector_result(monkeypatch, tmp_path):
    """When both tiers yield no text, the original flagged result stands."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, ["", "", ""])
    _stub_pypdf_retry(monkeypatch, ["", "", ""])

    from omrg.integrations.pdf import registry
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    calls: list[str] = []
    registered_get = registry.get

    def _get_reader(name: str):
        calls.append(name)
        return registered_get(name)

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert calls == ["liteparse", "pypdf"]
    assert len(documents) == 1
    assert documents[0].get_content() == ""
    meta = documents[0].metadata
    assert meta["pages_needing_ocr"] == 3
    assert "pages_needing_ocr_before_fallback" not in meta
    assert "extraction_fallback_backend" not in meta


def test_retry_exception_propagates_to_the_error_boundary(monkeypatch, tmp_path):
    """A last-tier pypdf crash on an opened file reaches the error boundary."""
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

    _stub_liteparse_retry(monkeypatch, ["", "", ""])
    monkeypatch.setitem(registry._cache, "pypdf", _CrashingReader)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ValueError, match="encrypted or malformed"):
        PdfInspectorReader().load_data(file=fake_pdf)


def test_liteparse_retry_forces_ocr_disabled(monkeypatch, tmp_path, effective_settings):
    """The rescue tier disables LiteParse OCR despite an operator default."""
    from llama_index.core import Document

    from omrg.core.settings import set_default_effective_settings
    from omrg.integrations.pdf import registry
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    set_default_effective_settings(effective_settings(liteparse_ocr_enabled=True))
    _stub_pdf_inspector(monkeypatch, "", page_count=1, pages_needing_ocr=[0])
    observed_settings: list[tuple[bool, int | None]] = []

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None) -> None:
            observed_settings.append((ocr_enabled, num_workers))

        def load_data(self, file, *args, **kwargs):
            return [Document(text="extraction-only rescue")]

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf must not be selected")]

    monkeypatch.setitem(registry._cache, "liteparse", _StubLiteParseReader)
    monkeypatch.setitem(registry._cache, "pypdf", _StubPypdfReader)

    document = PdfInspectorReader().load_data(file=tmp_path / "sloman.pdf")[0]

    assert observed_settings == [(False, None)]
    assert document.get_content() == "extraction-only rescue"
    assert document.metadata["extraction_fallback_backend"] == "liteparse"


def test_liteparse_rescue_does_not_require_default_settings(monkeypatch, tmp_path):
    """A bare adapter call stays on liteparse without composed settings."""
    from omrg.core.settings import reset_default_effective_settings
    from omrg.integrations.pdf import registry
    from omrg.integrations.pdf.liteparse import LiteParseReader
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=1, pages_needing_ocr=[0])
    observed_settings: list[tuple[bool, int | None, bool]] = []

    class _StubLiteParse:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None, quiet: bool) -> None:
            observed_settings.append((ocr_enabled, num_workers, quiet))

        def parse(self, file):
            item = MagicMock(text="standalone liteparse rescue")
            item.x = item.y = 0.0
            item.width = item.height = 10.0
            page = MagicMock(page_num=1, text_items=[item])
            return MagicMock(pages=[page])

    stub_module = MagicMock(LiteParse=_StubLiteParse)
    monkeypatch.setitem(sys.modules, "liteparse", stub_module)
    monkeypatch.setitem(registry._cache, "liteparse", LiteParseReader)
    _stub_pypdf_exploding(monkeypatch)
    reset_default_effective_settings()

    fake_pdf = tmp_path / "standalone.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    document = PdfInspectorReader().load_data(file=fake_pdf)[0]

    assert observed_settings == [(False, None, True)]
    assert document.get_content() == "standalone liteparse rescue"
    assert document.metadata["extraction_fallback_backend"] == "liteparse"


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
    _stub_liteparse_exploding(monkeypatch)
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
    _stub_liteparse_exploding(monkeypatch)
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
    _stub_liteparse_exploding(monkeypatch)
    _stub_pypdf_exploding(monkeypatch)

    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    meta = documents[0].metadata
    assert meta["page_count"] == 0
    assert "extraction_fallback_backend" not in meta
