"""Embed and protected-commit guarantees through graph adapters (task 3.4).

The embed and commit adapters reuse ``prepare_source_embeddings`` and
``commit_prepared_source``. These tests prove that a graph keeps every
existing guarantee: malformed vectors and invalid lineage fail before
mutation, legacy lineage is rejected before parsing, a failed attempt keeps
the previous version, cancellation stops a commit that has not started,
and a commit that has started finishes its write, verification and cleanup.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.schema import TextNode
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    invoke,
    offline_settings,
    resources,
)

from omrg.core.ingestion._state import write_lock
from omrg.core.ingestion.graph_adapters import SourceWork
from omrg.core.ingestion.replacement import IngestionStageError
from omrg.core.ingestion.source_state import SOURCE_ID_KEY, IncompatibleSourceLineageError
from omrg.core.ingestion.sources import SourceUnit
from omrg.core.pipelines import CancellationFlag, PipelineCancelledError

_COLLECTION = "graph_commit"
_CHAIN = (
    ("identify", "sources", "sources"),
    ("read", "sources", "documents"),
    ("normalise", "documents", "documents"),
    ("enrich", "documents", "documents"),
    ("chunk", "documents", "chunks"),
    ("embed", "chunks", "chunks"),
)


class _Harness:
    """One source file, one admitted canonical graph, explicit resources."""

    def __init__(self, tmp_path: Path, effective_settings: Any, store: Any) -> None:
        self.root = tmp_path
        self.source = tmp_path / "a.md"
        self.store = store
        self.catalogue = build_catalogue()
        self.snapshot = admit(
            canonical_graph(_COLLECTION),
            offline_settings(effective_settings),
            tmp_path,
            self.catalogue,
        )

    def resources(self, store: Any = None, **extra: Any) -> dict[str, Any]:
        return resources(self.snapshot, self.catalogue, store or self.store, **extra)

    async def embedded(self, text: str, **extra: Any) -> SourceWork:
        """Write *text* and run identify..embed for the one source."""
        self.source.write_text(text, encoding="utf-8")
        value: Any = (SourceUnit(0, self.source, "a.md", None),)
        run_resources = self.resources(**extra)
        for node_id, in_port, out_port in _CHAIN:
            output = await invoke(
                self.snapshot, self.catalogue, run_resources, node_id, {in_port: value}
            )
            value = output.values[out_port]
        return value

    async def commit(self, work: SourceWork, *, store: Any = None, token: Any = None) -> Any:
        return await invoke(
            self.snapshot,
            self.catalogue,
            self.resources(store),
            "commit",
            {"chunks": work},
            token=token,
        )

    def texts(self) -> list[str]:
        if not self.store.collection_exists(_COLLECTION):
            return []
        return sorted(text for _row, text, _meta in self.store.iter_documents(_COLLECTION))


@pytest.fixture
def harness(tmp_path: Path, effective_settings: Any) -> _Harness:
    from omrg.core.vectordb import get_default_store

    assert not write_lock.locked()
    yield _Harness(tmp_path, effective_settings, get_default_store())
    if write_lock.locked():
        write_lock.release()


_OLD = "# Old\n\nThe previous searchable version.\n"
_NEW = "# New\n\nThe replacement version.\n"


async def _durable_old(harness: _Harness) -> list[str]:
    await harness.commit(await harness.embedded(_OLD))
    return harness.texts()


# ── Malformed vectors and lineage ───────────────────────────────────────


class _NaNModel:
    model_name = "nan-model"

    def get_text_embedding_batch(self, texts: list[str], show_progress: bool = False) -> list:
        return [[float("nan")] * 384 for _ in texts]


@pytest.mark.asyncio
async def test_malformed_vector_fails_in_embed_and_keeps_previous_version(
    harness: _Harness,
) -> None:
    """A NaN vector stops in the embedding stage; nothing is written."""
    before = await _durable_old(harness)
    with pytest.raises(IngestionStageError) as caught:
        await harness.embedded(_NEW, embedder=_NaNModel())
    assert caught.value.stage == "embedding"
    assert harness.texts() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["drop_node", "foreign_attempt", "no_vector"])
async def test_invalid_lineage_fails_before_mutation(harness: _Harness, tamper: str) -> None:
    """The commit re-checks lineage before it takes the write lock."""
    before = await _durable_old(harness)
    work = await harness.embedded(_NEW)
    nodes = list(work.nodes or [])
    if tamper == "drop_node":
        nodes = nodes[:-1] or [TextNode(text="extra")]
    elif tamper == "foreign_attempt":
        nodes[0].metadata["source_attempt"] = "someone-else"
    else:
        nodes[0].embedding = None
    from dataclasses import replace

    with pytest.raises(IngestionStageError) as caught:
        await harness.commit(replace(work, nodes=nodes))
    assert caught.value.stage == "lineage"
    assert harness.texts() == before


@pytest.mark.asyncio
async def test_legacy_lineage_is_rejected_before_parsing(harness: _Harness) -> None:
    """Pre-lineage rows fail in the identify node; no repair is attempted."""
    from omrg.core.ingestion.source_state import canonical_source_path

    harness.source.write_text(_NEW, encoding="utf-8")
    legacy = TextNode(text="legacy", metadata={"file_path": canonical_source_path(harness.source)})
    harness.store.write_nodes([legacy], _COLLECTION)
    with pytest.raises(IncompatibleSourceLineageError):
        await harness.embedded(_NEW)
    assert harness.texts() == ["legacy"]


# ── Interrupted attempts ────────────────────────────────────────────────


class _FailVerify:
    """Store proxy whose durability count never matches."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def count_where(self, collection_name: str, where: dict) -> int:
        return 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


