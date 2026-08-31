"""Responsiveness tests for async ingestion path.

Verifies that the event loop remains responsive to concurrent tool calls
during a long-running ingest operation, the core motivation for the async
refactor (ADR-014).

Uses ``asyncio.Event`` to control ingest timing so tests can reliably
interleave a search with an in-progress ingest. Stage 3 unchanged-file skips
are deliberately invalidated with a chunk-size change when a test needs a
second ingest to remain in flight.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def pause_event() -> asyncio.Event:
    """Return an Event that the patched ingest function will wait on.

    The test sets this event to unblock the ingest after verifying
    responsiveness.
    """
    return asyncio.Event()


async def _patched_read_and_chunk(file_path, **kwargs):
    """Pause until ``_pause`` is set, then delegate to the real chunker.

    Takes ``**kwargs`` deliberately. Pinning the exact helper signature made
    older versions of this test pass against an ingest that failed before it
    was actually in flight when new chunker parameters were introduced.
    """
    from rag_mcp.core.ingestion import chunker as _chunker

    await _pause.wait()
    return await _chunker.read_and_chunk_file_async(file_path, **kwargs)


class TestIngestResponsiveness:
    """Verify the event loop remains responsive during ingest."""

    async def test_search_responsive_during_inflight_ingest(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """Concurrent MCP search returns while ingest is blocked mid-flight."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.transports.mcp import search_documents

        coll = "resp_test"
        await ingest_path_async(dir_with_docs, collection_name=coll)

        global _pause
        _pause = asyncio.Event()

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _patched_read_and_chunk,
        )

        # Change an index-shaping input so Stage 3's unchanged-source gate
        # cannot legitimately skip the patched read path.
        ingest_task = asyncio.create_task(
            ingest_path_async(
                dir_with_docs,
                chunk_size=128,
                collection_name=coll,
            )
        )

        await asyncio.sleep(0.1)

        results = await asyncio.wait_for(
            search_documents("test", top_k=5, collection=coll), timeout=30
        )

        assert not ingest_task.done(), (
            "ingest finished before the search - the test no longer proves "
            "the loop stayed responsive DURING ingest"
        )
        assert not _pause.is_set(), "ingest was unblocked too early"
        assert isinstance(results, list)

        _pause.set()
        await ingest_task

    async def test_list_collections_responds_during_ingest(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """Concurrent ``list_collections`` returns during in-flight ingest."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import list_collections

        coll = "list_resp"
        await ingest_path_async(dir_with_docs, collection_name=coll)

        global _pause
        _pause = asyncio.Event()
        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _patched_read_and_chunk,
        )

        ingest_task = asyncio.create_task(
            ingest_path_async(
                dir_with_docs,
                chunk_size=128,
                collection_name=coll,
            )
        )
        await asyncio.sleep(0.1)

        result = list_collections()

        assert not ingest_task.done(), (
            "ingest finished before list_collections - no longer proves "
            "responsiveness during ingest"
        )
        assert not _pause.is_set(), "ingest was unblocked too early"
        assert isinstance(result, list)

        _pause.set()
        await ingest_task

    async def test_async_search_offloads_blocking_retrieval(self, monkeypatch) -> None:
        """Slow synchronous retrieval runs in a worker, not the event loop."""
        from rag_mcp.transports.mcp import search_documents

        def slow_search(*args, **kwargs):
            time.sleep(0.3)
            return [
                {
                    "score": 1.0,
                    "source": "slow.txt",
                    "page_label": None,
                    "text": "slow result",
                    "reranked": False,
                }
            ]

        monkeypatch.setattr("rag_mcp.transports.mcp.search.search", slow_search)

        search_task = asyncio.create_task(search_documents("slow"))
        await asyncio.sleep(0.05)

        await asyncio.sleep(0.01)
        assert not search_task.done(), (
            "the blocking search completed before the loop yielded - it is "
            "not running in a worker thread, or the sleep was too long"
        )
        assert await search_task == [
            {
                "score": 1.0,
                "source": "slow.txt",
                "page_label": None,
                "text": "slow result",
                "reranked": False,
            }
        ]


class TestResponsivenessRegression:
    """Prove the test catches a blocking ingest - the safety net."""

    async def test_blocking_call_causes_responsiveness_failure(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """Insert ``time.sleep(2)`` into the async path; confirm test catches it."""
        import rag_mcp.core.ingestion.pipeline as _ing

        original = _ing.read_and_chunk_file_async

        async def _blocking_patched(
            file_path, chunk_size=None, chunk_overlap=None, content_type=None, **kwargs
        ):
            time.sleep(2)
            return await original(
                file_path,
                chunk_size,
                chunk_overlap,
                content_type=content_type,
                **kwargs,
            )

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _blocking_patched,
        )

        from rag_mcp.core.ingestion import ingest_path_async

        coll = "regress_test"
        start = time.monotonic()

        await ingest_path_async(dir_with_docs, collection_name=coll)

        ingest_task = asyncio.create_task(
            ingest_path_async(
                dir_with_docs,
                chunk_size=128,
                collection_name=coll,
            )
        )

        await asyncio.sleep(0.15)
        await asyncio.sleep(0.01)

        await ingest_task
        elapsed = time.monotonic() - start

        assert elapsed > 2.0, (
            f"Total test elapsed only {elapsed:.1f}s - the blocking "
            "`time.sleep(2)` was not triggered. The responsiveness "
            "regression test may not actually detect blocking calls."
        )


class TestSplitterOffload:
    """Verify SentenceSplitter work is offloaded from the event loop."""

    async def test_search_responsive_during_blocking_splitter(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """A slow splitter must not stall a concurrent search call."""
        from llama_index.core.node_parser import SentenceSplitter

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.transports.mcp import search_documents

        coll = "splitter_offload"
        await ingest_path_async(dir_with_docs, collection_name=coll)

        original_get_nodes = SentenceSplitter.get_nodes_from_documents
        release = threading.Event()
        entered = threading.Event()

        def _slow_get_nodes(self, documents, *args, **kwargs):
            entered.set()
            release.wait(timeout=30)
            return original_get_nodes(self, documents, *args, **kwargs)

        monkeypatch.setattr(
            SentenceSplitter,
            "get_nodes_from_documents",
            _slow_get_nodes,
        )

        ingest_task = asyncio.create_task(
            ingest_path_async(
                dir_with_docs,
                chunk_size=128,
                collection_name=coll,
            )
        )

        await asyncio.to_thread(entered.wait, 10)

        results = await asyncio.wait_for(
            search_documents("test", top_k=5, collection=coll), timeout=10
        )

        assert not ingest_task.done(), (
            "the ingest finished before the search - the blocking splitter "
            "was not actually in flight, so this proves nothing"
        )
        assert isinstance(results, list)

        release.set()
        await ingest_task
