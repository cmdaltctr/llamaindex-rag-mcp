"""Embedding preparation and protected commit seams (task 3.4, extraction).

``replace_source_nodes_async`` now composes two callable seams:
``prepare_source_embeddings`` (lineage stamping, embedding and the norm
guard, outside the write lock) and ``commit_prepared_source`` (write,
durability verification and stale cleanup as one locked operation). These
tests pin malformed-vector rejection, lineage validation before mutation,
interrupted attempts that keep the previous version, and lock retention.
The store is the per-test embedded LanceDB from ``tests/conftest.py``.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from llama_index.core.schema import TextNode

from omrg.core.ingestion import replacement
from omrg.core.ingestion._state import shutdown_requested, write_lock
from omrg.core.ingestion.replacement import IngestionStageError
from omrg.core.ingestion.source_state import (
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_INDEX_KEY,
    SOURCE_ID_KEY,
    new_source_attempt,
)
from omrg.core.vectordb import get_default_store

_COLLECTION = "seam_replacement"
_SOURCE_ID = "src_seam"
_FILE_PATH = "/virtual/seam.txt"
_THREAD_TIMEOUT = 10.0


@pytest.fixture(autouse=True)
def _clean_state():
    """Isolate the shutdown flag and fail fast on a leaked write lock."""
    shutdown_requested.clear()
    assert not write_lock.locked(), "write_lock arrived held from an earlier test"
    yield
    shutdown_requested.clear()
    if write_lock.locked():
        write_lock.release()


def _nodes(prefix: str, count: int = 2) -> list[TextNode]:
    """Return unembedded candidate nodes for one source."""
    return [TextNode(text=f"{prefix} chunk {index}") for index in range(count)]


def _prepare(nodes: list[TextNode], version: str, **kwargs: Any) -> Any:
    """Prepare *nodes* as one attempt of the shared virtual source."""
    return replacement.prepare_source_embeddings(
        nodes,
        file_path=_FILE_PATH,
        source_id=_SOURCE_ID,
        content_hash=f"hash-{version}",
        index_identity="identity",
        source_version=f"version-{version}",
        source_attempt=new_source_attempt(),
        **kwargs,
    )


def _commit(nodes: list[TextNode], prepared: Any, store: Any) -> Any:
    """Commit prepared *nodes* for the shared virtual source."""
    return replacement.commit_prepared_source(
        nodes, prepared, collection_name=_COLLECTION, store=store
    )


def _stored_texts(store: Any) -> list[str]:
    """Return the stored texts of the shared virtual source."""
    return sorted(
        text
        for _row, text, _meta in store.iter_filtered_documents(
            _COLLECTION, {SOURCE_ID_KEY: _SOURCE_ID}
        )
    )


def _durable(store: Any) -> list[str]:
    """Write and return one durable previous version."""
    nodes = _nodes("old")
    _commit(nodes, _prepare(nodes, "old"), store)
    return _stored_texts(store)


class _VectorModel:
    """Embedding model double returning caller-chosen vectors."""

    model_name = "seam-vector-model"

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors

    def get_text_embedding_batch(self, texts: list[str], show_progress: bool = False) -> list:
        return [list(vector) for vector in self._vectors]


# ── Preparation ──────────────────────────────────────────────────────────


def test_prepare_stamps_lineage_and_embeds_without_the_write_lock() -> None:
    """Preparation completes while another holder keeps the write lock."""
    nodes = _nodes("prep", 3)
    box: dict[str, Any] = {}

    def _worker() -> None:
        box["prepared"] = _prepare(nodes, "prep")

    with write_lock:
        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()
        worker.join(timeout=_THREAD_TIMEOUT)
        assert not worker.is_alive(), "preparation waited for the write lock"

    prepared = box["prepared"]
    assert (prepared.source_id, prepared.file_path) == (_SOURCE_ID, _FILE_PATH)
    assert prepared.chunk_count == 3
    assert prepared.norm_band is not None
    assert all(node.embedding for node in nodes)
    assert [node.metadata[SOURCE_CHUNK_INDEX_KEY] for node in nodes] == [0, 1, 2]
    assert {node.metadata[SOURCE_ATTEMPT_KEY] for node in nodes} == {prepared.source_attempt}


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0, 0.0]],  # fewer vectors than nodes
        [[1.0, 0.0], [float("nan"), 0.0]],  # non-finite element
        [[1.0, 0.0], [3.0, 4.0]],  # violates the unit-norm guard
    ],
)
def test_prepare_rejects_malformed_vectors_as_embedding_stage(vectors: list) -> None:
    """Malformed embeddings fail inside the attributed embedding stage."""
    with pytest.raises(IngestionStageError) as caught:
        _prepare(_nodes("bad"), "bad", embed_model=_VectorModel(vectors))

    assert caught.value.stage == "embedding"


def test_commit_rejects_wrong_dimension_and_keeps_previous_version() -> None:
    """The store write contract rejects a dimension change before mutation."""
    store = get_default_store()
    durable = _durable(store)
    nodes = _nodes("wide")
    prepared = _prepare(nodes, "wide", embed_model=_VectorModel([[1.0, 0.0], [0.0, 1.0]]))

    with pytest.raises(IngestionStageError) as caught:
        _commit(nodes, prepared, store)

    assert caught.value.stage == "store_write"
    assert _stored_texts(store) == durable
    assert not write_lock.locked()


# ── Lineage validation ───────────────────────────────────────────────────


def _unstamped(nodes: list[TextNode], prepared: Any) -> None:
    for node in nodes:
        node.metadata.pop(SOURCE_ATTEMPT_KEY)


def _other_attempt(nodes: list[TextNode], prepared: Any) -> None:
    nodes[0].metadata[SOURCE_ATTEMPT_KEY] = "another-attempt"


def _reordered(nodes: list[TextNode], prepared: Any) -> None:
    nodes.reverse()


def _truncated(nodes: list[TextNode], prepared: Any) -> None:
    nodes.pop()


def _other_source(nodes: list[TextNode], prepared: Any) -> None:
    nodes[1].metadata[SOURCE_ID_KEY] = "src_other"


@pytest.mark.parametrize(
    "corrupt", [_unstamped, _other_attempt, _reordered, _truncated, _other_source]
)
def test_commit_rejects_invalid_lineage_before_any_mutation(
    monkeypatch: pytest.MonkeyPatch, corrupt: Any
) -> None:
    """Nodes that do not match the prepared attempt never reach the store."""
    store = get_default_store()
    durable = _durable(store)
    nodes = _nodes("new", 3)
    prepared = _prepare(nodes, "new")
    corrupt(nodes, prepared)
    writes: list[int] = []
    monkeypatch.setattr(store, "write_nodes", lambda *a, **k: writes.append(1))

    with pytest.raises(IngestionStageError) as caught:
        _commit(nodes, prepared, store)

    assert caught.value.stage == "lineage"
    assert writes == []
    assert _stored_texts(store) == durable
    assert not write_lock.locked()


# ── Interrupted attempts ─────────────────────────────────────────────────


def test_shutdown_after_preparation_writes_nothing() -> None:
    """A shutdown between preparation and commit keeps the previous version."""
    store = get_default_store()
    durable = _durable(store)
    nodes = _nodes("late")
    prepared = _prepare(nodes, "late")
    shutdown_requested.set()

    outcome = _commit(nodes, prepared, store)

    assert (outcome.chunks_written, outcome.chunks_removed) == (0, 0)
    assert outcome.source_attempt == prepared.source_attempt
    assert outcome.timings.embedding_seconds == prepared.embedding_seconds
    assert _stored_texts(store) == durable


def test_failed_verification_keeps_previous_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write that cannot be verified never deletes the durable rows."""
    store = get_default_store()
    durable = _durable(store)
    nodes = _nodes("unverified")
    prepared = _prepare(nodes, "unverified")
    real_count_where = store.count_where
    monkeypatch.setattr(store, "count_where", lambda *a, **k: 0)

    with pytest.raises(IngestionStageError) as caught:
        _commit(nodes, prepared, store)

    assert caught.value.stage == "store_verify"
    stored = _stored_texts(store)
    assert all(text in stored for text in durable)
    assert not write_lock.locked()

    # The next verified attempt removes both the durable and the partial rows.
    monkeypatch.setattr(store, "count_where", real_count_where)
    retry = _nodes("retry")
    outcome = _commit(retry, _prepare(retry, "retry"), store)
    assert outcome.chunks_removed == len(stored)
    assert _stored_texts(store) == sorted(node.text for node in retry)


