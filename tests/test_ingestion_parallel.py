"""Tests for ingestion module - read/chunk and sequential ingestion.

Tests cover:
- read_and_chunk_file with MockEmbedding
- Bounded sequential ingestion behavior
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

from omrg.core.ingestion import ingest_path_async
from omrg.core.ingestion._state import (
    get_embed_semaphore as _get_embed_semaphore,
)
from omrg.core.ingestion._state import (
    shutdown_requested as _shutdown_requested,
)
from omrg.core.ingestion._state import (
    write_lock as _write_lock,
)
from omrg.core.ingestion.chunker import read_and_chunk_file_async
from omrg.core.ingestion.chunker import read_and_chunk_file_async as _read_and_chunk_file_async
from omrg.core.ingestion.loader import gather_supported_files as _gather_supported_files


class TestGatherSupportedFiles:
    """Tests for file discovery."""

    def test_single_file(self, sample_txt: Path) -> None:
        """Supported file is discovered."""
        files, skipped = _gather_supported_files(sample_txt)
        assert files == [sample_txt]
        assert skipped == []

    def test_unsupported_file(self, tmp_path: Path) -> None:
        """Unsupported single file is excluded without a skipped entry."""
        bad = tmp_path / "test.xyz"
        bad.write_text("content")
        files, skipped = _gather_supported_files(bad)
        assert files == []
        assert skipped == []

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

        skipped_names = {s["file"] for s in skipped}
        assert "bad.xyz" in skipped_names


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

    def test_public_wrapper_delegates_to_chunker(self, sample_txt: Path) -> None:
        """Public internal-supported wrapper reads and chunks benchmark files."""
        nodes = asyncio.run(read_and_chunk_file_async(sample_txt))
        assert len(nodes) > 0
        assert all(n.text for n in nodes)

    def test_custom_chunk_size(self, sample_txt: Path) -> None:
        """Smaller chunk_size produces more nodes."""
        nodes_default = asyncio.run(_read_and_chunk_file_async(sample_txt, chunk_size=512))
        nodes_small = asyncio.run(
            _read_and_chunk_file_async(sample_txt, chunk_size=64, chunk_overlap=10)
        )
        assert len(nodes_small) >= len(nodes_default)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Reading a non-existent file raises an exception."""
        with pytest.raises(Exception):
            asyncio.run(_read_and_chunk_file_async(tmp_path / "nonexistent.txt"))


class TestSequentialIngestPath:
    """Tests for the bounded sequential async ingestion path."""

    async def test_directory_ingest(self, dir_with_docs: Path) -> None:
        """Directory ingestion works."""
        result = await ingest_path_async(str(dir_with_docs))
        assert result["status"] == "ok"
        assert result["files_indexed"] > 0
        assert result["chunks_created"] > 0

    async def test_repeated_ingest_skips_unchanged_files(self, dir_with_docs: Path) -> None:
        """A complete matching source/index version skips expensive reprocessing."""
        r1 = await ingest_path_async(str(dir_with_docs))
        r2 = await ingest_path_async(str(dir_with_docs))
        assert r1["files_indexed"] > 0
        assert r1["chunks_created"] > 0
        assert r2["status"] == "ok"
        assert r2["files_indexed"] == 0
        assert r2["files_skipped_unchanged"] == r1["files_indexed"]
        assert r2["chunks_created"] == 0
        assert r2["chunks_removed"] == 0

    async def test_single_file_ingest(self, sample_txt: Path) -> None:
        """Single-file ingestion works."""
        result = await ingest_path_async(str(sample_txt))
        assert result["status"] == "ok"
        assert result["files_indexed"] > 0
        assert result["chunks_created"] > 0


class TestErrorIsolation:
    """Tests for per-file error handling."""

    async def test_corrupt_file_skipped(self, tmp_path: Path) -> None:
        """Corrupt files are skipped, valid files indexed."""
        good = tmp_path / "good.txt"
        good.write_text("This is valid content.")

        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"NOT A REAL PDF" * 100)

        result = await ingest_path_async(str(tmp_path))
        assert result["status"] == "ok"
        assert result["files_indexed"] >= 1

    async def test_nonexistent_path_returns_error(self) -> None:
        """Non-existent path returns error dict."""
        result = await ingest_path_async("/nonexistent/path")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestConcurrencyPrimitives:
    """Tests for thread-safety primitives in ingestion module."""

    def test_concurrent_write_lock_serialises(self) -> None:
        """The write lock serialises access to one thread at a time."""
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
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert max_concurrent == 1

    def test_embed_semaphore_limits_concurrency(self) -> None:
        """The limiter caps concurrent holders at the injected value.

        The limiter is built from the injected concurrency at call time rather
        than snapshotted at import, so the test states the value it depends on.
        """
        concurrency = 2
        semaphore = _get_embed_semaphore(concurrency)

        max_concurrent = 0
        current = 0
        counter_lock = threading.Lock()

        def worker() -> None:
            nonlocal max_concurrent, current
            with semaphore:
                with counter_lock:
                    current += 1
                    max_concurrent = max(max_concurrent, current)
                time.sleep(0.01)
                with counter_lock:
                    current -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert max_concurrent <= concurrency

    async def test_parallel_shutdown_early_exit(self, tmp_path: Path) -> None:
        """Shutdown flag set mid-ingest causes early exit with fewer files."""
        for i in range(5):
            (tmp_path / f"doc_{i}.txt").write_text(f"content {i} " * 20)

        def _signal_midway(phase: str, current: int, total: int) -> None:
            if phase == "read" and current >= 2:
                _shutdown_requested.set()

        try:
            result = await ingest_path_async(
                str(tmp_path),
                progress_callback=_signal_midway,
            )
            assert result["files_indexed"] < 5
        finally:
            _shutdown_requested.clear()
