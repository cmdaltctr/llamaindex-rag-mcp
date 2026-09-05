"""Red-first coverage for sparse-index freshness across store handles.

Stage 1 of the OpenSpec change
``fix-retrieval-freshness-and-context-assembly-2`` (task 1.1).

These tests pin the behaviour stages 2 and 3 must deliver, so they are
EXPECTED TO FAIL until that work lands:

- a long-lived reader handle must observe writes made through another
  handle (or another process) over the same Lance database, both in its
  BM25 sparse ranking and in the sparse leg of a hybrid query;
- the store must expose a durable data-version token
  (``get_data_version``) that changes for an ordinary mutation, an
  overwrite rebuild, and a delete/recreate that lands on the same
  numeric table version.

Until stage 2 adds the seam, the token assertions fail cleanly on the
missing method — never on an import error — and the behavioural
assertions fail on stale sparse results, which is the defect under fix.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import lancedb
import pytest

from omrg.core.retrieval.sparse import BM25SparseRetriever
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb import LanceVectorStore

_PRECOMPUTED_IDENTITY = EmbeddingIdentity(provider="test", model="mock")
_EMBEDDING_DIM = 384


def _mock_embedding() -> list[float]:
    """Return one deterministic unit vector matching the test embed model."""
    from llama_index.core import Settings

    return list(Settings.embed_model.get_query_embedding("freshness"))


def _upsert(
    store: LanceVectorStore,
    collection: str,
    rows: list[tuple[str, str, str]],
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Upsert simple rows through the public precomputed-embedding path.

    Args:
        store: Store handle that performs the write.
        collection: Target collection (Lance table).
        rows: ``(id, text, file_path)`` triples.
        extra_metadata: Additional metadata keys applied to every row; a
            key absent from the table schema triggers the store's
            overwrite-based struct evolution, which is the rebuild path
            under test.
    """
    metadatas: list[dict[str, Any]] = []
    for _row_id, _text, file_path in rows:
        metadata: dict[str, Any] = {"file_path": file_path}
        if extra_metadata:
            metadata.update(extra_metadata)
        metadatas.append(metadata)
    store.upsert_precomputed(
        collection,
        ids=[row[0] for row in rows],
        documents=[row[1] for row in rows],
        metadatas=metadatas,
        embeddings=[_mock_embedding() for _ in rows],
        embedding_identity=_PRECOMPUTED_IDENTITY,
    )


def _probe_durable_data_version(store: LanceVectorStore, collection: str) -> str | None:
    """Soft-probe the durable data-version seam without asserting it exists.

    Returns ``None`` until stage 2 (task 2.1) adds ``get_data_version``.
    Behavioural assertions run before the seam assertion so today's
    failure names the observable defect (stale sparse results), and the
    seam assertion keeps guarding once behaviour is fixed.
    """
    getter = getattr(store, "get_data_version", None)
    return getter(collection) if callable(getter) else None


def _require_durable_data_version(store: LanceVectorStore, collection: str) -> str | None:
    """Return the store's durable data-version token for one collection.

    Stage 2 (task 2.1) adds ``get_data_version`` to the ``VectorStore``
    ABC. Asserting the seam here keeps a pre-stage-2 failure a clean test
    failure rather than an ``AttributeError`` deep inside production
    code.
    """
    getter = getattr(store, "get_data_version", None)
    assert callable(getter), (
        "VectorStore.get_data_version is missing: stage 2 (task 2.1) must add "
        "the durable data-version seam these freshness tests pin."
    )
    return getter(collection)


def _numeric_table_version(uri: str, collection: str) -> int:
    """Return the raw Lance table version, bypassing the store adapter."""
    return lancedb.connect(uri).open_table(collection).version


