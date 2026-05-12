"""Unit tests for document ingestion and listing.

Tests cover:
- ingest_path() validation: non-existent path, unsupported extension, empty dir
- list_documents() with no collection
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from rag_mcp.ingestion import ingest_path, list_documents


# ── ingest_path validation ─────────────────────────────────────────────────


class TestIngestPathValidation:
    """Tests for ingest_path() input validation (no Ollama needed)."""

    def test_nonexistent_path_returns_error(self) -> None:
        """ingest_path with a non-existent path must return an error."""
        result = ingest_path("/nonexistent/directory/path")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_unsupported_extension_returns_error(self, tmp_path: Path) -> None:
        """ingest_path with an unsupported file extension must return error."""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("some content")
        result = ingest_path(str(bad_file))
        assert result["status"] == "error"
        assert "unsupported" in result["message"].lower()

    def test_empty_directory_returns_success_zero_counts(
        self, tmp_path: Path
    ) -> None:
        """ingest_path on an empty directory must return ok with zero counts."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        result = ingest_path(str(empty_dir))
        assert result["status"] == "ok"
        assert result["files_indexed"] == 0
        assert result["chunks_created"] == 0


# ── list_documents ─────────────────────────────────────────────────────────


class TestListDocuments:
    """Tests for list_documents() edge cases."""

    def test_empty_store_returns_empty_list(self) -> None:
        """list_documents() with no indexed documents must return []."""
        result = list_documents()
        assert result == []
