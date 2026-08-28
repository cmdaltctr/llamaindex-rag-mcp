"""Integration tests for MCP tool routing via in-memory ClientSession.

Tests cover:
- Tool discovery (list_tools)
- ingest_documents tool
- search_documents tool
- list_indexed_documents tool
- Parameter validation
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from conftest import connected_client
from mcp.types import TextContent


# ── Tool discovery ─────────────────────────────────────────────────────────


async def test_list_tools_discovers_all_seven(mcp_server) -> None:
    """The server must expose all expected tools."""
    async with connected_client(mcp_server) as client:
        result = await client.list_tools()
        tool_names = {t.name for t in result.tools}
        assert tool_names == {
            "ingest_documents",
            "search_documents",
            "list_indexed_documents",
            "list_collections",
            "delete_documents",
            "get_codebase_map",
            "change_collection_profile",
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


async def test_search_documents_handler_is_async_and_preserves_shape(
    mcp_server,
) -> None:
    """MCP search handler is async and returns the same list-of-dicts shape."""
    import rag_mcp.transports.mcp as server

    expected = [{
        "score": 0.9,
        "source": "fixture.txt",
        "page_label": None,
        "text": "fixture text",
        "reranked": False,
    }]

    assert inspect.iscoroutinefunction(server.search_documents)

    with patch("rag_mcp.transports.mcp.search", return_value=expected) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {
                    "query": "fixture",
                    "top_k": 3,
                    "similarity_threshold": 0.25,
                    "rerank": True,
                    "collection": "mcp_shape_coll",
                },
            )

    data = _extract_result(result)
    assert data == expected
    mock_search.assert_called_once_with(
        "fixture",
        top_k=3,
        similarity_threshold=0.25,
        rerank=True,
        hybrid=False,
        collection_name="mcp_shape_coll",
        metadata_filter=None,
        reranker=ANY,
        effective_settings=ANY,
    )


async def test_search_documents_defaults_follow_policy_resolver(mcp_server) -> None:
    """MCP omitted rerank should pass None so retrieval resolves policy."""
    from rag_mcp.config import get_settings as _gs

    expected = [{
        "score": 0.9,
        "source": "fixture.txt",
        "page_label": None,
        "text": "fixture text",
        "reranked": False,
    }]

    with patch("rag_mcp.transports.mcp.search", return_value=expected) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {"query": "fixture"},
            )

    data = _extract_result(result)
    assert data == expected
    mock_search.assert_called_once_with(
        "fixture",
        top_k=_gs().retrieval.top_k,
        similarity_threshold=_gs().retrieval.similarity_threshold,
        rerank=None,
        hybrid=_gs().retrieval.hybrid_enabled,
        collection_name="documents",
        metadata_filter=None,
        reranker=ANY,
        effective_settings=ANY,
    )


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


# ── 9.14 Collection parameter tests ─────────────────────────────────────────


async def test_ingest_with_collection_parameter(
    mcp_server, fixtures_dir: Path,
) -> None:
    """ingest_documents with collection param must store in named collection."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_test_coll"},
        )
        data = _extract_result(result)
        # Should succeed and use the named collection
        assert "files_indexed" in data
        assert data.get("collection") == "mcp_test_coll"


async def test_search_with_collection_parameter(
    mcp_server, fixtures_dir: Path,
) -> None:
    """search_documents with collection param must search named collection."""
    async with connected_client(mcp_server) as client:
        # First ingest into a named collection
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_search_coll"},
        )
        # Then search that collection
        result = await client.call_tool(
            "search_documents",
            {"query": "sample", "collection": "mcp_search_coll"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)


async def test_list_with_collection_parameter(
    mcp_server, fixtures_dir: Path,
) -> None:
    """list_indexed_documents with collection param must list named collection."""
    async with connected_client(mcp_server) as client:
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_list_coll"},
        )
        result = await client.call_tool(
            "list_indexed_documents",
            {"collection": "mcp_list_coll"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) >= 1


async def test_list_collections_tool(
    mcp_server, fixtures_dir: Path,
) -> None:
    """list_collections tool must return available collections."""
    async with connected_client(mcp_server) as client:
        # Ingest into two different collections
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "coll_a"},
        )
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "coll_b"},
        )

        result = await client.call_tool("list_collections", {})
        data = _extract_result(result)
        assert isinstance(data, list)

        # Must include both collections
        names = {c.get("name") for c in data}
        assert "coll_a" in names
        assert "coll_b" in names