def _recreate_reaching_numeric_version(
    writer: LanceVectorStore,
    uri: str,
    collection: str,
    seed_rows: list[tuple[str, str, str]],
    target_version: int,
) -> None:
    """Drop and recreate the table until its numeric version equals the target.

    Lance restarts a recreated table's version history, so ordinary
    commits after the recreation walk the numeric version back to a value
    a long-lived reader may already have cached. This reproduces the
    version-collision case the durable token must survive. The recreated
    incarnation carries different content from the cached one so a stale
    cache cannot satisfy the behavioural assertion vacuously.
    """
    writer.delete_collection(collection)
    _upsert(writer, collection, seed_rows)
    for cycle in range(target_version + 5):
        current = _numeric_table_version(uri, collection)
        if current == target_version:
            return
        _upsert(
            writer,
            collection,
            [
                (
                    f"recreate-cycle-{cycle}",
                    f"recreation filler cycle {cycle} content padding",
                    f"recreate_cycle_{cycle}.txt",
                )
            ],
        )
    raise AssertionError(
        f"Recreated table never reached numeric version {target_version}; "
        f"last observed {_numeric_table_version(uri, collection)}."
    )


def _assert_sparse_reflects(
    retriever: BM25SparseRetriever,
    query_term: str,
    expected_doc_id: str,
    context: str,
) -> None:
    """Assert the cached sparse index surfaces one freshly written row."""
    refreshed = retriever.query(query_term, top_n=5)
    assert [row[1] for row in refreshed] == [expected_doc_id], (
        f"{context}: the long-lived reader's next sparse query must reflect "
        f"the write without a restart; got {[row[1] for row in refreshed]}."
    )


def _assert_hybrid_sparse_leg_reflects(
    reader: LanceVectorStore,
    collection: str,
    query: str,
    expected_source: str,
    context: str,
) -> None:
    """Assert a hybrid query fuses the freshly written row through sparse.

    The dense leg of a hybrid query already sees committed rows today, so
    the honest observable for the sparse defect is the fused row carrying
    a sparse rank: only a rebuilt BM25 index can supply it.
    """
    from omrg.core.retrieval import search

    rows = search(
        query,
        top_k=5,
        rerank=False,
        hybrid=True,
        collection_name=collection,
        store=reader,
        include_diagnostics=True,
    )
    matching = [row for row in rows if row.get("source") == expected_source]
    assert matching, f"{context}: hybrid query must return the new row at all."
    assert matching[0].get("sparse_rank") is not None, (
        f"{context}: the new row {expected_source!r} must enter the hybrid "
        "fusion through the sparse leg, which requires the BM25 cache to be "
        "invalidated by the other handle's write."
    )


# ── Unit tests: two store handles in one process ───────────────────────


