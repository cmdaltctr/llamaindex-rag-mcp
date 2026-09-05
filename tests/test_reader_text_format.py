"""Reader text-format declarations and pre-read resolution.

Spec: openspec/changes/fix-embedding-and-structure-fidelity-1/
specs/pdf-reader/spec.md — "Readers declare their emitted text format",
plus design D3 (the chunker routes on the declaration; the pipeline
resolves it before the unchanged check) and D5 (``page_provenance`` is
machine-discoverable through the registry descriptor).

Covers tasks 3.3 (pre-read resolver, ``auto`` coverage, the BackendRead
agreement assertion), 4.1-4.3 (PDF registry declarations, ``describe``,
fail-on-omission), and 4.4-4.5 (document-backend declarations and the
format carried on ``BackendRead``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ORCH_LOGGER = "omrg.core.ingestion.backends.orchestrator"


def _pdf_registry():
    """Return the PDF reader registry (lazy, mirrors suite convention)."""
    from omrg.integrations.pdf import registry

    return registry


def _orchestrator():
    """Return the document-backend orchestrator module."""
    from omrg.core.ingestion.backends import orchestrator

    return orchestrator


def _drop_temp_pdf_entries(name: str) -> None:
    """Remove temporary PDF-registry entries from every backing dict."""
    registry = _pdf_registry()
    for attr in ("_registry", "_probe_modules", "_text_formats", "_page_provenance", "_cache"):
        mapping = getattr(registry, attr, None)
        if isinstance(mapping, dict):
            mapping.pop(name, None)


def _azure_settings(effective_settings, pdf_reader: str = "pypdf", **overrides):
    """EffectiveSettings selecting azure with dummy credentials."""
    return effective_settings(
        document_backend="azure",
        azure_doc_intelligence_endpoint="https://example.azure.com/",
        azure_doc_intelligence_key="dummy-key",
        pdf_reader=pdf_reader,
        **overrides,
    )


def _write_pdf(tmp_path: Path) -> Path:
    """Create a stub PDF file (content is never parsed by mocked paths)."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    return pdf


# ── Task 4.2: declared formats and page provenance ─────────────────────


class TestPdfReaderDeclarations:
    """The shipped readers declare the formats the spec pins."""

    @pytest.mark.parametrize(
        ("reader", "text_format"),
        [
            ("pdf_inspector", "markdown"),
            ("liteparse", "plain"),
            ("pypdf", "plain"),
            ("pypdfium2", "plain"),
        ],
    )
    def test_declared_text_formats(self, reader: str, text_format: str) -> None:
        """Spec scenario "Declared formats"."""
        assert _pdf_registry().describe(reader)["text_format"] == text_format

    @pytest.mark.parametrize(
        ("reader", "page_provenance"),
        [
            ("pdf_inspector", False),
            ("liteparse", True),
            ("pypdf", True),
            ("pypdfium2", True),
        ],
    )
    def test_declared_page_provenance(self, reader: str, page_provenance: bool) -> None:
        """Spec scenario "Page support is discoverable"."""
        assert _pdf_registry().describe(reader)["page_provenance"] is page_provenance

    def test_describe_mirrors_document_backend_pattern(self) -> None:
        """Task 4.1 — describe() exposes the declared reader metadata."""
        meta = _pdf_registry().describe("pypdf")
        assert set(meta) == {"import_path", "probe_module", "text_format", "page_provenance"}
        assert meta["import_path"] == "omrg.integrations.pdf.pypdf:PyPDFReader"
        assert meta["probe_module"] == "pypdf"

    def test_describe_unknown_lists_names(self) -> None:
        """An unknown name raises KeyError listing every registered reader."""
        with pytest.raises(KeyError) as excinfo:
            _pdf_registry().describe("no-such-reader")
        message = str(excinfo.value)
        assert "Available" in message
        for name in ("pdf_inspector", "liteparse", "pypdf", "pypdfium2"):
            assert name in message


# ── Task 4.3: registration fails without a declaration ─────────────────


