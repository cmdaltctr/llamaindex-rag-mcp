"""Page-provenance contract (fix-embedding-and-structure-fidelity-1).

Spec: openspec/changes/fix-embedding-and-structure-fidelity-1/specs/
pdf-reader/spec.md — "Page provenance is honest per reader".

Readers that can observe page boundaries SHALL emit ``page_label`` (the
key retrieval reads) as a string alongside the existing integer ``page``.
``pdf_inspector`` returns one document for the whole file and genuinely
cannot know the page, so it MUST emit nothing rather than a placeholder
while still reporting ``page_count``. The registry descriptor exposes
the capability (``page_provenance``) and the configuration guide's
per-reader matrix must agree with it (task 6.5).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_GUIDE = _REPO_ROOT / "docs" / "guides" / "configuration.md"


# ── Stub plumbing for pypdfium2 (not installed in the base venv) ───────


def _install_fake_pypdfium2(monkeypatch: pytest.MonkeyPatch, page_texts: list[str]) -> None:
    """Install a fake ``pypdfium2`` module in ``sys.modules``.

    The stub mirrors the adapter's narrow API surface (``PdfDocument``
    supporting ``len``, indexing, and ``close``; pages exposing
    ``get_textpage().get_text_range()``) so the REAL adapter code runs.
    ``monkeypatch.setitem`` restores any prior entry on teardown.
    """
    import types

    class _FakeTextPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_text_range(self) -> str:
            return self._text

    class _FakePdfPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_textpage(self) -> _FakeTextPage:
            return _FakeTextPage(self._text)

    class _FakePdfDocument:
        def __init__(self, path: str) -> None:
            self._pages = [_FakePdfPage(text) for text in page_texts]

        def __len__(self) -> int:
            return len(self._pages)

        def __getitem__(self, index: int) -> _FakePdfPage:
            return self._pages[index]

        def close(self) -> None:
            return None

    stub = types.ModuleType("pypdfium2")
    stub.PdfDocument = _FakePdfDocument  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pypdfium2", stub)


# ── Task 1.4 / 6.1: liteparse and pypdfium2 emit page_label ───────────


class TestLiteParsePageLabel:
    """liteparse knows the page number; it must say so (spec scenario)."""

    def test_emits_string_page_label_alongside_integer_page(self, fixtures_dir: Path) -> None:
        """Each emitted document carries a string page_label next to int page."""
        from omrg.integrations.pdf.liteparse import LiteParseReader

        documents = LiteParseReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert documents, "smoke_text.pdf must parse to at least one page document"
        for doc in documents:
            meta = doc.metadata
            assert "page" in meta, f"integer page missing: {sorted(meta)}"
            assert isinstance(meta["page"], int)
            assert "page_label" in meta, (
                f"page_label missing (page_provenance is declared true): {sorted(meta)}"
            )
            assert isinstance(meta["page_label"], str)
            # pypdf's existing format: the 1-based page number as a string.
            assert meta["page_label"] == str(meta["page"])


class TestPypdfium2PageLabel:
    """pypdfium2 paginates per page; it must emit page_label (spec scenario)."""

    def test_emits_string_page_label_alongside_integer_page(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Each emitted page document carries a string page_label next to int page."""
        _install_fake_pypdfium2(
            monkeypatch,
            [
                "First page text with enough content to survive chunking.",
                "Second page text with enough content to survive chunking.",
            ],
        )
        from omrg.integrations.pdf.pypdfium import PyPDFium2Reader

        pdf = tmp_path / "two_page.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        documents = PyPDFium2Reader().load_data(file=pdf)

        assert len(documents) == 2
        for index, doc in enumerate(documents, start=1):
            meta = doc.metadata
            assert meta["page"] == index
            assert isinstance(meta["page"], int)
            assert "page_label" in meta, (
                f"page_label missing (page_provenance is declared true): {sorted(meta)}"
            )
            assert isinstance(meta["page_label"], str)
            assert meta["page_label"] == str(index)


