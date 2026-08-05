"""Unit tests for type-aware ingestion dispatch — CodeSplitter, config, binary skip, content_type metadata."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_mcp.core.chunking.code import chunk_code_file_async as _chunk_code_file_async
from rag_mcp.core.chunking.config_file import chunk_config_file as _chunk_config_file
from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async as _read_and_chunk_file_async


class TestCodeSplitterDispatch:
    """Tests for code file chunking via CodeSplitter."""

    @pytest.mark.asyncio
    async def test_python_code_chunked(self, tmp_path: Path) -> None:
        """Python files are chunked using CodeSplitter with content_type metadata."""
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        (tmp_path / "app.py").write_text(code)
        nodes = await _chunk_code_file_async(
            tmp_path / "app.py", "python", 1024, 100, "code/python",
        )
        assert len(nodes) >= 1
        for node in nodes:
            assert node.metadata.get("content_type") == "code/python"

    @pytest.mark.asyncio
    async def test_code_splitter_fallback(self, tmp_path: Path) -> None:
        """CodeSplitter falls back to SentenceSplitter on error."""
        (tmp_path / "app.py").write_text("x = 1\n")
        # Patch at the function's import location to avoid module-level pollution.
        with patch.object(
            __import__("llama_index.core.node_parser", fromlist=["CodeSplitter"]),
            "CodeSplitter",
            side_effect=Exception("boom"),
        ):
            nodes = await _chunk_code_file_async(
                tmp_path / "app.py", "python", 1024, 100, "code/python",
            )
        assert len(nodes) >= 1
        assert nodes[0].metadata.get("content_type") == "code/python"


class TestConfigFileChunking:
    """Tests for config file whole-file chunking."""

    def test_config_single_chunk(self, tmp_path: Path) -> None:
        """Config files produce a single whole-file chunk."""
        (tmp_path / "config.yaml").write_text("key: value\n")
        nodes = _chunk_config_file(
            tmp_path / "config.yaml", "config/yaml",
        )
        assert len(nodes) == 1
        assert nodes[0].metadata.get("content_type") == "config/yaml"
        assert "key: value" in nodes[0].text


class TestContentTypeDispatch:
    """Tests for content_type-based dispatch in _read_and_chunk_file_async."""

    @pytest.mark.asyncio
    async def test_code_dispatch(self, tmp_path: Path) -> None:
        """code/* content_type dispatches to CodeSplitter."""
        code = "def foo():\n    pass\n"
        (tmp_path / "app.py").write_text(code)
        nodes = await _read_and_chunk_file_async(
            tmp_path / "app.py", content_type="code/python",
        )
        assert len(nodes) >= 1
        assert all(n.metadata.get("content_type") == "code/python" for n in nodes)

    @pytest.mark.asyncio
    async def test_config_dispatch(self, tmp_path: Path) -> None:
        """config/* content_type dispatches to whole-file chunking."""
        (tmp_path / "settings.json").write_text('{"key": "value"}')
        nodes = await _read_and_chunk_file_async(
            tmp_path / "settings.json", content_type="config/json",
        )
        assert len(nodes) == 1
        assert nodes[0].metadata.get("content_type") == "config/json"

    @pytest.mark.asyncio
    async def test_none_content_type_uses_extension(self, tmp_path: Path) -> None:
        """None content_type falls back to extension-based routing."""
        (tmp_path / "doc.md").write_text("# Hello\n\nWorld")
        nodes = await _read_and_chunk_file_async(
            tmp_path / "doc.md", content_type=None,
        )
        # Should produce nodes via the existing markdown path.
        assert len(nodes) >= 1

    @pytest.mark.asyncio
    async def test_content_type_takes_precedence(self, tmp_path: Path) -> None:
        """content_type takes precedence over file extension."""
        # A .txt file with code/python content_type should use CodeSplitter.
        (tmp_path / "script.txt").write_text("def foo():\n    pass\n")
        nodes = await _read_and_chunk_file_async(
            tmp_path / "script.txt", content_type="code/python",
        )
        assert len(nodes) >= 1
        assert all(n.metadata.get("content_type") == "code/python" for n in nodes)


class TestBinarySkip:
    """Tests for binary file skipping in ingest_path_async."""

    @pytest.mark.asyncio
    async def test_binary_file_skipped(self, tmp_path: Path) -> None:
        """Binary files are skipped with status='skipped'."""
        (tmp_path / "app.py").write_text("x = 1\n")
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        from rag_mcp.core.codebase.codebase_map import FileEntry, FileInventory

        mock_inventory = FileInventory(
            entries=[
                FileEntry("app.py", "code", "python", True, ".py"),
                FileEntry("image.png", "binary", "png", False, ".png"),
            ],
            type_counts={"code/python": 1, "binary/png": 1},
            binary_files=["image.png"],
        )

        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False), \
             patch("rag_mcp.core.codebase.codebase_map.detect_file_types", return_value=mock_inventory), \
             patch("rag_mcp.core.ingestion.pipeline.gather_supported_files", return_value=([tmp_path / "app.py", tmp_path / "image.png"], [])), \
             patch("rag_mcp.core.ingestion.pipeline.remove_document", return_value={"status": "ok", "chunks_removed": 0}), \
             patch("rag_mcp.core.ingestion.pipeline.embed_and_write_async", new_callable=AsyncMock, return_value=1):
            from rag_mcp.core.ingestion import ingest_path_async
            result = await ingest_path_async(str(tmp_path))

        skipped = [d for d in result["file_details"] if d.get("status") == "skipped"]
        assert len(skipped) >= 1