@pytest.mark.asyncio
async def test_failed_verification_keeps_previous_version_and_retry_cleans(
    harness: _Harness,
) -> None:
    """A failed attempt leaves old rows searchable; a retry replaces them."""
    before = await _durable_old(harness)
    work = await harness.embedded(_NEW)
    with pytest.raises(IngestionStageError) as caught:
        await harness.commit(work, store=_FailVerify(harness.store))
    assert caught.value.stage == "store_verify"
    assert set(before) <= set(harness.texts())

    retry = await harness.embedded(_NEW)
    output = await harness.commit(retry)
    assert output.values["summary"]["status"] == "indexed"
    assert harness.texts() == sorted(n.text for n in retry.nodes or [])


# ── Cancellation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_before_commit_starts_nothing(harness: _Harness) -> None:
    """A cancelled run does not start a protected commit."""
    before = await _durable_old(harness)
    work = await harness.embedded(_NEW)
    token = CancellationFlag()
    token.cancel()
    with pytest.raises(PipelineCancelledError):
        await harness.commit(work, token=token)
    assert harness.texts() == before


class _CancelDuringWrite:
    """Store proxy that requests cancellation while the write runs."""

    def __init__(self, store: Any, token: CancellationFlag) -> None:
        self._store = store
        self._token = token

    def write_nodes(self, *args: Any, **kwargs: Any) -> Any:
        self._token.cancel()
        return self._store.write_nodes(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


@pytest.mark.asyncio
async def test_cancellation_during_commit_lets_it_finish(harness: _Harness) -> None:
    """Write, verification and stale cleanup finish; the effect is reported."""
    await _durable_old(harness)
    work = await harness.embedded(_NEW)
    token = CancellationFlag()
    output = await harness.commit(work, store=_CancelDuringWrite(harness.store, token), token=token)
    assert token.cancelled
    summary = output.values["summary"]
    assert summary["status"] == "indexed"
    assert summary["chunks_removed"] > 0
    assert output.effects == (f"committed:{work.identity.source_id}",)
    assert harness.texts() == sorted(n.text for n in work.nodes or [])


class _BlockingWrite:
    """Store proxy whose write waits until the test releases it."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self.entered = threading.Event()
        self.release = threading.Event()

    def write_nodes(self, *args: Any, **kwargs: Any) -> Any:
        self.entered.set()
        assert self.release.wait(10.0)
        return self._store.write_nodes(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


@pytest.mark.asyncio
async def test_task_cancellation_waits_for_an_entered_commit(harness: _Harness) -> None:
    """Cancelling the awaiting task cannot leave a half-finished commit."""
    await _durable_old(harness)
    work = await harness.embedded(_NEW)
    blocking = _BlockingWrite(harness.store)
    task = asyncio.create_task(harness.commit(work, store=blocking))
    assert await asyncio.to_thread(blocking.entered.wait, 10.0)
    task.cancel()
    await asyncio.sleep(0.05)
    assert not task.done(), "the adapter returned while the commit was still running"
    blocking.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not write_lock.locked()
    assert harness.texts() == sorted(n.text for n in work.nodes or [])
    rows = list(
        harness.store.iter_filtered_documents(_COLLECTION, {SOURCE_ID_KEY: work.identity.source_id})
    )
    assert len(rows) == len(work.nodes or [])


@pytest.mark.asyncio
async def test_commit_refuses_a_reuse_check_for_another_collection(harness: _Harness) -> None:
    """The reuse check and the commit must name the same collection."""
    from dataclasses import replace

    work = await harness.embedded(_NEW)
    with pytest.raises(ValueError, match="collection"):
        await harness.commit(replace(work, collection="elsewhere"))
    assert harness.texts() == []
