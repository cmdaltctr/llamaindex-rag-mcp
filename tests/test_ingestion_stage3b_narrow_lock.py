"""Stage 3B narrow-lock regressions for the ingestion replacement path.

The Stage 3B hoist runs lineage/attempt stamping and
``_embed_missing_nodes`` above the process-global ``write_lock`` inside
``replace_source_nodes_async``, while write, durability verification, and
stale cleanup stay inside the lock.

Tests 1 and 2 pin the hoisted behaviour: embedding must proceed while the
lock is held elsewhere. Test 3 pins the vector-identity invariant the
order depends on, and passes under either order. Test 4 pins the boundary
that must not regress — store mutation waits for the lock — which current
code already satisfies.

Concurrency style mirrors ``tests/test_ingestion_parallel.py``: plain
``threading.Thread`` workers and ``asyncio.run`` from sync tests.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from llama_index.core.schema import MetadataMode, TextNode

from rag_mcp.core.ingestion import replacement
from rag_mcp.core.ingestion._state import shutdown_requested, write_lock
from rag_mcp.core.ingestion.replacement import replace_source_nodes_async
from rag_mcp.core.ingestion.source_state import (
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_COUNT_KEY,
    SOURCE_CONTENT_HASH_KEY,
    SOURCE_INDEX_IDENTITY_KEY,
    SOURCE_VERSION_KEY,
    new_source_attempt,
    stamp_source_lineage,
)
from rag_mcp.core.vectordb import get_default_store
from rag_mcp.core.vectordb.base import VectorStore

_COLLECTION = "stage3b_narrow_lock"

# Generous ceilings: a wrong implementation must fail an assertion,
# never hang the suite on an Event.wait or a thread join.
_EMBED_SIGNAL_TIMEOUT = 5.0
_STUB_BLOCK_TIMEOUT = 15.0
_THREAD_JOIN_TIMEOUT = 20.0
_QUIET_WINDOW_SECONDS = 0.2
_EMBED_HOLD_SECONDS = 0.05

# Digit-free node texts let test 3 assert the chunk-count value never
# appears in embedding text without accidental digit matches.
_TEXT_WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")


def _make_nodes(count: int, prefix: str) -> list[TextNode]:
    """Build small distinct nodes standing in for one parsed source file."""
    return [
        TextNode(text=f"{prefix} {word} content", id_=f"{prefix}-node-{index}")
        for index, word in enumerate(_TEXT_WORDS[:count])
    ]


def _assign_stub_embeddings(nodes: list[Any]) -> None:
    """Mirror the tail of the real ``_embed_missing_nodes``: fill vectors."""
    for node in nodes:
        node.embedding = [0.1, 0.2]


def _spawn_replacement(
    nodes: list[TextNode],
    *,
    file_path: str,
    suffix: str,
    store: Any = None,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Run one replacement in a worker thread, boxing outcome or error.

    ``asyncio.run`` inside a plain thread matches how sync tests in
    ``test_ingestion_parallel.py`` drive coroutines.
    """
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["outcome"] = asyncio.run(
                replace_source_nodes_async(
                    nodes,
                    file_path=file_path,
                    source_id=f"src_{suffix}",
                    content_hash=f"content-hash-{suffix}",
                    index_identity=f"index-identity-{suffix}",
                    source_version=f"source-version-{suffix}",
                    collection_name=_COLLECTION,
                    store=store,
                )
            )
        except BaseException as exc:
            box["error"] = exc

    return threading.Thread(target=worker, daemon=True), box


@pytest.fixture(autouse=True)
def _clean_ingestion_state():
    """Isolate process-wide ingestion state around each test.

    Fail fast when an earlier test leaked a held lock (prevents a hang
    here), and force-release the lock when this test fails mid-hold so
    the rest of the suite is not blocked behind the failed worker.
    """
    shutdown_requested.clear()
    assert not write_lock.locked(), "write_lock arrived held from an earlier test"
    yield
    shutdown_requested.clear()
    if write_lock.locked():
        write_lock.release()


