"""Red-first contract tests for machine-local orphaned-source visibility.

Pins ``openspec/changes/orphaned-source-visibility-2`` tasks 1.1-1.4: the
``orphaned`` tri-state on every ``list_documents()`` row. The tests inject a
fake store through the ``store=`` seam, so no backend, embedding, or settings
are involved. They fail on the current implementation (the task 1.6 red run)
and pin the spec scenarios once the additive field lands.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from rag_mcp.core.ingestion.loader import list_documents
from rag_mcp.core.ingestion.source_state import SOURCE_ID_KEY


class _FakeListingStore:
    """Minimal store satisfying the ``list_documents()`` listing seam.

    Implements only ``count()`` and ``iter_metadatas()`` — the two
    VectorStore operations the listing consumes (task 1.1).
    """

    def __init__(self, metadatas: list[dict | None]) -> None:
        self._metadatas = list(metadatas)

    def count(self, collection_name: str) -> int:
        return len(self._metadatas)

    def iter_metadatas(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[dict | None]:
        yield from self._metadatas


# ── Task 1.2: absolute sources split into present and missing ─────────


class TestAbsoluteSourceClassification:
    """Absolute paths are classified once per grouped source."""

    def test_existing_absolute_source_reports_orphaned_false(self, tmp_path: Path) -> None:
        """Spec: an absolute path that exists on this machine reports false."""
        existing = tmp_path / "present.txt"
        existing.write_text("present", encoding="utf-8")
        store = _FakeListingStore([{SOURCE_ID_KEY: "src_present", "file_path": str(existing)}])

        rows = list_documents("documents", store=store)

        assert rows == [
            {
                "source": str(existing),
                "source_id": "src_present",
                "chunks": 1,
                "orphaned": False,
            }
        ]

    def test_missing_absolute_source_reports_orphaned_true(self, tmp_path: Path) -> None:
        """Spec: an absolute path absent from this machine reports true."""
        gone = tmp_path / "gone.txt"  # deliberately never created
        store = _FakeListingStore([{SOURCE_ID_KEY: "src_gone", "file_path": str(gone)}])

        rows = list_documents("documents", store=store)

        assert rows[0]["orphaned"] is True

    def test_grouped_missing_source_lists_once_with_chunk_count(self, tmp_path: Path) -> None:
        """Spec: classification is per grouped source, not per chunk row."""
        gone = tmp_path / "moved.txt"
        metas = [
            {SOURCE_ID_KEY: "src_moved", "file_path": str(gone)},
            {SOURCE_ID_KEY: "src_moved", "file_path": str(gone)},
            {SOURCE_ID_KEY: "src_moved", "file_path": str(gone)},
        ]

        rows = list_documents("documents", store=_FakeListingStore(metas))

        assert rows == [
            {"source": str(gone), "source_id": "src_moved", "chunks": 3, "orphaned": True}
        ]


# ── Task 1.3: legacy rows report the unknown state ────────────────────


class TestLegacyRowsReportUnknown:
    """Rows without a usable absolute path report ``None``."""

    def test_basename_only_legacy_row_reports_orphaned_none(self) -> None:
        """Spec: a basename-only ``file_name`` is never filesystem-checked."""
        store = _FakeListingStore([{"file_name": "report.pdf"}])

        rows = list_documents("documents", store=store)

        assert rows == [{"source": "report.pdf", "source_id": None, "chunks": 1, "orphaned": None}]

    def test_row_without_source_metadata_reports_orphaned_none(self) -> None:
        """Spec: a row with no source metadata lists as ``unknown``."""
        store = _FakeListingStore([{}])

        rows = list_documents("documents", store=store)

        assert rows == [{"source": "unknown", "source_id": None, "chunks": 1, "orphaned": None}]


# ── Task 1.4: no existence check against the working directory ────────


class TestNonAbsoluteSourcesAreNeverChecked:
    """A basename must not resolve through the process working directory."""

    def test_basename_matching_cwd_file_still_reports_orphaned_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec: a CWD collision must not turn a basename into ``false``.

        ``paper.pdf`` exists in the process working directory. If the
        implementation tested the basename for existence, the row would
        wrongly report ``false``; the contract is ``None``.
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / "paper.pdf").write_text("colliding", encoding="utf-8")
        store = _FakeListingStore([{"file_name": "paper.pdf"}])

        rows = list_documents("documents", store=store)

        assert rows[0]["orphaned"] is None

    @pytest.mark.skipif(
        sys.platform == "win32", reason="foreign-syntax expectation is host-specific"
    )
    def test_foreign_windows_style_path_reports_orphaned_none(self) -> None:
        """Spec: another operating system's absolute path is not absolute here."""
        foreign = "C:\\Docs\\report.pdf"
        store = _FakeListingStore([{SOURCE_ID_KEY: "src_foreign", "file_path": foreign}])

        rows = list_documents("documents", store=store)

        assert rows[0]["orphaned"] is None