# ── 9.15 Backward compatibility tests ──────────────────────────────────────


async def test_ingest_without_collection_defaults_to_documents(
    mcp_server, fixtures_dir: Path,
) -> None:
    """ingest_documents without collection must use 'documents' collection."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)},
        )
        data = _extract_result(result)
        # Should work without specifying collection
        assert "status" in data


async def test_search_without_collection_defaults_to_documents(
    mcp_server,
) -> None:
    """search_documents without collection must work with default."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "search_documents", {"query": "anything"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)


async def test_list_without_collection_defaults_to_documents(
    mcp_server,
) -> None:
    """list_indexed_documents without collection must work with default."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("list_indexed_documents", {})
        data = _extract_result(result)
        assert isinstance(data, list)


# ── delete_documents MCP tool tests ──────────────────────────────────────────


async def test_delete_documents_by_path(
    mcp_server, fixtures_dir: Path,
) -> None:
    """delete_documents with path must remove chunks and return count."""
    async with connected_client(mcp_server) as client:
        # First ingest
        ingest_result = await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)},
        )
        ingest_data = _extract_result(ingest_result)
        assert ingest_data["status"] == "ok"

        # Delete by path of one file
        sample_file = fixtures_dir / "sample.txt"
        result = await client.call_tool(
            "delete_documents", {"path": str(sample_file)},
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["mode"] == "path"
        assert "chunks_removed" in data


async def test_delete_documents_dry_run(
    mcp_server, fixtures_dir: Path,
) -> None:
    """delete_documents with dry_run must preview without deleting."""
    async with connected_client(mcp_server) as client:
        # First ingest
        await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)},
        )

        # Dry run
        sample_file = fixtures_dir / "sample.txt"
        result = await client.call_tool(
            "delete_documents",
            {"path": str(sample_file), "dry_run": True},
        )
        data = _extract_result(result)
        assert data.get("dry_run") is True
        assert "would_delete" in data


async def test_delete_documents_drop_collection(
    mcp_server, fixtures_dir: Path,
) -> None:
    """delete_documents with only collection must drop the collection."""
    async with connected_client(mcp_server) as client:
        # Ingest into named collection
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_drop_coll"},
        )

        # Drop collection
        result = await client.call_tool(
            "delete_documents", {"collection": "mcp_drop_coll"},
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["mode"] == "collection"


async def test_delete_documents_collection_dry_run(
    mcp_server, fixtures_dir: Path,
) -> None:
    """delete_documents with collection + dry_run must preview drop."""
    async with connected_client(mcp_server) as client:
        # Ingest into the collection first so the success branch is hit.
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_preview_coll"},
        )

        result = await client.call_tool(
            "delete_documents",
            {"collection": "mcp_preview_coll", "dry_run": True},
        )
        data = _extract_result(result)
        assert data.get("dry_run") is True
        assert data.get("mode") == "collection"
        assert data.get("would_delete", 0) >= 1


async def test_delete_documents_by_metadata_filter(
    mcp_server, fixtures_dir: Path,
) -> None:
    """delete_documents with metadata_filter must remove matching chunks."""
    async with connected_client(mcp_server) as client:
        # Ingest first
        await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)},
        )

        # Delete by metadata (just use a non-matching filter)
        result = await client.call_tool(
            "delete_documents",
            {"metadata_filter": {"category": "nonexistent"}},
        )
        data = _extract_result(result)
        # Should succeed with 0 removed (filter matches nothing)
        assert data["status"] == "ok"
        assert data.get("chunks_removed", 0) == 0


# ── delete_documents edge-case tests ────────────────────────────────────────


async def test_delete_documents_empty_metadata_filter_error(
    mcp_server,
) -> None:
    """delete_documents with empty metadata_filter must return an error."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "delete_documents",
            {"metadata_filter": {}},
        )
        data = _extract_result(result)
        assert data["status"] == "error"
        assert "metadata_filter must be a non-empty dict" in data["message"]


