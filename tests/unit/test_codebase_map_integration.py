"""Integration tests for codebase map pipeline, caching, and MCP tool invocation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rag_mcp.core.codebase.codebase_map import (
    CodebaseMap,
    FileInventory,
    build_codebase_map,
    format_codebase_map,
    get_codebase_map_text,
    _load_cache,
    _save_cache,
)


class TestBuildCodebaseMap:
    """Tests for the full build_codebase_map pipeline."""

    def test_build_with_code_files(self, tmp_path: Path) -> None:
        """Building a map with code files produces code communities."""
        (tmp_path / "app.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n")
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False):
            m = build_codebase_map(str(tmp_path))
        assert len(m.inventory.entries) >= 2
        assert "code/python" in m.inventory.type_counts

    def test_build_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory produces empty map."""
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False):
            m = build_codebase_map(str(tmp_path))
        assert len(m.inventory.entries) == 0

    def test_build_with_documents(self, tmp_path: Path) -> None:
        """Building with markdown files detects document types."""
        (tmp_path / "README.md").write_text("# Project\n\nHello world")
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False):
            m = build_codebase_map(str(tmp_path))
        assert "document/markdown" in m.inventory.type_counts

    def test_build_no_git(self, tmp_path: Path) -> None:
        """Building outside a git repo sets commit_hash to None."""
        (tmp_path / "app.py").write_text("x = 1\n")
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False), \
             patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value=None):
            m = build_codebase_map(str(tmp_path))
        assert m.commit_hash is None


class TestCaching:
    """Tests for cache load/save and invalidation."""

    def test_save_and_load_cache(self, tmp_path: Path) -> None:
        """Cache round-trip preserves data."""
        m = CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 3}),
            code_communities=[{"label": "Core", "files": ["a.py"], "file_count": 1, "edge_count": 0}],
            commit_hash="abc123",
        )
        _save_cache(str(tmp_path), m)

        with patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value="abc123"):
            loaded = _load_cache(str(tmp_path))
        assert loaded is not None
        assert loaded.commit_hash == "abc123"
        assert loaded.code_communities[0]["label"] == "Core"

    def test_cache_miss_different_hash(self, tmp_path: Path) -> None:
        """Cache miss when commit hash differs."""
        m = CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 1}),
            commit_hash="abc123",
        )
        _save_cache(str(tmp_path), m)

        with patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value="def456"):
            loaded = _load_cache(str(tmp_path))
        assert loaded is None

    def test_cache_miss_no_file(self, tmp_path: Path) -> None:
        """No cache file returns None."""
        loaded = _load_cache(str(tmp_path))
        assert loaded is None

    def test_cache_no_git(self, tmp_path: Path) -> None:
        """No git returns None (caching disabled)."""
        m = CodebaseMap(commit_hash=None)
        _save_cache(str(tmp_path), m)
        # Should not write a cache file when commit_hash is None.
        cache_file = tmp_path / ".opencode" / "codebase-graph.json"
        assert not cache_file.exists()

    def test_cache_corrupt_file(self, tmp_path: Path) -> None:
        """Corrupt cache file returns None."""
        cache_dir = tmp_path / ".opencode"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "codebase-graph.json"
        cache_file.write_text("{invalid json")

        with patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value="abc123"):
            loaded = _load_cache(str(tmp_path))
        assert loaded is None


class TestGetCodebaseMapText:
    """Tests for the MCP tool entry point."""

    def test_error_path_not_found(self) -> None:
        """Non-existent path returns error JSON."""
        result = get_codebase_map_text(path="/nonexistent/path/xyz")
        data = json.loads(result)
        assert data["status"] == "error"
        assert "Path not found" in data["message"]

    def test_error_not_a_directory(self, tmp_path: Path) -> None:
        """File path (not directory) returns error JSON."""
        (tmp_path / "file.txt").write_text("hello")
        result = get_codebase_map_text(path=str(tmp_path / "file.txt"))
        data = json.loads(result)
        assert data["status"] == "error"

    def test_valid_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid directory returns formatted map text."""
        (tmp_path / "app.py").write_text("x = 1\n")
        monkeypatch.chdir(tmp_path)
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False), \
             patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value=None):
            result = get_codebase_map_text(path=".")
        assert "## File Types" in result
        assert "code/python" in result

    def test_refresh_bypasses_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Refresh=True bypasses cache."""
        (tmp_path / "app.py").write_text("x = 1\n")
        monkeypatch.chdir(tmp_path)
        with patch("rag_mcp.integrations.magika._is_magika_available", return_value=False), \
             patch("rag_mcp.core.codebase.cache._get_git_commit_hash", return_value=None), \
             patch("rag_mcp.core.codebase.cache._load_cache") as mock_load:
            result = get_codebase_map_text(path=".", refresh=True)
            # _load_cache should not be called when refresh=True.
            mock_load.assert_not_called()
        assert "## File Types" in result

    def test_never_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """MCP tool handler never raises — returns error JSON."""
        monkeypatch.chdir(tmp_path)
        with patch("rag_mcp.core.codebase.codebase_map.build_codebase_map", side_effect=RuntimeError("boom")):
            result = get_codebase_map_text(path=".")
            data = json.loads(result)
            assert data["status"] == "error"
            assert "boom" in data["message"]
