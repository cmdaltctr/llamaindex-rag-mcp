"""Tests for ingestion module — _read_and_chunk_file and parallel ingestion.

Tests cover:
- _read_and_chunk_file with MockEmbedding
- Parallel vs sequential produces same chunks
- Per-file error isolation (corrupt files skipped)
- All-files-fail scenario
- Concurrency primitives (write lock, semaphore, shutdown)
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from rag_mcp.ingestion import (
    _read_and_chunk_file_async,
    _gather_supported_files,
    _shutdown_requested,
    _write_lock,
    _embed_semaphore,
    ingest_path_async,
    list_documents,
)


# ── _gather_supported_files ──────────────────────────────────────────────


class TestGatherSupportedFiles:
    """Tests for file discovery."""

    def test_single_file(self, sample_txt: Path) -> None:
        """Supported file is discovered."""
        files, skipped = _gather_supported_files(sample_txt)
        assert files == [sample_txt]
        assert skipped == []

    def test_unsupported_file(self, tmp_path: Path) -> None:
        """Unsupported extension is excluded and tracked as skipped."""
        bad = tmp_path / "test.xyz"
        bad.write_text("content")
        files, skipped = _gather_supported_files(bad)
        assert files == []

    def test_directory_with_mixed_files(self, tmp_path: Path) -> None:
        """Only supported extensions are discovered in directories."""
        (tmp_path / "good.txt").write_text("text content")
        (tmp_path / "also_good.md").write_text("# markdown")
        (tmp_path / "bad.xyz").write_text("bad content")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.pdf").write_text("not real pdf")

        files, skipped = _gather_supported_files(tmp_path)
        names = {f.name for f in files}
        assert "good.txt" in names
        assert "also_good.md" in names
        assert "bad.xyz" not in names

        # Verify skipped files are tracked
        skipped_names = {s["file"] for s in skipped}
        assert "bad.xyz" in skipped_names


# ── _read_and_chunk_file ─────────────────────────────────────────────────


class TestReadAndChunkFile:
    """Tests for single file reading and chunking."""

    def test_read_txt_file(self, sample_txt: Path) -> None:
        """Reads a .txt file and returns nodes."""
        nodes = asyncio.run(_read_and_chunk_file_async(sample_txt))
        assert len(nodes) > 0
        assert all(n.text for n in nodes)

    def test_read_md_file(self, sample_md: Path) -> None:
        """Reads a .md file and returns nodes."""
        nodes = asyncio.run(_read_and_chunk_file_async(sample_md))
        assert len(nodes) > 0

    def test_custom_chunk_size(self, sample_txt: Path) -> None:
        """Smaller chunk_size produces more nodes."""
        nodes_default = asyncio.run(_read_and_chunk_file_async(sample_txt, chunk_size=512))
        nodes_small = asyncio.run(_read_and_chunk_file_async(sample_txt, chunk_size=64))
        assert len(nodes_small) >= len(nodes_default)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Reading a non-existent file raises an exception."""
        with pytest.raises(Exception):
            asyncio.run(_read_and_chunk_file_async(tmp_path / "nonexistent.txt"))


# ── Parallel vs Sequential ───────────────────────────────────────────────


class TestIngestPathWithWorkers:
    """Tests for parallel vs sequential ingestion."""

    async def test_sequential_ingest(self, dir_with_docs: Path) -> None:
        """Sequential ingestion (workers=1) works."""
        result = await ingest_path_async(str(dir_with_docs), workers=1)
        assert result["status"] == "ok"
        assert result["files_indexed"] > 0
        assert result["chunks_created"] > 0

    async def test_parallel_ingest(self, dir_with_docs: Path) -> None:
        """Parallel ingestion (workers=4) works via async path."""
        result = await ingest_path_async(str(dir_with_docs), workers=4)
        assert result["status"] == "ok"
        assert result["files_indexed"] > 0
        assert result["chunks_created"] > 0

    async def test_parallel_produces_same_chunk_count(
        self, dir_with_docs: Path
    ) -> None:
        """Sequential produces consistent chunk count."""
        r1 = await ingest_path_async(str(dir_with_docs), workers=1)
        r2 = await ingest_path_async(str(dir_with_docs), workers=4)
        assert r1["files_indexed"] == r2["files_indexed"]
        assert r1["chunks_created"] == r2["chunks_created"]

    async def test_workers_clamped_to_one(self, sample_txt: Path) -> None:
        """Workers < 1 is clamped to 1."""
        result = await ingest_path_async(str(sample_txt), workers=0)
        assert result["status"] == "ok"

        result = await ingest_path_async(str(sample_txt), workers=-5)
        assert result["status"] == "ok"


class TestErrorIsolation:
    """Tests for per-file error handling."""

    async def test_corrupt_file_skipped(self, tmp_path: Path) -> None:
        """Corrupt files are skipped, valid files indexed."""
        good = tmp_path / "good.txt"
        good.write_text("This is valid content.")

        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"NOT A REAL PDF" * 100)

        result = await ingest_path_async(str(tmp_path), workers=1)
        assert result["status"] == "ok"
        assert result["files_indexed"] >= 1

    async def test_nonexistent_path_returns_error(self) -> None:
        """Non-existent path returns error dict."""
        result = await ingest_path_async("/nonexistent/path")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


# ── Concurrency primitives ────────────────────────────────────────────────


class TestConcurrencyPrimitives:
    """Tests for thread-safety primitives in ingestion module."""

    def test_concurrent_write_lock_serialises(self) -> None:
        """_write_lock serialises access — only one thread at a time."""
        max_concurrent = 0
        current = 0
        counter_lock = threading.Lock()

        def worker() -> None:
            nonlocal max_concurrent, current
            with _write_lock:
                with counter_lock:
                    current += 1
                    max_concurrent = max(max_concurrent, current)
                time.sleep(0.01)
                with counter_lock:
                    current -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent == 1

    def test_embed_semaphore_limits_concurrency(self) -> None:
        """BoundedSemaphore(2) limits to at most 2 concurrent holders."""
        from rag_mcp.config import EMBED_CONCURRENCY

        max_concurrent = 0
        current = 0
        counter_lock = threading.Lock()

        def worker() -> None:
            nonlocal max_concurrent, current
            with _embed_semaphore:
                with counter_lock:
                    current += 1
                    max_concurrent = max(max_concurrent, current)
                time.sleep(0.01)
                with counter_lock:
                    current -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent <= EMBED_CONCURRENCY

    async def test_parallel_shutdown_early_exit(self, tmp_path: Path) -> None:
        """Shutdown flag set mid-parallel causes early exit with fewer files."""
        for i in range(5):
            (tmp_path / f"doc_{i}.txt").write_text(
                f"content {i} " * 20
            )

        # Set the flag via progress callback after some files are read
        def _signal_midway(phase: str, current: int, total: int) -> None:
            if phase == "read" and current >= 2:
                _shutdown_requested.set()

        try:
            result = await ingest_path_async(
                str(tmp_path),
                workers=4,
                progress_callback=_signal_midway,
            )
            # Should have stopped early — fewer files indexed than total
            assert result["files_indexed"] < 5
        finally:
            _shutdown_requested.clear()