async def test_delete_documents_metadata_dry_run_with_match(
    mcp_server, fixtures_dir: Path,
) -> None:
    """metadata_filter + dry_run on ingested data must preview matching count."""
    async with connected_client(mcp_server) as client:
        # Ingest first so there are chunks with file_name metadata.
        await client.call_tool(
            "ingest_documents", {"path": str(fixtures_dir)},
        )

        # Use file_name metadata which is always present on ingested chunks.
        result = await client.call_tool(
            "delete_documents",
            {
                "metadata_filter": {"file_name": "sample.txt"},
                "dry_run": True,
            },
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["dry_run"] is True
        assert data["mode"] == "metadata"
        assert data["would_delete"] >= 1


async def test_delete_documents_metadata_dry_run_nonexistent_coll(
    mcp_server,
) -> None:
    """metadata_filter + dry_run on a non-existent collection must return 0."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "delete_documents",
            {
                "metadata_filter": {"category": "research"},
                "dry_run": True,
                "collection": "coll_does_not_exist",
            },
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["dry_run"] is True
        assert data["mode"] == "metadata"
        assert data["would_delete"] == 0


async def test_delete_documents_collection_dry_run_nonexistent_coll(
    mcp_server,
) -> None:
    """collection-mode dry_run on a non-existent collection must return 0."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "delete_documents",
            {"collection": "coll_does_not_exist", "dry_run": True},
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["dry_run"] is True
        assert data["mode"] == "collection"
        assert data["would_delete"] == 0


async def test_delete_documents_path_dry_run_nonexistent_coll(
    mcp_server, sample_txt: Path,
) -> None:
    """path-mode dry_run on a non-existent collection must return would_delete: 0."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "delete_documents",
            {
                "path": str(sample_txt),
                "dry_run": True,
                "collection": "coll_does_not_exist",
            },
        )
        data = _extract_result(result)
        assert data["status"] == "ok"
        assert data["dry_run"] is True
        assert data["mode"] == "path"
        assert data["would_delete"] == 0


# ── main() entry-point test ────────────────────────────────────────────────


def test_main_calls_mcp_run() -> None:
    """main() must configure logging and call mcp.run(transport='stdio')."""
    with patch("rag_mcp.transports.mcp.mcp.run") as mock_run:
        from rag_mcp.transports.mcp import main

        main()

    mock_run.assert_called_once_with(transport="stdio")


# ── search_documents: metadata_filter exposure ─────────────────────────────


async def test_search_documents_metadata_filter_passed_through(
    mcp_server,
) -> None:
    """metadata_filter param must reach retrieval.search() unchanged."""
    expected = [{
        "score": 0.9,
        "source": "ai.txt",
        "page_label": None,
        "text": "ai content",
        "reranked": False,
    }]

    with patch(
        "rag_mcp.transports.mcp.search", return_value=expected,
    ) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {
                    "query": "attention",
                    "metadata_filter": {"category": "ai"},
                    "collection": "filtered_coll",
                },
            )

    data = _extract_result(result)
    assert data == expected
    # The filter must reach retrieval.search untouched.
    _, kwargs = mock_search.call_args
    assert kwargs["metadata_filter"] == {"category": "ai"}


async def test_search_documents_returns_filter_matches(
    mcp_server, tmp_path: Path, monkeypatch,
) -> None:
    """End-to-end: a filtered MCP search returns only matching chunks."""
    import rag_mcp.config as _config
    from rag_mcp.core.settings import EffectiveSettings, MetadataBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword", keyword_rules=None)))

    ai_doc = tmp_path / "ai.txt"
    ai_doc.write_text(
        "transformer attention heads. deep learning neural networks. "
        "embeddings drive llm performance."
    )

    async with connected_client(mcp_server) as client:
        await client.call_tool(
            "ingest_documents",
            {"path": str(ai_doc), "collection": "mcp_filter"},
        )

        # Filter that should not match anything.
        result = await client.call_tool(
            "search_documents",
            {
                "query": "attention",
                "collection": "mcp_filter",
                "metadata_filter": {"category": "philosophy"},
            },
        )
        data = _extract_result(result)
        assert data == []

        # Unfiltered: should return at least one result.
        result_open = await client.call_tool(
            "search_documents",
            {"query": "attention", "collection": "mcp_filter"},
        )
        open_data = _extract_result(result_open)
        assert isinstance(open_data, list)
        assert len(open_data) > 0


async def test_search_documents_unfiltered_unchanged(mcp_server) -> None:
    """Unfiltered search must pass metadata_filter=None to retrieval."""
    expected: list[dict] = []

    with patch(
        "rag_mcp.transports.mcp.search", return_value=expected,
    ) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents", {"query": "anything"},
            )

    data = _extract_result(result)
    assert data == []
    _, kwargs = mock_search.call_args
    assert kwargs["metadata_filter"] is None


# ── search_documents: error envelope ───────────────────────────────────────


async def test_search_documents_validation_error_envelope(
    mcp_server,
) -> None:
    """A ValueError from search → validation envelope, no exception."""
    def _raise_value_error(*args, **kwargs):
        raise ValueError("Invalid where clause: unsupported operator $bogus")

    with patch("rag_mcp.transports.mcp.search", side_effect=_raise_value_error):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {
                    "query": "anything",
                    "metadata_filter": {"category": {"$bogus": "x"}},
                },
            )

    data = _extract_result(result)
    assert isinstance(data, list)
    assert len(data) == 1
    err = data[0]
    assert err["status"] == "error"
    assert err["error_type"] == "validation"
    assert "unsupported operator" in err["message"].lower()


async def test_search_documents_retrieval_error_envelope(
    mcp_server,
) -> None:
    """A ChromaDB failure during search → retrieval envelope."""
    # Forge an exception class whose ``__module__`` lives under chromadb,
    # without importing chromadb.errors directly (which moves between
    # versions).  This matches the production-side discriminator in
    # rag_mcp.transports.mcp.search_documents.
    fake_chroma = type(
        "ChromaError",
        (RuntimeError,),
        {"__module__": "chromadb.errors"},
    )

    def _raise_chroma(*args, **kwargs):
        raise fake_chroma("collection 'x' is corrupt")

    with patch("rag_mcp.transports.mcp.search", side_effect=_raise_chroma):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents", {"query": "anything"},
            )

    data = _extract_result(result)
    assert isinstance(data, list)
    assert len(data) == 1
    err = data[0]
    assert err["status"] == "error"
    assert err["error_type"] == "retrieval"
    assert "corrupt" in err["message"]


async def test_search_documents_internal_error_envelope(
    mcp_server,
) -> None:
    """An unexpected non-ChromaDB error → internal envelope."""
    def _raise_unexpected(*args, **kwargs):
        raise KeyError("missing config key 'foo'")

    with patch("rag_mcp.transports.mcp.search", side_effect=_raise_unexpected):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents", {"query": "anything"},
            )

    data = _extract_result(result)
    assert isinstance(data, list)
    assert len(data) == 1
    err = data[0]
    assert err["status"] == "error"
    assert err["error_type"] == "internal"


async def test_search_documents_success_has_no_status_key(
    mcp_server,
) -> None:
    """Successful results must not contain a 'status' key on any dict."""
    expected = [
        {
            "score": 0.9,
            "source": "a.txt",
            "page_label": None,
            "text": "first",
            "reranked": False,
        },
        {
            "score": 0.5,
            "source": "b.txt",
            "page_label": 1,
            "text": "second",
            "reranked": False,
        },
    ]

    with patch("rag_mcp.transports.mcp.search", return_value=expected):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents", {"query": "anything"},
            )

    data = _extract_result(result)
    assert data == expected
    for entry in data:
        assert "status" not in entry


# ── get_codebase_map ───────────────────────────────────────────────────────


async def test_get_codebase_map_handler_is_callable(mcp_server, tmp_path) -> None:
    """The handler must actually run — not just appear in the tool list.

    Regression test for a broken relative import (``.core`` instead of
    ``..core``) that made this tool raise ``ModuleNotFoundError`` out of the
    handler, violating AGENTS.md gotcha #1. The pre-existing tool-list test
    only asserted the *name* was registered, so it never caught this.
    """
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "get_codebase_map", {"path": str(tmp_path), "refresh": False}
        )
        # Must return content rather than raising out of the handler.
        assert result.content
        text = result.content[0].text
        assert isinstance(text, str) and text
        # If it failed, it must be the structured error contract (gotcha #1),
        # never an unhandled ModuleNotFoundError.
        assert "ModuleNotFoundError" not in text
