"""Unit tests for azure_reader.py — response parsing, table chunking, import guarding.

The fallback/retry surface moved to
``core/ingestion/backends/orchestrator`` (register-document-backend-
strategies, task 3.2); its coverage lives in ``tests/test_document_backends.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omrg.integrations.azure import (
    AzureDocReader,
    _format_table,
    _split_table_rows,
    parse_azure_response,
)


class TestParseAzureResponse:
    """Tests for Azure structured JSON → LlamaIndex Document conversion."""

    def test_paragraphs_extracted(self, tmp_path: Path) -> None:
        """Paragraphs are converted to Documents."""
        result = MagicMock()
        para1 = MagicMock(content="Hello world", role="paragraph")
        para2 = MagicMock(content="Second paragraph", role="heading1")
        result.paragraphs = [para1, para2]
        result.tables = []
        result.content = ""

        documents = parse_azure_response(result, tmp_path / "test.pdf")
        assert len(documents) == 2
        assert "Hello world" in documents[0].text
        assert documents[1].metadata.get("heading_role") == "heading1"

    def test_tables_extracted(self, tmp_path: Path) -> None:
        """Tables are converted to Documents with content_type='table'."""
        result = MagicMock()
        result.paragraphs = []

        cell1 = MagicMock(content="A", row_index=0, column_index=0)
        cell2 = MagicMock(content="B", row_index=0, column_index=1)
        cell3 = MagicMock(content="1", row_index=1, column_index=0)
        cell4 = MagicMock(content="2", row_index=1, column_index=1)
        table = MagicMock(
            cells=[cell1, cell2, cell3, cell4],
            row_count=2,
            column_count=2,
        )
        result.tables = [table]
        result.content = ""

        documents = parse_azure_response(result, tmp_path / "test.pdf")
        assert len(documents) == 1
        assert documents[0].metadata.get("content_type") == "table"
        assert "| A | B |" in documents[0].text

    def test_empty_result(self, tmp_path: Path) -> None:
        """Empty Azure result produces empty list."""
        result = MagicMock()
        result.paragraphs = []
        result.tables = []
        result.content = ""
        documents = parse_azure_response(result, tmp_path / "test.pdf")
        assert documents == []

    def test_raw_content_fallback(self, tmp_path: Path) -> None:
        """When no paragraphs/tables, raw content is used."""
        result = MagicMock()
        result.paragraphs = []
        result.tables = []
        result.content = "Raw text content"
        documents = parse_azure_response(result, tmp_path / "test.pdf")
        assert len(documents) == 1
        assert "Raw text content" in documents[0].text


class TestTableChunking:
    """Tests for table-aware chunking."""

    def test_small_table_intact(self) -> None:
        """Small tables are kept as a single chunk."""
        cells = []
        for r in range(5):
            for c in range(3):
                cell = MagicMock(content=f"R{r}C{c}", row_index=r, column_index=c)
                cells.append(cell)
        table = MagicMock(cells=cells, row_count=5, column_count=3)
        text = _format_table(table)
        assert "| R0C0 | R0C1 | R0C2 |" in text
        assert "| R4C0 | R4C1 | R4C2 |" in text

    def test_large_table_split(self) -> None:
        """Large tables (>50 rows) are split into row groups."""
        cells = []
        for r in range(120):
            for c in range(2):
                cell = MagicMock(content=f"R{r}C{c}", row_index=r, column_index=c)
                cells.append(cell)
        table = MagicMock(cells=cells, row_count=120, column_count=2)
        groups = _split_table_rows(table, group_size=50)
        assert len(groups) == 3  # 50 + 50 + 20

    def test_empty_table(self) -> None:
        """Empty table produces empty string."""
        table = MagicMock(cells=[], row_count=0, column_count=0)
        text = _format_table(table)
        assert text == ""


class TestImportGuarding:
    """Tests for lazy Azure SDK import guarding."""

    def test_import_error_when_sdk_missing(self) -> None:
        """ImportError raised when Azure SDK is not installed."""
        reader = AzureDocReader(endpoint="https://example.com", key="fake")
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            with pytest.raises(ImportError, match="azure-ai-documentintelligence"):
                reader._get_client()

    def test_module_loads_without_sdk(self) -> None:
        """Module loads even when Azure SDK is not installed."""
        # The module is already imported at top level — just verify it's usable.
        reader = AzureDocReader(endpoint="https://example.com", key="fake")
        assert reader.endpoint == "https://example.com"
        assert reader.model == "prebuilt-layout"
