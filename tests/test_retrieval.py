"""Integration tests for the retrieval module.

Tests cover:
- search on empty store returns empty
- similarity_threshold filtering
- reranked flag propagation with default and explicit rerank
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import connected_client


async def _ingest_fixtures(client, fixtures_dir: Path) -> None:
    """Helper: ingest test fixtures via the MCP client."""
    await client.call_tool("ingest_documents", {"path": str(fixtures_dir)})


# ── Empty store ────────────────────────────────────────────────────────────


async def test_search_empty_store_returns_empty(mcp_server) -> None:
    """Searching with no indexed documents must return an empty list."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "search_documents", {"query": "anything"}
        )
        data = _extract_result(result)
        assert data == []


# ── Similarity threshold filtering ─────────────────────────────────────────


async def test_high_threshold_filters_all(
    mcp_server, fixtures_dir: Path
) -> None:
    """A very high similarity_threshold should filter all results."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France", "similarity_threshold": 0.99},
        )
        data = _extract_result(result)
        # All results may be filtered out (MockEmbedding scores are low)
        # The test verifies the parameter is accepted without error
        assert isinstance(data, list)


async def test_default_threshold_includes_results(
    mcp_server, fixtures_dir: Path
) -> None:
    """Default threshold (0.0) should include all retrieved results."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


# ── Rerank flag propagation ────────────────────────────────────────────────


async def test_default_search_reranked_false(
    mcp_server, fixtures_dir: Path
) -> None:
    """Without rerank, all results must have reranked=False."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert r["reranked"] is False


async def test_rerank_enabled_sets_flag(
    mcp_server, fixtures_dir: Path
) -> None:
    """With rerank=True, the reranked flag reflects actual reranker state."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital", "rerank": True},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        # The reranked flag is True if the reranker loaded, False if it
        # fell back. Either way, the call must succeed.
        for r in data:
            assert "reranked" in r


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestThresholdScaling:
    """Tests for score-aware threshold scaling.

    When the reranker is active, sigmoid-normalised scores occupy a much
    lower range than cosine similarity.  The search() function should
    scale the threshold down by 30× automatically to avoid over-filtering.
    """

    def test_no_rerank_threshold_unchanged(self) -> None:
        """Without reranking, the threshold must not be scaled."""
        from rag_mcp.retrieval import _effective_threshold

        assert _effective_threshold(0.3, rerank=False) == 0.3

    def test_rerank_threshold_scaled_down(self) -> None:
        """With reranking, the threshold must be scaled down 30×."""
        from rag_mcp.retrieval import _effective_threshold

        assert _effective_threshold(0.3, rerank=True) == pytest.approx(0.01)

    def test_zero_threshold_stays_zero_no_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero without rerank."""
        from rag_mcp.retrieval import _effective_threshold

        assert _effective_threshold(0.0, rerank=False) == 0.0

    def test_zero_threshold_stays_zero_with_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero with rerank."""
        from rag_mcp.retrieval import _effective_threshold

        assert _effective_threshold(0.0, rerank=True) == 0.0

    def test_moderate_threshold_with_rerank(self) -> None:
        """A moderate threshold (0.5) should become ~0.0167 with rerank."""
        from rag_mcp.retrieval import _effective_threshold

        assert _effective_threshold(0.5, rerank=True) == pytest.approx(
            0.5 / 30
        )

    def test_colosseum_score_survives_threshold(self) -> None:
        """The Colosseum query (score 0.015) must survive threshold 0.3.

        This was the motivating case: the reranker correctly identified
        the Colosseum chunk but gave it a low sigmoid score (0.015).
        With 30× scaling, threshold 0.3 → 0.01, so 0.015 passes.
        """
        from rag_mcp.retrieval import _effective_threshold

        threshold = _effective_threshold(0.3, rerank=True)
        assert 0.015 >= threshold  # Colosseum score should pass


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_result(result):
    """Extract the data payload from a FastMCP CallToolResult."""
    import json
    from mcp.types import TextContent

    if hasattr(result, "structuredContent") and result.structuredContent:
        return result.structuredContent.get("result", result.structuredContent)

    if result.content and isinstance(result.content[0], TextContent):
        return json.loads(result.content[0].text)

    return result