# ── Lock retention ───────────────────────────────────────────────────────


def test_commit_holds_the_write_lock_for_write_verify_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write, verification and stale cleanup run as one locked operation."""
    store = get_default_store()
    _durable(store)
    nodes = _nodes("locked")
    prepared = _prepare(nodes, "locked")
    observed: dict[str, list[bool]] = {"write": [], "verify": [], "cleanup": []}

    def _observe(name: str, target: Any) -> Any:
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            observed[name].append(write_lock.locked())
            return target(*args, **kwargs)

        return _wrapper

    monkeypatch.setattr(store, "write_nodes", _observe("write", store.write_nodes))
    monkeypatch.setattr(store, "count_where", _observe("verify", store.count_where))
    monkeypatch.setattr(store, "delete_ids", _observe("cleanup", store.delete_ids))

    outcome = _commit(nodes, prepared, store)

    assert outcome.chunks_written == 2
    assert outcome.chunks_removed == 2
    assert observed == {"write": [True], "verify": [True], "cleanup": [True]}
    assert not write_lock.locked()
    assert _stored_texts(store) == sorted(node.text for node in nodes)


@pytest.mark.asyncio
async def test_replace_source_nodes_composes_prepare_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standard replacement path calls the same two seams in order."""
    calls: list[str] = []
    real_prepare = replacement.prepare_source_embeddings
    real_commit = replacement.commit_prepared_source

    def _prepare_spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("prepare")
        return real_prepare(*args, **kwargs)

    def _commit_spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("commit")
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(replacement, "prepare_source_embeddings", _prepare_spy)
    monkeypatch.setattr(replacement, "commit_prepared_source", _commit_spy)

    outcome = await replacement.replace_source_nodes_async(
        _nodes("composed"),
        file_path=_FILE_PATH,
        source_id=_SOURCE_ID,
        content_hash="hash-composed",
        index_identity="identity",
        source_version="version-composed",
        collection_name=_COLLECTION,
        store=get_default_store(),
    )

    assert calls == ["prepare", "commit"]
    assert outcome.chunks_written == 2
    assert outcome.norm_band is not None
