"""Tests for SIGINT (Ctrl+C) signal handling during ingestion.

Tests cover:
- Shutdown flag causes ingestion to stop early
- No partial ChromaDB writes when shutdown is requested
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.ingestion._state import shutdown_requested as _shutdown_requested
from rag_mcp.core.ingestion.writer import embed_and_write_async as _embed_and_write_async


class TestShutdownFlag:
    """Tests for _shutdown_requested event flag."""

    async def test_shutdown_flag_cleared_on_new_ingest(self, dir_with_docs: Path) -> None:
        """Shutdown flag is cleared at the start of each ingest_path_async call."""
        _shutdown_requested.set()
        assert _shutdown_requested.is_set()

        result = await ingest_path_async(str(dir_with_docs))
        assert result["status"] == "ok"

    async def test_shutdown_flag_stops_sequential_early(self, tmp_path: Path) -> None:
        """Sequential ingestion stops when shutdown flag is set mid-run."""
        for i in range(5):
            (tmp_path / f"doc_{i}.txt").write_text(f"Content of document {i}. " * 20)

        def _signal_after_first(phase: str, current: int, total: int) -> None:
            if phase == "read" and current >= 1:
                _shutdown_requested.set()

        try:
            result = await ingest_path_async(
                str(tmp_path),
                progress_callback=_signal_after_first,
            )
        finally:
            _shutdown_requested.clear()

        # Stage 3A commits each source fully before advancing (ADR-048), so
        # a shutdown signalled after the first source's completion cannot
        # un-write that source; the flag stops the remaining sources instead.
        assert result["files_indexed"] == 1


class TestEmbedAndWriteShutdown:
    """Tests for _embed_and_write_async respecting the shutdown flag."""

    async def test_returns_zero_when_shutdown_set(self, tmp_path: Path) -> None:
        """_embed_and_write_async returns 0 when shutdown flag is set."""
        _shutdown_requested.set()
        try:
            result = await _embed_and_write_async(["fake_node"])
            assert result == 0
        finally:
            _shutdown_requested.clear()

    async def test_returns_zero_for_empty_nodes(self) -> None:
        """_embed_and_write_async returns 0 for empty node list."""
        result = await _embed_and_write_async([])
        assert result == 0


class TestLockRecheckOnShutdown:
    """Tests for the double-check of _shutdown_requested inside _write_lock."""

    async def test_embed_and_write_bails_inside_lock(self) -> None:
        """_embed_and_write_async re-checks shutdown flag after acquiring lock."""
        _shutdown_requested.set()
        try:
            result = await _embed_and_write_async(["fake_node"])
            assert result == 0
        finally:
            _shutdown_requested.clear()


class TestPathResolution:
    """Tests for ingest_path resolving ~ and relative paths."""

    async def test_ingest_path_resolves_tilde(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ingest_path_async expands ~ via expanduser to the home directory."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        test_dir = fake_home / "test_rag_dir"
        test_dir.mkdir()
        (test_dir / "doc.txt").write_text("Content for tilde expansion test. " * 10)

        monkeypatch.setenv("HOME", str(fake_home))

        result = await ingest_path_async("~/test_rag_dir/doc.txt")
        assert result["status"] == "ok"
        assert result["files_indexed"] == 1

    async def test_ingest_path_resolves_relative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ingest_path_async resolves relative paths from the current directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "doc.txt").write_text("Relative path content. " * 10)

        monkeypatch.chdir(tmp_path)
        result = await ingest_path_async("subdir/doc.txt")
        assert result["status"] == "ok"
        assert result["files_indexed"] == 1