def test_ordinary_mutation_from_another_handle_is_visible_to_long_lived_reader(
    tmp_path: Path,
) -> None:
    """A write through handle A must refresh handle B's sparse index."""
    uri = str(tmp_path / "freshness_lance")
    writer = LanceVectorStore(uri=uri)
    reader = LanceVectorStore(uri=uri)
    collection = "documents"

    _upsert(
        writer,
        collection,
        [
            ("seed", "seed content zebra unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ],
    )

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("zebra", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)

    _upsert(
        writer,
        collection,
        [("added", "fresh content quokka unique beta filler", "added.txt")],
    )

    _assert_sparse_reflects(retriever, "quokka", "added", "ordinary mutation")
    _assert_hybrid_sparse_leg_reflects(
        reader, collection, "quokka", "added.txt", "ordinary mutation"
    )
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        "An ordinary mutation by another handle must change the durable "
        "data-version token observed by a long-lived reader."
    )


def test_overwrite_rebuild_from_another_handle_is_visible_to_long_lived_reader(
    tmp_path: Path,
) -> None:
    """An overwrite-based rebuild must refresh handle B's sparse index."""
    uri = str(tmp_path / "freshness_lance")
    writer = LanceVectorStore(uri=uri)
    reader = LanceVectorStore(uri=uri)
    collection = "documents"

    _upsert(
        writer,
        collection,
        [
            ("seed", "seed content wombat unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ],
    )

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("wombat", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)
    version_before = _numeric_table_version(uri, collection)

    # A metadata key absent from the table schema forces the store's
    # overwrite-based struct evolution: the table is rebuilt in place and
    # the new row is merged afterwards.
    _upsert(
        writer,
        collection,
        [("rebuilt", "rebuilt content narwhal unique psi filler", "rebuilt.txt")],
        extra_metadata={"rebuild_marker": "stage-1"},
    )

    assert _numeric_table_version(uri, collection) > version_before
    _assert_sparse_reflects(retriever, "narwhal", "rebuilt", "overwrite rebuild")
    _assert_hybrid_sparse_leg_reflects(
        reader, collection, "narwhal", "rebuilt.txt", "overwrite rebuild"
    )
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        "An overwrite-based rebuild must change the durable data-version "
        "token observed by a long-lived reader."
    )


def test_recreation_reaching_the_same_numeric_version_changes_the_token(
    tmp_path: Path,
) -> None:
    """A delete/recreate colliding on numeric version must still change the token.

    Numeric ``table.version`` alone cannot serve as cache identity: a
    recreated table restarts its history and can reach a version a
    reader has already cached. The durable token must differ anyway.
    """
    uri = str(tmp_path / "freshness_lance")
    writer = LanceVectorStore(uri=uri)
    reader = LanceVectorStore(uri=uri)
    collection = "documents"
    seed_rows = [
        ("seed", "seed content platypus unique alpha filler", "seed.txt"),
        ("fill1", "filler one gamma delta content", "fill1.txt"),
        ("fill2", "filler two gamma epsilon content", "fill2.txt"),
    ]

    _upsert(writer, collection, seed_rows)
    target_version = _numeric_table_version(uri, collection)

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("platypus", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)

    # The recreated incarnation reuses the seed row id but carries new
    # text, so only a rebuilt sparse index can surface the new token.
    recreated_rows = [
        ("seed", "recreated content okapi unique alpha filler", "seed.txt"),
        ("fill1", "filler one gamma delta content", "fill1.txt"),
        ("fill2", "filler two gamma epsilon content", "fill2.txt"),
    ]
    _recreate_reaching_numeric_version(writer, uri, collection, recreated_rows, target_version)

    assert _numeric_table_version(uri, collection) == target_version
    _assert_sparse_reflects(retriever, "okapi", "seed", "delete/recreate")
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        f"A delete/recreate landing on the same numeric table version "
        f"({target_version}) must still change the durable token."
    )


def test_durable_token_is_stable_without_mutation(tmp_path: Path) -> None:
    """Two reads with no intervening mutation must return the same token."""
    uri = str(tmp_path / "freshness_lance")
    writer = LanceVectorStore(uri=uri)
    collection = "documents"
    _upsert(
        writer,
        collection,
        [
            ("seed", "seed content zebra unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ],
    )
    reader = LanceVectorStore(uri=uri)

    assert _require_durable_data_version(reader, collection) == _require_durable_data_version(
        reader, collection
    )


def test_durable_token_for_absent_collection_reports_absence(tmp_path: Path) -> None:
    """Requesting the token of a missing collection must not raise."""
    reader = LanceVectorStore(uri=str(tmp_path / "freshness_lance"))

    assert _require_durable_data_version(reader, "never_created") is None


# ── Subprocess tests: writer in another process ────────────────────────


_WRITER_SCRIPT = textwrap.dedent(
    """
    import sys
    from omrg.core.vectordb.identity import EmbeddingIdentity
    from omrg.core.vectordb.lancedb import LanceVectorStore

    uri, collection, phase = sys.argv[1], sys.argv[2], sys.argv[3]
    vector = [1.0] + [0.0] * 383
    identity = EmbeddingIdentity(provider="test", model="mock")

    def upsert(rows, extra_meta=None):
        metadatas = []
        for _id, _text, path in rows:
            meta = {"file_path": path}
            if extra_meta:
                meta.update(extra_meta)
            metadatas.append(meta)
        store = LanceVectorStore(uri=uri)
        store.upsert_precomputed(
            collection,
            ids=[r[0] for r in rows],
            documents=[r[1] for r in rows],
            metadatas=metadatas,
            embeddings=[vector for _ in rows],
            embedding_identity=identity,
        )

    if phase == "seed":
        upsert([
            ("seed", "seed content capybara unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ])
    elif phase == "upsert":
        upsert([("subproc-added", "fresh content quokka unique beta filler", "subproc_added.txt")])
    elif phase == "overwrite":
        upsert(
            [
                (
                    "subproc-rebuilt",
                    "rebuilt content narwhal unique psi filler",
                    "subproc_rebuilt.txt",
                )
            ],
            extra_meta={"subproc_rebuild_marker": "stage-1"},
        )
    elif phase == "recreate":
        target_version = int(sys.argv[4])
        # Different content from the seed phase: a stale reader cache must
        # not be able to satisfy the freshness assertion vacuously.
        seed_rows = [
            ("seed", "recreated content okapi unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ]
        store = LanceVectorStore(uri=uri)
        store.delete_collection(collection)
        upsert(seed_rows)
        cycle = 0
        import lancedb as _lancedb
        while _lancedb.connect(uri).open_table(collection).version != target_version:
            upsert([(
                f"subproc-cycle-{cycle}",
                f"subprocess filler cycle {cycle} content padding",
                f"subproc_cycle_{cycle}.txt",
            )])
            cycle += 1
            if cycle > target_version + 5:
                raise SystemExit("recreation never reached the target version")
    else:
        raise SystemExit(f"unknown phase: {phase}")
    """
)


def _run_writer_subprocess(uri: str, collection: str, phase: str, *extra: str) -> None:
    """Run one writer phase in a separate process against the shared database."""
    completed = subprocess.run(
        [sys.executable, "-c", _WRITER_SCRIPT, uri, collection, phase, *extra],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"Writer subprocess phase {phase!r} failed:\n{completed.stderr}"
    )


@pytest.fixture
def shared_database(tmp_path: Path) -> tuple[str, str]:
    """Seed one collection from a writer subprocess and return (uri, collection)."""
    uri = str(tmp_path / "freshness_lance")
    collection = "cross_process_documents"
    _run_writer_subprocess(uri, collection, "seed")
    return uri, collection


def test_reader_process_observes_subprocess_ordinary_mutation(
    shared_database: tuple[str, str],
) -> None:
    """A write from another process must refresh this process's sparse index."""
    uri, collection = shared_database
    reader = LanceVectorStore(uri=uri)

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("capybara", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)

    _run_writer_subprocess(uri, collection, "upsert")

    _assert_sparse_reflects(retriever, "quokka", "subproc-added", "subprocess ordinary mutation")
    _assert_hybrid_sparse_leg_reflects(
        reader, collection, "quokka", "subproc_added.txt", "subprocess ordinary mutation"
    )
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        "A mutation by another process must change the durable data-version "
        "token observed by this process without any inter-process signalling."
    )


def test_reader_process_observes_subprocess_overwrite_rebuild(
    shared_database: tuple[str, str],
) -> None:
    """An overwrite rebuild in another process must refresh this process."""
    uri, collection = shared_database
    reader = LanceVectorStore(uri=uri)

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("capybara", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)

    _run_writer_subprocess(uri, collection, "overwrite")

    _assert_sparse_reflects(retriever, "narwhal", "subproc-rebuilt", "subprocess overwrite rebuild")
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        "An overwrite-based rebuild by another process must change the "
        "durable token observed by this process."
    )


def test_reader_process_observes_subprocess_recreation_on_colliding_version(
    shared_database: tuple[str, str],
) -> None:
    """A subprocess delete/recreate colliding on version must refresh this process."""
    uri, collection = shared_database
    reader = LanceVectorStore(uri=uri)

    retriever = BM25SparseRetriever(collection, store=reader)
    assert [row[1] for row in retriever.query("capybara", top_n=5)] == ["seed"]
    token_probe_before = _probe_durable_data_version(reader, collection)
    target_version = _numeric_table_version(uri, collection)

    _run_writer_subprocess(uri, collection, "recreate", str(target_version))

    assert _numeric_table_version(uri, collection) == target_version
    _assert_sparse_reflects(retriever, "okapi", "seed", "subprocess delete/recreate")
    token_after = _require_durable_data_version(reader, collection)
    assert token_after != token_probe_before, (
        f"A subprocess delete/recreate landing on the same numeric table "
        f"version ({target_version}) must still change the durable token."
    )
