"""Coverage for core paths the v2 refactor reshaped.

Task 12.2. Targets the Azure document branch in the chunker, the MCP
handlers' error contract (gotcha #1), and the new VectorStore.fetch_all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import connected_client
from omrg.core.settings import EffectiveSettings

# ── core/ingestion/chunker.py: the Azure document branch ────────────────


class TestAzureDocumentBranch:
    """document_backend='azure' routes PDFs/DOCX through Azure, then splits."""

    async def test_azure_backend_reads_and_chunks(self, tmp_path: Path) -> None:
        from llama_index.core import Document

        from omrg.core.ingestion.chunker import read_and_chunk_file_async

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        docs = [Document(text="Azure extracted prose. " * 40)]
        with patch(
            "omrg.integrations.azure.read_documents",
            AsyncMock(return_value=docs),
        ):
            nodes = await read_and_chunk_file_async(
                pdf,
                content_type="document",
                settings=EffectiveSettings(
                    document_backend="azure",
                    azure_doc_intelligence_endpoint="https://example.azure.com/",
                    azure_doc_intelligence_key="dummy-key",
                ),
            )
        assert nodes
        assert all(n.metadata.get("content_type") == "document" for n in nodes)

    async def test_azure_failure_degrades_to_local(self, tmp_path: Path) -> None:
        """An Azure error must not abort ingestion (ADR-024 graceful degradation).

        Under the registry dispatch the .md suffix never reaches the azure
        backend at all (registry suffix gate); the RuntimeError stub stays
        as a belt-and-braces guard for any future suffix drift.
        """
        from omrg.core.ingestion.chunker import read_and_chunk_file_async

        md = tmp_path / "notes.md"
        md.write_text("# Heading\n\n" + ("local fallback prose. " * 30))

        with patch(
            "omrg.integrations.azure.read_documents",
            AsyncMock(side_effect=RuntimeError("azure down")),
        ):
            nodes = await read_and_chunk_file_async(
                md, settings=EffectiveSettings(document_backend="azure")
            )
        assert nodes, "must fall back to local reading rather than return nothing"

    async def test_markdown_uses_the_markdown_chunk_size(self, tmp_path: Path) -> None:
        """.md files use markdown_chunk_size, other files use chunk_size."""
        from omrg.core.ingestion.chunker import read_and_chunk_file_async
        from omrg.core.settings import ChunkingBlock

        md = tmp_path / "big.md"
        md.write_text("# H\n\n" + ("word " * 2000))

        small = await read_and_chunk_file_async(
            md,
            settings=EffectiveSettings(
                chunking=ChunkingBlock(markdown_chunk_size=256, chunk_size=4096, chunk_overlap=16)
            ),
        )
        large = await read_and_chunk_file_async(
            md,
            settings=EffectiveSettings(
                chunking=ChunkingBlock(markdown_chunk_size=4096, chunk_size=256, chunk_overlap=16)
            ),
        )
        assert len(small) > len(large), (
            "markdown_chunk_size must drive .md splitting, not chunk_size"
        )


# ── core/vectordb: fetch_all and the default holder ─────────────────────


class TestFetchAll:
    """The bulk read added for the document graph (task 6.1)."""

    def _store(self, collection):
        from omrg.core.vectordb.chroma import ChromaVectorStore

        store = ChromaVectorStore(persist_dir="/tmp/x")
        store._get_collection = MagicMock(return_value=collection)
        return store

    def test_returns_payload_for_a_populated_collection(self) -> None:
        collection = MagicMock()
        collection.count.return_value = 2
        collection.get.return_value = {"ids": ["1", "2"], "metadatas": [{}, {}]}
        result = self._store(collection).fetch_all("documents", ["metadatas"])
        assert result is not None and result["ids"] == ["1", "2"]

    def test_empty_collection_returns_none(self) -> None:
        """Callers degrade gracefully rather than handling an empty payload."""
        collection = MagicMock()
        collection.count.return_value = 0
        assert self._store(collection).fetch_all("documents", ["metadatas"]) is None

    def test_missing_collection_returns_none(self) -> None:
        from omrg.core.vectordb.chroma import ChromaVectorStore

        store = ChromaVectorStore(persist_dir="/tmp/x")
        store._get_collection = MagicMock(side_effect=Exception("no such collection"))
        assert store.fetch_all("nope", ["metadatas"]) is None

    def test_read_error_returns_none(self) -> None:
        collection = MagicMock()
        collection.count.return_value = 3
        collection.get.side_effect = Exception("backend exploded")
        assert self._store(collection).fetch_all("documents", ["metadatas"]) is None


# ── transports/mcp.py: the error contract (gotcha #1) ───────────────────


class TestMcpHandlersNeverRaise:
    """Every handler returns a structured error rather than propagating."""

    @pytest.mark.parametrize(
        "tool, args",
        [
            ("search_documents", {"query": "x"}),
            ("list_indexed_documents", {}),
            ("get_codebase_map", {"path": "."}),
        ],
    )
    async def test_handler_returns_error_payload_on_failure(
        self, mcp_server, tool: str, args: dict
    ) -> None:
        """A core-layer exception becomes an error result, never a raise."""
        targets = {
            "search_documents": "omrg.transports.mcp.search.search",
            "list_indexed_documents": "omrg.transports.mcp.list._list_documents",
            "get_codebase_map": ("omrg.core.codebase.codebase_map.get_codebase_map_text"),
        }
        with patch(targets[tool], side_effect=RuntimeError("boom")):
            async with connected_client(mcp_server) as client:
                result = await client.call_tool(tool, args)
        text = result.content[0].text
        assert "boom" in text or "error" in text.lower()
        assert "Traceback" not in text


class TestMcpProfileResolutionErrors:
    """A bad collection profile tag surfaces as a structured error.

    ProfileResolver raises ValueError for an unknown or non-operational tag
    (e.g. a collection tagged 'hybrid'). Every handler that resolves a
    profile must convert that into the error contract rather than let it
    escape (gotcha #1).
    """

    async def test_ingest_reports_invalid_profile_tag(self, mcp_server) -> None:
        with patch.object(
            __import__("omrg.transports.mcp", fromlist=["_profile_resolver"]),
            "_profile_resolver",
        ) as resolver:
            resolver.resolve.side_effect = ValueError("tagged 'hybrid'")
            async with connected_client(mcp_server) as client:
                result = await client.call_tool(
                    "ingest_documents", {"path": ".", "collection": "bad"}
                )
        assert "hybrid" in result.content[0].text

    async def test_search_reports_invalid_profile_tag(self, mcp_server) -> None:
        with patch.object(
            __import__("omrg.transports.mcp", fromlist=["_profile_resolver"]),
            "_profile_resolver",
        ) as resolver:
            resolver.resolve.side_effect = ValueError("tagged 'hybrid'")
            async with connected_client(mcp_server) as client:
                result = await client.call_tool(
                    "search_documents", {"query": "x", "collection": "bad"}
                )
        assert "hybrid" in result.content[0].text


class TestMcpProfileChangeErrors:
    """change_collection_profile degrades on both the preview and apply paths."""

    async def test_preview_failure_returns_error(self, mcp_server) -> None:
        with patch(
            "omrg.core.profiles.generate_safety_contract",
            side_effect=RuntimeError("store unreachable"),
        ):
            async with connected_client(mcp_server) as client:
                result = await client.call_tool(
                    "change_collection_profile",
                    {"collection": "docs", "profile": "codebase"},
                )
        assert "store unreachable" in result.content[0].text

    async def test_apply_failure_returns_error(self, mcp_server) -> None:
        with patch(
            "omrg.core.profiles.apply_profile_change",
            side_effect=RuntimeError("write failed"),
        ):
            async with connected_client(mcp_server) as client:
                result = await client.call_tool(
                    "change_collection_profile",
                    {"collection": "docs", "profile": "codebase", "confirm": True},
                )
        assert "write failed" in result.content[0].text

    async def test_list_collections_failure_returns_error(self, mcp_server) -> None:
        with patch(
            "omrg.core.retrieval.list_collections",
            side_effect=RuntimeError("no store"),
        ):
            async with connected_client(mcp_server) as client:
                result = await client.call_tool("list_collections", {})
        assert "no store" in result.content[0].text
