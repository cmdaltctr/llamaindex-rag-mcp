"""Responsiveness tests for async ingestion path.

Verifies that the event loop remains responsive to concurrent tool calls
during a long-running ingest operation — the core motivation for the
async refactor (ADR-014).

Uses ``asyncio.Event`` to control ingest timing so tests can reliably
interleave a search with an in-progress ingest.
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

    Takes ``**kwargs`` deliberately. The previous version pinned the exact
    signature (``chunk_size``/``chunk_overlap`` only); when the real function
    gained parameters, every call raised TypeError, the ingest failed
    instantly, and the "responsive during ingest" tests passed against an
    ingest that was never actually in flight.
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

        # Pre-populate so search has data to find.
        coll = "resp_test"
        await ingest_path_async(dir_with_docs, collection_name=coll)

        # Patch the read function to block on an Event.
        global _pause
        _pause = asyncio.Event()

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _patched_read_and_chunk,
        )

        # Start re-ingest — it will block inside _patched_read_and_chunk.
        ingest_task = asyncio.create_task(
            ingest_path_async(dir_with_docs, collection_name=coll)
        )

        # Give the task a moment to enter the patched function.
        await asyncio.sleep(0.1)

        # Search must complete WHILE the ingest is still parked on the event.
        #
        # This asserts the property directly instead of timing it. If the
        # ingest were blocking the loop, this await could not proceed at all
        # until `_pause` is set, so `wait_for` would time out. The 10s budget
        # is a hang-guard, not a performance bar — a wall-clock upper bound
        # like `elapsed < 0.5` measured how busy the machine was, not whether
        # the loop was blocked, and flaked under parallel load.
        results = await asyncio.wait_for(
            search_documents("test", top_k=5, collection=coll), timeout=10
        )

        assert not ingest_task.done(), (
            "ingest finished before the search — the test no longer proves "
            "the loop stayed responsive DURING ingest"
        )
        assert not _pause.is_set(), "ingest was unblocked too early"
        assert isinstance(results, list)

        # Unblock and await ingest completion.
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
            ingest_path_async(dir_with_docs, collection_name=coll)
        )
        await asyncio.sleep(0.1)

        # Same property, same reasoning as the search test above.
        result = list_collections()

        assert not ingest_task.done(), (
            "ingest finished before list_collections — no longer proves "
            "responsiveness during ingest"
        )
        assert not _pause.is_set(), "ingest was unblocked too early"
        assert isinstance(result, list)

        _pause.set()
        await ingest_task

    async def test_async_search_offloads_blocking_retrieval(
        self, monkeypatch
    ) -> None:
        """Slow synchronous retrieval runs in a worker, not the event loop."""
        from rag_mcp.transports.mcp import search_documents

        def slow_search(*args, **kwargs):
            time.sleep(0.3)
            return [{
                "score": 1.0,
                "source": "slow.txt",
                "page_label": None,
                "text": "slow result",
                "reranked": False,
            }]

        monkeypatch.setattr("rag_mcp.transports.mcp.search", slow_search)

        search_task = asyncio.create_task(search_documents("slow"))
        await asyncio.sleep(0.05)

        # The loop must still be schedulable while the blocking search runs
        # in a worker thread. Asserted as "this coroutine got to run before
        # the search finished" rather than as a stopwatch reading.
        await asyncio.sleep(0.01)
        assert not search_task.done(), (
            "the blocking search completed before the loop yielded — it is "
            "not running in a worker thread, or the sleep was too long"
        )
        assert await search_task == [{
            "score": 1.0,
            "source": "slow.txt",
            "page_label": None,
            "text": "slow result",
            "reranked": False,
        }]


class TestResponsivenessRegression:
    """Prove the test catches a blocking ingest — the safety net."""

    async def test_blocking_call_causes_responsiveness_failure(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """Insert ``time.sleep(2)`` into the async path; confirm test catches it.

        Patches ``_read_and_chunk_file_async`` to block the event loop
        for 2 s.  If the test completes quickly, the patch was not
        triggered, meaning the safety net is broken.
        """
        import rag_mcp.core.ingestion.pipeline as _ing

        original = _ing.read_and_chunk_file_async

        async def _blocking_patched(file_path, chunk_size=None, chunk_overlap=None, content_type=None, **kwargs):
            time.sleep(2)
            return await original(file_path, chunk_size, chunk_overlap, content_type=content_type)

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _blocking_patched,
        )

        from rag_mcp.core.ingestion import ingest_path_async

        coll = "regress_test"

        # Measure total time: pre-ingest provides data, re-ingest blocks.
        start = time.monotonic()

        await ingest_path_async(dir_with_docs, collection_name=coll)

        # Start re-ingest as a task — the patch adds a 2 s block.
        ingest_task = asyncio.create_task(
            ingest_path_async(dir_with_docs, collection_name=coll)
        )

        # Wait for the ingest to start and enter the blocking sleep.
        await asyncio.sleep(0.15)

        # Try to execute a simple coroutine.  If the event loop is
        # blocked by ``time.sleep(2)``, this will not complete until
        # the sleep finishes.
        await asyncio.sleep(0.01)

        # If we reach here, either:
        #   1. The sleep(2) finished -> the blocking call was exercised.
        #   2. The patch was never called.
        # We distinguish by checking total elapsed time.
        await ingest_task
        elapsed = time.monotonic() - start

        assert elapsed > 2.0, (
            f"Total test elapsed only {elapsed:.1f}s — the blocking "
            "`time.sleep(2)` was not triggered. The responsiveness "
            "regression test may not actually detect blocking calls."
        )


class TestSplitterOffload:
    """Verify the SentenceSplitter call is offloaded from the event loop.

    The wider responsiveness tests above patch
    ``_read_and_chunk_file_async`` in full, so they cannot catch a
    regression where the splitter slips back onto the event-loop thread.
    These tests inject a blocking splitter directly and prove the
    surrounding loop stays responsive.
    """

    async def test_search_responsive_during_blocking_splitter(
        self, dir_with_docs: str, monkeypatch
    ) -> None:
        """A slow splitter must not stall a concurrent search call."""
        from llama_index.core.node_parser import SentenceSplitter

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.transports.mcp import search_documents

        coll = "splitter_offload"

        # Pre-populate so search has something to retrieve.
        await ingest_path_async(dir_with_docs, collection_name=coll)

        original_get_nodes = SentenceSplitter.get_nodes_from_documents

        # Gate the splitter on an Event rather than a fixed sleep. With
        # `time.sleep(0.6)` the ingest could finish before the search under
        # CPU load, and the test then asserted nothing. The Event holds the
        # splitter open until the search has demonstrably completed.
        release = threading.Event()
        entered = threading.Event()

        def _slow_get_nodes(self, documents, *args, **kwargs):
            # Synchronous block — only safe if offloaded to a worker thread.
            entered.set()
            release.wait(timeout=30)
            return original_get_nodes(self, documents, *args, **kwargs)

        monkeypatch.setattr(
            SentenceSplitter,
            "get_nodes_from_documents",
            _slow_get_nodes,
        )

        ingest_task = asyncio.create_task(
            ingest_path_async(dir_with_docs, collection_name=coll)
        )

        # Wait until the splitter is genuinely blocking, rather than
        # guessing with a sleep.
        await asyncio.to_thread(entered.wait, 10)

        # Deterministic form, matching the other responsiveness tests: the
        # search must complete while the blocking splitter is still running,
        # not merely "within 0.5s" — which measured machine load.
        results = await asyncio.wait_for(
            search_documents("test", top_k=5, collection=coll), timeout=10
        )

        assert not ingest_task.done(), (
            "the ingest finished before the search — the blocking splitter "
            "was not actually in flight, so this proves nothing"
        )
        assert isinstance(results, list)

        release.set()
        await ingest_task