def test_embedding_proceeds_while_lock_is_held_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding must start while another thread holds the write lock.

    Pins the Stage 3B hoist: ``_embed_missing_nodes`` runs before the
    replacement acquires ``write_lock``. Current code acquires the lock
    first, so the worker blocks before embedding, ``embed_started`` never
    fires within the wait window, and this test fails.
    """
    nodes = _make_nodes(3, "locked-source")
    embed_started = threading.Event()
    allow_proceed = threading.Event()

    def blocking_embed(replacement_nodes: list[Any]) -> None:
        embed_started.set()
        allow_proceed.wait(timeout=_STUB_BLOCK_TIMEOUT)
        _assign_stub_embeddings(replacement_nodes)

    monkeypatch.setattr(replacement, "_embed_missing_nodes", blocking_embed)

    thread, box = _spawn_replacement(
        nodes,
        file_path="/virtual/locked-source.txt",
        suffix="locked",
    )
    write_lock.acquire()
    thread.start()
    try:
        started_while_locked = embed_started.wait(timeout=_EMBED_SIGNAL_TIMEOUT)
        assert started_while_locked, (
            "embedding never started while the test held write_lock; "
            "embedding still runs inside the global write lock"
        )
    finally:
        allow_proceed.set()
        if write_lock.locked():
            write_lock.release()
        thread.join(timeout=_THREAD_JOIN_TIMEOUT)

    assert "error" not in box, f"replacement raised: {box.get('error')!r}"
    assert not thread.is_alive()
    assert box["outcome"].chunks_written == len(nodes)


def test_concurrent_replacements_overlap_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two same-collection replacements must overlap during embedding.

    With embedding outside the global write lock, two concurrent
    replacements for different files run their embed phases simultaneously
    (bounded by the embed semaphore, width 2 here). Current code holds the
    lock across embedding, so the phases serialise and the observed peak
    stays at 1 — this test fails today.
    """
    state_lock = threading.Lock()
    embed_state = {"current": 0, "peak": 0}

    def counting_embed(replacement_nodes: list[Any]) -> None:
        with state_lock:
            embed_state["current"] += 1
            embed_state["peak"] = max(embed_state["peak"], embed_state["current"])
        time.sleep(_EMBED_HOLD_SECONDS)
        with state_lock:
            embed_state["current"] -= 1
        _assign_stub_embeddings(replacement_nodes)

    monkeypatch.setattr(replacement, "_embed_missing_nodes", counting_embed)

    nodes_a = _make_nodes(2, "overlap-a")
    nodes_b = _make_nodes(2, "overlap-b")

    async def run_both() -> tuple[Any, Any]:
        return await asyncio.gather(
            replace_source_nodes_async(
                nodes_a,
                file_path="/virtual/overlap-a.txt",
                source_id="src_overlap_a",
                content_hash="content-hash-overlap-a",
                index_identity="index-identity-overlap-a",
                source_version="source-version-overlap-a",
                collection_name=_COLLECTION,
            ),
            replace_source_nodes_async(
                nodes_b,
                file_path="/virtual/overlap-b.txt",
                source_id="src_overlap_b",
                content_hash="content-hash-overlap-b",
                index_identity="index-identity-overlap-b",
                source_version="source-version-overlap-b",
                collection_name=_COLLECTION,
            ),
        )

    outcomes = asyncio.run(run_both())

    store = get_default_store()
    stored_paths = {
        metadata.get("file_path") for _, _, metadata in store.iter_documents(_COLLECTION)
    }

    assert outcomes[0].chunks_written == len(nodes_a)
    assert outcomes[1].chunks_written == len(nodes_b)
    assert "/virtual/overlap-a.txt" in stored_paths
    assert "/virtual/overlap-b.txt" in stored_paths
    assert store.count(_COLLECTION) == len(nodes_a) + len(nodes_b)
    assert embed_state["peak"] == 2, (
        f"peak concurrent embeddings was {embed_state['peak']}, expected 2; "
        "the global write lock still serialises the embed phase"
    )


