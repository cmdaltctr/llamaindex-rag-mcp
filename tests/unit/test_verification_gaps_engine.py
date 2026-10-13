"""Engine-scoped composition gaps from the verification report (section B).

Covers four scenarios that had code but no test:

* ``build_engine`` leaves the process-default settings, store and
  embedder untouched.
* The process-wide reranker model cache survives another Engine's close.
* An Engine call after a cancelled run works, and the global ingestion
  ``shutdown_requested`` flag stays unset.
* One run cannot report another run's reranker failure reason.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_engine_pipelines_support import FakeStore, build_engine, chunks
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrg.core.ingestion._state import shutdown_requested
from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.pipelines import EventKind, NodeStatus, PipelineResult, RunCancellation, RunStatus
from omrg.core.retrieval import _reranker_cache
from omrg.core.retrieval.reranker import CrossEncoderReranker, reset_model_cache
from omrg.core.settings import EffectiveSettings, MetadataBlock
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.engine import Engine

_MODEL_ID = "fake-org/fake-cross-encoder"
_CACHE_KEY = ("onnx", _MODEL_ID)


def rerank_graph(**prepare_params: Any) -> dict[str, Any]:
    """Return prepare -> dense -> rerank (on) -> threshold -> context."""

    def edge(a: str, b: str, c: str, d: str) -> dict[str, Any]:
        return {"source": {"node": a, "port": b}, "target": {"node": c, "port": d}}

    return {
        "schema_version": 1,
        "nodes": [
            {"id": "prepare", "operation": "retrieve.prepare_query", "params": prepare_params},
            {"id": "dense", "operation": "retrieve.dense"},
            {"id": "rerank", "operation": "select.rerank", "params": {"enabled": True}},
            {"id": "select", "operation": "select.threshold"},
            {"id": "context", "operation": "context.assemble"},
        ],
        "edges": [
            edge("prepare", "query", "dense", "query"),
            edge("dense", "evidence", "rerank", "evidence"),
            edge("rerank", "evidence", "select", "evidence"),
            edge("select", "evidence", "context", "evidence"),
        ],
        "inputs": [
            {
                "name": "query",
                "kind": "query",
                "required": True,
                "targets": [{"node": "prepare", "port": "query"}],
            }
        ],
        "outputs": [{"name": "context", "source": {"node": "context", "port": "context"}}],
    }


def _node(result: PipelineResult, node_id: str) -> Any:
    return next(n for n in result.nodes if n.node_id == node_id)


# ── Construction leaves process defaults alone ───────────────────────────


def test_build_engine_leaves_process_defaults_unchanged(tmp_path: Path) -> None:
    """The default settings, store and LlamaIndex embedder are the same objects after."""
    from omrg.compose_engine import build_engine as compose_build_engine
    from omrg.core.settings import get_default_effective_settings
    from omrg.core.vectordb import get_default_store

    before = (
        get_default_effective_settings(),
        get_default_store(),
        LlamaIndexSettings.embed_model,
    )
    built = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "built"),
        collection_name="built_only",
    )
    with (
        patch("omrg.compose.build_embed_model", return_value=MagicMock(model_name="m")),
        patch("omrg.compose.build_vector_store", return_value=MagicMock()),
        patch("omrg.compose.settings_to_effective", return_value=built),
        patch("omrg.compose.build_reranker", return_value=None),
        patch("omrg.compose._resolve_active_strategies"),
        patch("omrg.compose._log_norm_guard_state"),
    ):
        engine = compose_build_engine(MagicMock())

    assert engine._effective_settings is built
    after = (
        get_default_effective_settings(),
        get_default_store(),
        LlamaIndexSettings.embed_model,
    )
    assert all(a is b for a, b in zip(before, after, strict=True))
    assert get_default_effective_settings().collection_name != "built_only"
    engine.close()
    assert get_default_effective_settings() is before[0]


# ── Shared model cache survives another Engine's close ──────────────────


class _FakeSession:
    """ONNX session double that scores later rows higher."""

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

    def run(self, _outputs: Any, feed: dict[str, Any]) -> list[Any]:
        count = len(feed["input_ids"])
        return [np.arange(count, dtype=np.float32).reshape(count, 1) + 2.0]


class _FakeTokenizer:
    """Tokenizer double with the ``tokenizers.Encoding`` attributes."""

    def encode_batch(self, batch: list[tuple[str, str]]) -> list[SimpleNamespace]:
        return [SimpleNamespace(ids=[1, 2], attention_mask=[1, 1], type_ids=[0, 0]) for _ in batch]


@pytest.fixture
def seeded_model_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, ...]]:
    """Seed the process-wide cache with a fake model; refuse any download."""
    import huggingface_hub

    def _no_download(*args: Any, **kwargs: Any) -> Any:
        raise OSError("tests never download a reranker model")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", _no_download)
    reset_model_cache()
    entry = (_FakeSession(), _FakeTokenizer(), 512)
    _reranker_cache._MODEL_CACHE[_CACHE_KEY] = entry
    yield entry
    reset_model_cache()


def test_model_cache_survives_another_engine_close(
    seeded_model_cache: tuple[Any, ...], effective_settings: Any
) -> None:
    """Closing Engine B keeps the shared model; Engine A still reranks."""
    store_a = FakeStore(chunks("a"))
    reranker_a = CrossEncoderReranker(model_id=_MODEL_ID)
    engine_a = build_engine(effective_settings(), store_a, reranker=reranker_a)
    engine_b = build_engine(
        effective_settings(), FakeStore(chunks("b")), reranker=CrossEncoderReranker(_MODEL_ID)
    )
    warm = asyncio.run(engine_b.run_pipeline(rerank_graph(), inputs={"query": "q"}))
    assert warm.status is RunStatus.SUCCEEDED, warm.error

    engine_b.close()
    summaries: list[dict[str, Any]] = []

    async def sink(event: Any) -> None:
        if event.kind == EventKind.NODE_COMPLETED and event.node_id == "rerank":
            summaries.append(dict(event.data))

    result = asyncio.run(
        engine_a.run_pipeline(rerank_graph(), inputs={"query": "q"}, on_event=sink)
    )

    assert _reranker_cache._MODEL_CACHE.get(_CACHE_KEY) is seeded_model_cache
    assert result.status is RunStatus.SUCCEEDED, result.error
    assert _node(result, "rerank").fallback is None
    assert summaries == [summaries[0]] and summaries[0]["reranked"] is True
    assert reranker_a.last_failure_reason is None
    assert not store_a.closed
    engine_a.close()


# ── Engine call after a cancelled run ────────────────────────────────────


def test_engine_call_after_cancelled_run_and_flag_stays_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """A cancelled graph run sets no global flag; the Engine keeps working."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    engine = Engine(
        offline_settings(effective_settings),
        store=store,
        embed_model=LlamaIndexSettings.embed_model,
    )
    token = RunCancellation()

    async def cancel_after_first_commit(event: Any) -> None:
        if event.kind == EventKind.EFFECT_COMMITTED:
            token.cancel("user request")

    assert not shutdown_requested.is_set()
    cancelled = asyncio.run(
        engine.run_pipeline(
            canonical_ingestion_definition("cancelled"),
            inputs={"path": str(root)},
            on_event=cancel_after_first_commit,
            cancellation=token,
        )
    )
    assert cancelled.status is RunStatus.CANCELLED
    assert not shutdown_requested.is_set()

    again = asyncio.run(
        engine.run_pipeline(canonical_ingestion_definition("after"), inputs={"path": str(root)})
    )
    assert again.status is RunStatus.SUCCEEDED, again.error
    assert len(again.completed_effects) == 3
    rows = engine.search("guide", collection_name="after")
    assert rows, "search after a cancelled run returned nothing"
    assert not shutdown_requested.is_set()
    engine.close()