class TestRegistrationRequiresDeclaration:
    """A new reader must declare its format; silence is an error."""

    def test_register_without_text_format_raises(self) -> None:
        """Spec scenario "A new reader must declare a format"."""
        registry = _pdf_registry()
        with pytest.raises(TypeError, match="text_format"):
            registry.register(
                "temp_undeclared",
                "omrg.integrations.pdf.pypdf:PyPDFReader",
                "pypdf",
                page_provenance=True,
            )
        assert "temp_undeclared" not in registry.available()

    def test_register_without_page_provenance_raises(self) -> None:
        """The page capability is equally required, not defaulted."""
        registry = _pdf_registry()
        with pytest.raises(TypeError, match="page_provenance"):
            registry.register(
                "temp_no_pages",
                "omrg.integrations.pdf.pypdf:PyPDFReader",
                "pypdf",
                text_format="plain",
            )
        assert "temp_no_pages" not in registry.available()

    def test_register_with_invalid_format_raises(self) -> None:
        """A format outside plain/markdown fails instead of defaulting."""
        registry = _pdf_registry()
        with pytest.raises(ValueError, match="text_format"):
            registry.register(
                "temp_bogus_format",
                "omrg.integrations.pdf.pypdf:PyPDFReader",
                "pypdf",
                text_format="html",
                page_provenance=True,
            )
        assert "temp_bogus_format" not in registry.available()

    def test_temporary_registration_roundtrip(self) -> None:
        """A fully declared temporary registration is describable."""
        registry = _pdf_registry()
        try:
            registry.register(
                "temp_markdown_reader",
                "omrg.integrations.pdf.pypdf:PyPDFReader",
                text_format="markdown",
                page_provenance=False,
            )
            meta = registry.describe("temp_markdown_reader")
            assert meta["text_format"] == "markdown"
            assert meta["page_provenance"] is False
            assert meta["probe_module"] == "omrg.integrations.pdf.pypdf"
        finally:
            _drop_temp_pdf_entries("temp_markdown_reader")


# ── Task 3.3: the shared pre-read resolver ─────────────────────────────