def test_source_metadata_keys_never_enter_embed_text() -> None:
    """Stamped source metadata stays out of embedding text under both orders.

    The Stage 3B reorder swaps the embed/stamp order, so this guard
    exercises the seam directly: stamp first (the new order), then render
    ``MetadataMode.EMBED`` content exactly as ``_embed_missing_nodes``
    would. Every source key must be excluded, which keeps the embed text
    identical under either order. Passes before and after the change.
    """
    nodes = _make_nodes(3, "stamp-guard")
    file_path = "/virtual/stamp-guard.txt"
    source_id = "src_stamp_guard"
    content_hash = "aa11" * 8
    index_identity = "bb22" * 8
    source_version = "cc33" * 8
    source_attempt = new_source_attempt()

    stamp_source_lineage(
        nodes,
        file_path=file_path,
        source_id=source_id,
        content_hash=content_hash,
        index_identity=index_identity,
        source_version=source_version,
        source_attempt=source_attempt,
    )

    stamped: dict[str, str] = {
        SOURCE_CONTENT_HASH_KEY: content_hash,
        SOURCE_INDEX_IDENTITY_KEY: index_identity,
        SOURCE_VERSION_KEY: source_version,
        SOURCE_ATTEMPT_KEY: source_attempt,
    }
    for node in nodes:
        embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
        for key, value in stamped.items():
            assert value not in embed_text, f"{key} value leaked into embed text"
            assert key not in embed_text
        assert SOURCE_CHUNK_COUNT_KEY not in embed_text
        assert str(len(nodes)) not in embed_text
        for key in (*stamped, SOURCE_CHUNK_COUNT_KEY):
            assert key in node.excluded_embed_metadata_keys
        assert node.id_

    stamped_ids = {node.id_ for node in nodes}
    assert len(stamped_ids) == len(nodes)


class _WriteRecordingStore:
    """Delegating wrapper signalling when the store first sees write_nodes."""

    def __init__(self, inner: VectorStore) -> None:
        self._inner = inner
        self.write_attempted = threading.Event()

    def write_nodes(self, nodes: list[Any], collection_name: str) -> None:
        self.write_attempted.set()
        self._inner.write_nodes(nodes, collection_name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_write_verify_cleanup_still_inside_lock_after_hoist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Store mutation must wait for the write lock even after the hoist.

    The safety counterpart to the overlap tests: embedding may run
    unlocked, but ``write_nodes`` must not reach the store while another
    thread holds ``write_lock``. Current code already keeps the write
    inside the lock, so this passes today and must keep passing after
    the hoist.
    """
    store = _WriteRecordingStore(get_default_store())

    def instant_embed(replacement_nodes: list[Any]) -> None:
        _assign_stub_embeddings(replacement_nodes)

    monkeypatch.setattr(replacement, "_embed_missing_nodes", instant_embed)

    nodes = _make_nodes(3, "write-guard")
    thread, box = _spawn_replacement(
        nodes,
        file_path="/virtual/write-guard.txt",
        suffix="write-guard",
        store=store,
    )
    write_lock.acquire()
    thread.start()
    try:
        time.sleep(_QUIET_WINDOW_SECONDS)
        assert not store.write_attempted.is_set(), (
            "store.write_nodes ran while the test held write_lock; "
            "the store mutation escaped the global write lock"
        )
    finally:
        write_lock.release()
        thread.join(timeout=_THREAD_JOIN_TIMEOUT)

    assert "error" not in box, f"replacement raised: {box.get('error')!r}"
    assert not thread.is_alive()
    assert store.write_attempted.is_set()
    assert box["outcome"].chunks_written == len(nodes)