# ── Reranker diagnostics belong to their own run ─────────────────────────


class _ScriptedReranker:
    """Shared reranker: query ``alpha`` fails, query ``beta`` succeeds.

    The failing call waits briefly for the other call to finish. Runs on
    one Engine are serialised, so the wait times out and the failing run
    reads its own reason. Without serialisation the other call would
    clear the shared reason before the failing run reads it.
    """

    backend_name = "scripted"

    def __init__(self) -> None:
        self.last_failure_reason: str | None = None
        self.beta_done = threading.Event()
        self.queries: list[str] = []

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        self.queries.append(query)
        self.last_failure_reason = None
        if query == "alpha":
            self.last_failure_reason = "inference failed: alpha only"
            self.beta_done.wait(timeout=0.5)
            for row in results:
                row["_reranked"] = False
            return results[:top_k]
        for index, row in enumerate(results):
            row["score"] = 0.99 - index * 0.01
            row["_reranked"] = True
        self.beta_done.set()
        return results[:top_k]


def test_one_run_cannot_report_another_runs_rerank_failure(effective_settings: Any) -> None:
    """Run A carries its failure reason; run B on the same Engine carries none."""
    reranker = _ScriptedReranker()
    settings = effective_settings(**{"retrieval.rerank_enabled": True})
    engine = build_engine(settings, FakeStore(chunks()), reranker=reranker)
    selects: dict[str, dict[str, Any]] = {}

    def sink_for(name: str) -> Any:
        async def sink(event: Any) -> None:
            if event.kind == EventKind.NODE_COMPLETED and event.node_id == "select":
                selects[name] = dict(event.data)

        return sink

    async def both() -> list[PipelineResult]:
        first = asyncio.create_task(
            engine.run_pipeline(rerank_graph(), inputs={"query": "alpha"}, on_event=sink_for("a"))
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            engine.run_pipeline(rerank_graph(), inputs={"query": "beta"}, on_event=sink_for("b"))
        )
        return list(await asyncio.gather(first, second))

    run_a, run_b = asyncio.run(both())

    assert sorted(reranker.queries) == ["alpha", "beta"]
    assert run_a.status is RunStatus.SUCCEEDED and run_b.status is RunStatus.SUCCEEDED
    assert _node(run_a, "rerank").fallback == "inference failed: alpha only"
    assert selects["a"]["rerank_reason"] == "inference failed: alpha only"
    assert _node(run_b, "rerank").status is NodeStatus.SUCCEEDED
    assert _node(run_b, "rerank").fallback is None
    # Run B reports its own rerank decision, never run A's failure.
    assert selects["b"]["rerank_reason"] == "profile-resolved reranker enabled"
    engine.close()
