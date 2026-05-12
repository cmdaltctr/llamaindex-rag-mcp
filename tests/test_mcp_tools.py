"""Integration tests for MCP tool routing via in-memory ClientSession.

Tests cover:
- Tool discovery (list_tools)
- ingest_documents tool
- search_documents tool
- list_indexed_documents tool
- Parameter validation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import connected_client
from mcp.types import TextContent


# ── Tool discovery ─────────────────────────────────────────────────────────


async def test_list_tools_discovers_all_three(mcp_server) -> None:
    """The server must expose exactly the three expected tools."""
    async with connected_client(mcp_server) as client:
        result = await client.list_tools()
        tool_names = {t.name for t in result.tools}
        assert tool_names == {
            "ingest_documents",
            "search_documents",
            "list_indexed_documents",
        }


# ── ingest_documents ───────────────────────────────────────────────────────


async def test_ingest_documents_with_fixtures_dir(
    mcp_server, fixtures_dir: Path
) -> None:
    """Ingesting the test fixtures directory must succeed."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)}
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["files_indexed"] > 0


# ── search_documents ───────────────────────────────────────────────────────


async def test_search_after_ingest_returns_results(
    mcp_server, fixtures_dir: Path
) -> None:
    """After ingesting fixtures, search must return results with correct shape."""
    async with connected_client(mcp_server) as client:
        # First, ingest
        await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)}
        )
        # Then search
        result = await client.call_tool(
            "search_documents", {"query": "capital of France"}
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        # Check shape of first result
        first = data[0]
        assert "score" in first
        assert "source" in first
        assert "text" in first
        assert "reranked" in first


# ── list_indexed_documents ─────────────────────────────────────────────────


async def test_list_after_ingest_returns_nonempty(
    mcp_server, fixtures_dir: Path
) -> None:
    """After ingesting, list_indexed_documents must return non-empty."""
    async with connected_client(mcp_server) as client:
        await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)}
        )
        result = await client.call_tool(
            "list_indexed_documents", {}
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        # Check shape
        first = data[0]
        assert "source" in first
        assert "chunks" in first


# ── Parameter validation ───────────────────────────────────────────────────


async def test_search_without_query_returns_error(mcp_server) -> None:
    """Calling search_documents without query must return an error."""
    async with connected_client(mcp_server) as client:
        # FastMCP wraps pydantic validation errors as isError=True
        result = await client.call_tool("search_documents", {})
        assert result.isError is True
        # Verify the error mentions the missing field
        error_text = result.content[0].text
        assert "query" in error_text.lower()
        assert "required" in error_text.lower()


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_result(result):
    """Extract the data payload from a FastMCP CallToolResult.

    Handles both structuredContent (newer FastMCP) and TextContent
    (older fallback) response formats.
    """
    # Check for structured content first
    if hasattr(result, "structuredContent") and result.structuredContent:
        return result.structuredContent.get("result", result.structuredContent)

    # Fallback: parse TextContent
    if result.content and isinstance(result.content[0], TextContent):
        return json.loads(result.content[0].text)

    # Last resort: return raw
    return result