class TestAutoChainPreservesPageLabel:
    """A chunk retrieved through the ``auto`` chain keeps its page_label."""

    async def test_chunk_retrieved_through_auto_keeps_page_label(
        self,
        monkeypatch: pytest.MonkeyPatch,
        effective_settings,
        fixtures_dir: Path,
    ) -> None:
        """auto → pypdfium2 → stored chunk metadata carries page_label.

        Spec scenario "pypdfium2 emits page_label": a chunk retrieved
        through the ``auto`` chain MUST preserve it. liteparse is poisoned
        so the capability probe falls through to the stubbed pypdfium2.
        """
        _install_fake_pypdfium2(
            monkeypatch,
            ["Auto-chain page text with enough words to form a chunk. " * 4],
        )
        monkeypatch.setitem(sys.modules, "liteparse", None)

        from omrg.core.ingestion import ingest_path_async
        from omrg.core.vectordb import get_default_store

        settings = effective_settings(pdf_reader="auto", extraction_mode="disabled")
        result = await ingest_path_async(
            str(fixtures_dir / "smoke_text.pdf"),
            collection_name="auto_page_label",
            effective_settings=settings,
        )

        assert result["status"] == "ok", result
        assert result["chunks_created"] >= 1

        payload = get_default_store().fetch_all("auto_page_label", ["metadatas"])
        assert payload, "no chunks stored"
        labels = {meta.get("page_label") for meta in payload["metadatas"]}
        # Retrieval reads ``page_label`` straight from stored metadata
        # (core/retrieval/dense.py) — preserved means present and stringly.
        assert labels == {"1"}


# ── pdf_inspector: honest absence (spec scenario) ──────────────────────


class TestPdfInspectorReportsNoPage:
    """pdf_inspector must not fabricate a page; it still reports page_count."""

    def test_page_label_absent_not_fabricated(self, fixtures_dir: Path) -> None:
        """One document per file: page_label MUST be absent, never a placeholder."""
        from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

        documents = PdfInspectorReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert len(documents) == 1
        meta = documents[0].metadata
        assert "page_label" not in meta, (
            f"pdf_inspector cannot observe pages; fabricating one is forbidden: {sorted(meta)}"
        )

    def test_still_reports_page_count(self, fixtures_dir: Path) -> None:
        """The operator still sees the document's true length."""
        from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

        documents = PdfInspectorReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert documents[0].metadata.get("page_count") == 1


# ── Task 6.5: the configuration guide and the registry agree ──────────


class TestDocsAndRegistryAgree:
    """The documented page-provenance matrix mirrors ``registry.describe()``."""

    @staticmethod
    def _matrix_rows() -> dict[str, tuple[str, bool]]:
        """Parse the per-reader matrix out of the configuration guide.

        Returns ``{reader: (text_format, page_provenance)}`` from rows like
        ``| `pypdf` | `plain` | Yes — per-page |`` inside the PDF reading
        section.
        """
        text = _CONFIG_GUIDE.read_text(encoding="utf-8")
        rows: dict[str, tuple[str, bool]] = {}
        pattern = re.compile(
            r"^\|\s*`(?P<reader>[a-z0-9_]+)`\s*"
            r"\|\s*`(?P<fmt>plain|markdown)`\s*"
            r"\|\s*(?P<page>Yes|No)\b",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            rows[match.group("reader")] = (
                match.group("fmt"),
                match.group("page") == "Yes",
            )
        return rows

    def test_every_registered_reader_has_a_matrix_row(self) -> None:
        """The matrix covers exactly the registered concrete readers."""
        from omrg.integrations.pdf import registry

        rows = self._matrix_rows()
        assert set(rows) == set(registry.available()), (
            f"configuration.md page-provenance matrix rows {sorted(rows)} do not "
            f"match registered readers {registry.available()}"
        )

    def test_matrix_agrees_with_registry_declarations(self) -> None:
        """Each row's format and page capability match ``describe()``."""
        from omrg.integrations.pdf import registry

        rows = self._matrix_rows()
        assert rows, "no page-provenance matrix found in docs/guides/configuration.md"
        for reader, (text_format, page_provenance) in rows.items():
            described = registry.describe(reader)
            assert described["text_format"] == text_format, reader
            assert described["page_provenance"] is page_provenance, reader