class TestPreReadResolver:
    """resolve_declared_text_format is the one pre-read resolution policy."""

    def test_local_pdf_reader_declaration_wins_for_pdfs(
        self, effective_settings, fixtures_dir: Path
    ) -> None:
        """A markdown-declaring reader routes its PDFs as markdown."""
        orch = _orchestrator()
        pdf = fixtures_dir / "smoke_text.pdf"
        markdown = orch.resolve_declared_text_format(
            pdf, settings=effective_settings(pdf_reader="pdf_inspector")
        )
        plain = orch.resolve_declared_text_format(
            pdf, settings=effective_settings(pdf_reader="pypdf")
        )
        assert markdown == "markdown"
        assert plain == "plain"

    def test_local_non_pdf_files_are_plain(self, effective_settings, tmp_path: Path) -> None:
        """Non-PDF files under local are plain regardless of the reader."""
        orch = _orchestrator()
        settings = effective_settings(pdf_reader="pdf_inspector")
        txt = tmp_path / "notes.txt"
        txt.write_text("plain prose", encoding="utf-8")
        md = tmp_path / "notes.md"
        md.write_text("# heading", encoding="utf-8")
        assert orch.resolve_declared_text_format(txt, settings=settings) == "plain"
        assert orch.resolve_declared_text_format(md, settings=settings) == "plain"

    def test_azure_declares_plain_for_its_suffixes(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Azure's static declaration applies inside its suffix gate."""
        orch = _orchestrator()
        pdf = _write_pdf(tmp_path)
        assert (
            orch.resolve_declared_text_format(pdf, settings=_azure_settings(effective_settings))
            == "plain"
        )

    def test_gated_file_reports_the_fallback_declaration(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """A `.md` under azure gates to local, which is plain (non-PDF)."""
        orch = _orchestrator()
        md = tmp_path / "notes.md"
        md.write_text("# heading", encoding="utf-8")
        assert (
            orch.resolve_declared_text_format(md, settings=_azure_settings(effective_settings))
            == "plain"
        )

    def test_auto_selector_uses_the_composition_root_resolution(
        self, effective_settings, fixtures_dir: Path
    ) -> None:
        """Direct callers leaving the selector at ``auto`` resolve identically.

        Task 3.3: the pre-read resolver must agree with the composition
        root's ``resolve_pdf_reader`` policy (LiteParse → pypdfium2 →
        pypdf), so a caller that bypassed ``compose`` hashes the same
        ``parser.text_format`` into the identity.
        """
        from omrg.capabilities import resolve_pdf_reader
        from omrg.config import Settings
        from omrg.integrations.pdf.factory import resolve_reader_name

        pdf = fixtures_dir / "smoke_text.pdf"
        composed = resolve_pdf_reader(Settings(_env_file=None, pdf_reader="auto"))
        assert resolve_reader_name("auto") == composed

        settings = effective_settings(pdf_reader="auto")
        resolved = _orchestrator().resolve_declared_text_format(pdf, settings=settings)
        assert resolved == _pdf_registry().describe(composed)["text_format"]


# ── Tasks 4.4-4.5: BackendRead carries the resolved format ─────────────


class TestBackendReadCarriesFormat:
    """``BackendRead.text_format`` mirrors the pre-read resolution."""

    async def test_local_markdown_reader_stamps_markdown(
        self, effective_settings, fixtures_dir: Path
    ) -> None:
        """Task 4.5 — the declaration travels alongside `structured`."""
        orch = _orchestrator()
        settings = effective_settings(pdf_reader="pdf_inspector")
        result = await orch.read_document(fixtures_dir / "smoke_text.pdf", settings=settings)
        assert result.text_format == "markdown"
        assert result.structured is False
        assert result.text_format == orch.resolve_declared_text_format(
            fixtures_dir / "smoke_text.pdf", settings=settings
        )

    async def test_local_plain_reader_stamps_plain(
        self, effective_settings, fixtures_dir: Path
    ) -> None:
        """Task 4.5 — plain readers stamp plain."""
        orch = _orchestrator()
        settings = effective_settings(pdf_reader="pypdf")
        result = await orch.read_document(fixtures_dir / "smoke_text.pdf", settings=settings)
        assert result.text_format == "plain"
        assert result.structured is False

    async def test_azure_read_stamps_plain_and_structured(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Task 4.4 — azure's static declaration rides the structured flag."""
        orch = _orchestrator()
        docs = [MagicMock(name="azure-doc")]
        with patch(
            "omrg.integrations.azure.read_documents",
            AsyncMock(return_value=docs),
        ):
            result = await orch.read_document(
                _write_pdf(tmp_path), settings=_azure_settings(effective_settings)
            )
        assert result.structured is True
        assert result.text_format == "plain"

    async def test_disagreement_with_pre_read_resolver_fails_loudly(
        self, effective_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Design D3 — BackendRead verifies the pre-resolved value.

        When the stamped format diverges from the pre-read resolver on a
        clean (non-degraded) read, the read fails instead of silently
        mis-routing the chunker and hashing a stale identity.
        """
        orch = _orchestrator()
        monkeypatch.setattr(
            orch,
            "resolve_declared_text_format",
            lambda file_path, *, settings: "markdown",
        )
        settings = effective_settings(pdf_reader="pypdf")
        with pytest.raises(RuntimeError, match="text_format"):
            await orch.read_document(_write_pdf(tmp_path), settings=settings)

    async def test_unavailable_degradation_substitutes_the_fallback_format(
        self,
        effective_settings,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Wholesale degradation warns and adopts the fallback's format.

        Azure is selected (declares plain) but unavailable; the read
        degrades to the local chain whose PDF reader declares markdown.
        The read succeeds, the substitution is visible in the log, and no
        agreement error fires — the identity is stale, not the read.
        """
        orch = _orchestrator()
        docs = [MagicMock(name="local-doc")]
        with (
            patch(
                "omrg.integrations.azure.read_documents",
                AsyncMock(side_effect=ImportError("azure-ai-documentintelligence missing")),
            ),
            patch(
                "omrg.core.ingestion.backends.local.read_documents",
                AsyncMock(return_value=docs),
            ),
            caplog.at_level(logging.WARNING, logger=_ORCH_LOGGER),
        ):
            result = await orch.read_document(
                _write_pdf(tmp_path),
                settings=_azure_settings(effective_settings, pdf_reader="pdf_inspector"),
            )
        assert result.structured is False
        assert result.text_format == "markdown"
        warning_text = " ".join(
            record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
        )
        assert "differs from the pre-resolved" in warning_text
