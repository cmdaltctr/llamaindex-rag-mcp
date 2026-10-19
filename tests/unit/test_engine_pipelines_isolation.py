"""Engine graph leases, serialisation and isolation (task 4.3).

Covers two Engines that run at the same time without shared state,
``close()`` during an active run, and poisoned process defaults. The run
lock per Engine is covered in ``test_engine_pipelines_locking.py``.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from tests.unit.test_engine_pipelines_support import (
    FakeEmbedder,
    FakeStore,
    build_engine,
    chunks,
    retrieval_graph,
)

from omrg.core.pipelines import RunStatus


async def _until(event: threading.Event) -> None:
    """Wait for a thread event without blocking the loop."""
    for _ in range(1000):
        if event.is_set():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the store was never entered")


def test_two_engines_run_concurrently_and_stay_isolated(effective_settings) -> None:
    """Two Engines with different settings and stores run at the same time."""
    store_a, store_b = FakeStore(chunks("a")), FakeStore(chunks("b", count=4))
    barrier = threading.Barrier(2, timeout=5)
    store_a.barrier = store_b.barrier = barrier
    engine_a = build_engine(effective_settings(top_k=1), store_a, embed_model=FakeEmbedder("m-a"))
    engine_b = build_engine(effective_settings(top_k=3), store_b, embed_model=FakeEmbedder("m-b"))

    async def both():
        return await asyncio.gather(
            engine_a.run_pipeline(retrieval_graph(), inputs={"query": "q"}),
            engine_b.run_pipeline(retrieval_graph(), inputs={"query": "q"}),
        )

    result_a, result_b = asyncio.run(both())
    assert result_a.status is RunStatus.SUCCEEDED, result_a.error
    assert result_b.status is RunStatus.SUCCEEDED, result_b.error
    rows_a = result_a.outputs["context"].public_rows()
    rows_b = result_b.outputs["context"].public_rows()
    assert [r["source_id"] for r in rows_a] == ["a-s0"]
    assert [r["source_id"] for r in rows_b] == ["b-s0", "b-s1", "b-s2"]
    embedding_a = result_a.outputs["context"].provenance.embedding
    assert embedding_a is not None and embedding_a.model == "m-a"
    assert engine_a._pipelines is not engine_b._pipelines
    assert engine_a._pipelines.catalogue() is not engine_b._pipelines.catalogue()
    engine_b.close()
    store_a.barrier = None
    again = asyncio.run(engine_a.run_pipeline(retrieval_graph(), inputs={"query": "q"}))
    assert again.status is RunStatus.SUCCEEDED and not store_a.closed


def test_close_during_a_run_fails_and_keeps_the_engine_usable(effective_settings) -> None:
    """close() reports active work, keeps resources, then works after the drain."""
    store = FakeStore(chunks())
    store.gate = threading.Event()
    engine = build_engine(effective_settings(), store)

    async def scenario():
        run = asyncio.create_task(engine.run_pipeline(retrieval_graph(), inputs={"query": "q"}))
        await _until(store.entered)
        with pytest.raises(RuntimeError, match="active graph run"):
            engine.close()
        assert not store.closed and engine._store is store
        store.gate.set()
        return await run

    result = asyncio.run(scenario())
    assert result.status is RunStatus.SUCCEEDED
    engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    engine.close()
    assert store.closed
    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(engine.run_pipeline(retrieval_graph(), inputs={"query": "q"}))


def test_failed_run_releases_its_lease(effective_settings) -> None:
    """A run that fails at runtime releases the lease, so close() works."""

    class BrokenStore(FakeStore):
        def query_dense(self, *args, **kwargs):
            raise OSError("disk gone")

    store = BrokenStore(chunks())
    engine = build_engine(effective_settings(), store)
    result = asyncio.run(engine.run_pipeline(retrieval_graph(), inputs={"query": "q"}))
    assert result.status is RunStatus.FAILED and result.failed_node == "dense"
    engine.close()
    assert store.closed


def test_poisoned_process_defaults_are_never_read(monkeypatch, effective_settings) -> None:
    """Validation and execution use only the Engine's own composition."""
    import llama_index.core

    from omrg.core import settings as settings_mod
    from omrg.core import vectordb
    from omrg.core.retrieval import pipeline

    def poisoned(*args, **kwargs):
        raise AssertionError("process default read")

    for target, name in (
        (settings_mod, "get_default_effective_settings"),
        (settings_mod, "resolve_effective_settings"),
        (vectordb, "get_default_store"),
        (pipeline, "get_default_store"),
        (pipeline, "resolve_effective_settings"),
    ):
        monkeypatch.setattr(target, name, poisoned)
    monkeypatch.setattr(
        type(llama_index.core.Settings), "embed_model", property(poisoned), raising=False
    )
    engine = build_engine(effective_settings())
    engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    result = asyncio.run(engine.run_pipeline(retrieval_graph(), inputs={"query": "q"}))
    assert result.status is RunStatus.SUCCEEDED, result.error
