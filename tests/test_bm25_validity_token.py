"""Stage-3 BM25 validity-token behaviour (tasks 3.1-3.4).

Pins the ``hybrid-retrieval`` spec scenarios that the stage-1 file does
not reach, on top of the durable-token seam stage 2 added:

- the durable token is preferred and stays silent when available;
- the process-local fallback is tagged, and warns **once per collection
  per process** naming the reduced guarantee;
- a capability transition (tagged fallback -> tagged durable) compares
  unequal even when the numeric members match, so the cache rebuilds;
- a mutation landing between a rebuild's pre-fetch and pre-publish
  token reads discards the unstable build and retries within a bounded
  policy — including mutations and recreations made by a **separate
  process** (the watch-daemon shape);
- a continuously mutating store exhausts the bounded retries, serves a
  best-effort build, and publishes nothing.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from rag_mcp.core.retrieval.sparse import (
    _LOCAL_TOKEN_PREFIX,
    _MAX_BUILD_ATTEMPTS,
    BM25SparseRetriever,
    reset_fallback_warning_state,
)
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_DURABLE_PREFIX = "lancedb-durable-v1"


class _ScriptedStore:
    """Minimal BM25 store double with scriptable validity modes.

    Emulates one collection whose durable data version is either fixed
    (``str``), absent (``None``) or advancing (callable).  Rows are
    served verbatim; ``read_calls`` counts full row scans so tests can
    pin rebuild counts.
    """

    def __init__(self, rows: list[tuple[str, str]], data_version: Any) -> None:
        self._rows = list(rows)
        self._data_version = data_version
        self._generations: dict[str, int] = {}
        self.read_calls = 0

    @property
    def cache_identity(self) -> object:
        return self

    def count(self, collection_name: str) -> int:
        return len(self._rows)

    def iter_documents(self, collection_name: str, page_size: int | None = None):
        self.read_calls += 1
        for doc_id, text in self._rows:
            yield (doc_id, text, {})

    def get_generation(self, collection_name: str) -> int:
        return self._generations.get(collection_name, 0)

    def bump_generation(self, collection_name: str) -> None:
        self._generations[collection_name] = self._generations.get(collection_name, 0) + 1

    def get_data_version(self, collection_name: str) -> str | None:
        if callable(self._data_version):
            return self._data_version()
        return self._data_version

    def set_data_version(self, data_version: Any) -> None:
        self._data_version = data_version


class _MutatingStore(_ScriptedStore):
    """Store double whose collection mutates mid-build, once.

    The mutation lands after the first row of the *first* row scan —
    between the rebuild's pre-fetch and pre-publish token reads — which
    is exactly the race the spec's "mutation during a BM25 build"
    scenario describes.  Later scans observe the post-mutation state
    without mutating again, so the bounded retry can succeed.
    """

    def __init__(self, rows: list[tuple[str, str]], added_row: tuple[str, str]) -> None:
        super().__init__(rows, data_version=f"{_DURABLE_PREFIX}:epoch-a:1")
        self._added_row = added_row
        self._mutated = False

    def iter_documents(self, collection_name: str, page_size: int | None = None):
        self.read_calls += 1
        rows = list(self._rows)
        for offset, (doc_id, text) in enumerate(rows):
            yield (doc_id, text, {})
            if offset == 0 and not self._mutated:
                self._mutated = True
                self._rows.append(self._added_row)
                self._data_version = f"{_DURABLE_PREFIX}:epoch-a:2"


@pytest.fixture(autouse=True)
def _isolate_bm25_cache_and_warnings() -> Any:
    """Keep the process-wide BM25 cache and warning state out of neighbours."""
    BM25SparseRetriever._cache.clear()
    reset_fallback_warning_state()
    yield
    BM25SparseRetriever._cache.clear()
    reset_fallback_warning_state()


# ── Token preference and the fallback guarantee ────────────────────────


def test_durable_token_is_preferred_and_stays_silent(caplog: pytest.LogCaptureFixture) -> None:
    """A store with a durable version supplies the cache token verbatim."""
    store = _ScriptedStore([("a", "alpha rareterm content")], f"{_DURABLE_PREFIX}:epoch-x:7")
    retriever = BM25SparseRetriever("documents", store=store)

    with caplog.at_level(logging.WARNING):
        retriever.query("rareterm", top_n=5)

    assert BM25SparseRetriever._cache[(store, "documents")].validity_token == (
        f"{_DURABLE_PREFIX}:epoch-x:7"
    )
    assert not caplog.records


def test_fallback_token_is_tagged_and_warns_once_per_collection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No durable version: tagged local token, one warning naming the limit."""
    store = _ScriptedStore([("a", "alpha rareterm content")], data_version=None)
    retriever = BM25SparseRetriever("documents", store=store)

    with caplog.at_level(logging.WARNING):
        retriever.query("rareterm", top_n=5)
        retriever.query("rareterm", top_n=5)
        retriever.query("rareterm", top_n=5)

    fallback_warnings = [
        record
        for record in caplog.records
        if record.name == "rag_mcp.core.retrieval.sparse"
        and "process-local generation counter" in record.message
    ]
    assert len(fallback_warnings) == 1
    # The warning names the reduced guarantee, not just the mechanism.
    assert "other processes" in fallback_warnings[0].message
    assert BM25SparseRetriever._cache[(store, "documents")].validity_token == (
        f"{_LOCAL_TOKEN_PREFIX}:0"
    )
    # A second collection on a store without the capability warns for
    # itself: "once" is per collection, not per process-wide first use.
    other = _ScriptedStore([("b", "beta content")], data_version=None)
    with caplog.at_level(logging.WARNING):
        BM25SparseRetriever("notes", store=other).query("beta", top_n=5)
    assert (
        len(
            [
                record
                for record in caplog.records
                if record.name == "rag_mcp.core.retrieval.sparse"
                and "process-local generation counter" in record.message
            ]
        )
        == 2
    )


def test_capability_transition_from_fallback_to_durable_invalidates() -> None:
    """Tagged tokens never compare equal, even with equal numeric members.

    A legacy table reads ``None`` (fallback token ``bm25-local-v1:3``);
    the next OMRG-controlled writer installs an epoch whose table
    version is also 3. The numeric members match, but the cache must
    rebuild because the tags differ (spec: capability transition).
    """
    store = _ScriptedStore(
        [
            ("a", "alpha rareterm content"),
            ("fill", "filler gamma delta content"),
        ],
        data_version=None,
    )
    store._generations["documents"] = 3
    retriever = BM25SparseRetriever("documents", store=store)

    retriever.query("rareterm", top_n=5)
    assert BM25SparseRetriever._cache[(store, "documents")].validity_token == (
        f"{_LOCAL_TOKEN_PREFIX}:3"
    )
    assert store.read_calls == 1

    # Numeric table version 3 collides with generation 3 on purpose.
    store.set_data_version(f"{_DURABLE_PREFIX}:epoch-new:3")
    store._rows.append(("b", "beta freshterm content"))

    results = retriever.query("freshterm", top_n=5)

    assert [row[1] for row in results] == ["b"]
    assert store.read_calls == 2
    assert BM25SparseRetriever._cache[(store, "documents")].validity_token == (
        f"{_DURABLE_PREFIX}:epoch-new:3"
    )


# ── Mutation during the build ──────────────────────────────────────────


def test_mutation_during_build_is_discarded_and_retried() -> None:
    """A mid-build mutation must not be published; the retry rebuilds."""
    store = _MutatingStore(
        [
            ("seed", "seed content tapir unique filler"),
            ("fill", "filler gamma delta content"),
        ],
        added_row=("added", "fresh content pangolin unique filler"),
    )
    retriever = BM25SparseRetriever("documents", store=store)

    results = retriever.query("pangolin", top_n=5)

    # Attempt one read the pre-mutation rows and was discarded; attempt
    # two observed the post-mutation state and was published.
    assert store.read_calls == 2
    assert [row[1] for row in results] == ["added"]
    assert BM25SparseRetriever._cache[(store, "documents")].validity_token == (
        f"{_DURABLE_PREFIX}:epoch-a:2"
    )
    assert [row.doc_id for row in BM25SparseRetriever._cache[(store, "documents")].rows] == [
        "seed",
        "fill",
        "added",
    ]


def test_continuous_mutation_exhausts_bounded_retries_and_publishes_nothing() -> None:
    """A store mutating on every token read serves uncached, publishes nothing."""
    store = _ScriptedStore(
        [
            ("seed", "seed content tapir unique filler"),
            ("fill1", "filler one gamma delta content"),
            ("fill2", "filler two gamma epsilon content"),
        ],
        data_version=lambda: f"{_DURABLE_PREFIX}:epoch-spin:{next(store._spin)}",
    )
    store._spin = iter(range(1000))  # type: ignore[attr-defined]
    retriever = BM25SparseRetriever("documents", store=store)

    results = retriever.query("tapir", top_n=5)

    # The query is still served (best effort) with the last-read rows…
    assert [row[1] for row in results] == ["seed"]
    # …the bounded policy ran out of attempts…
    assert store.read_calls == _MAX_BUILD_ATTEMPTS
    # …and nothing unstable was installed in the cache.
    assert (store, "documents") not in BM25SparseRetriever._cache


# ── Separate-process mutation during the build (Lance) ─────────────────


_WRITER_SCRIPT = textwrap.dedent(
    """
    import sys
    from rag_mcp.core.vectordb.identity import EmbeddingIdentity
    from rag_mcp.core.vectordb.lancedb import LanceVectorStore

    uri, collection, phase = sys.argv[1], sys.argv[2], sys.argv[3]
    vector = [1.0] + [0.0] * 383
    identity = EmbeddingIdentity(provider="test", model="mock")
    store = LanceVectorStore(uri=uri)

    def upsert(rows):
        store.upsert_precomputed(
            collection,
            ids=[r[0] for r in rows],
            documents=[r[1] for r in rows],
            metadatas=[{"file_path": r[2]} for r in rows],
            embeddings=[vector for _ in rows],
            embedding_identity=identity,
        )

    if phase == "seed":
        upsert([
            ("seed", "seed content tapir unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ])
    elif phase == "upsert":
        upsert([("mid-build", "fresh content pangolin unique beta filler", "mid_build.txt")])
    elif phase == "recreate":
        store.delete_collection(collection)
        upsert([
            ("seed", "recreated content aardwolf unique alpha filler", "seed.txt"),
            ("fill1", "filler one gamma delta content", "fill1.txt"),
            ("fill2", "filler two gamma epsilon content", "fill2.txt"),
        ])
    else:
        raise SystemExit(f"unknown phase: {phase}")
    """
)


def _run_writer(uri: str, collection: str, phase: str) -> None:
    """Run one writer phase in a separate process against the shared database."""
    completed = subprocess.run(
        [sys.executable, "-c", _WRITER_SCRIPT, uri, collection, phase],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"Writer subprocess phase {phase!r} failed:\n{completed.stderr}"
    )


def _seed_from_subprocess(tmp_path: Path) -> tuple[str, str, LanceVectorStore]:
    """Seed a collection from a writer process; return (uri, collection, reader)."""
    uri = str(tmp_path / "midbuild_lance")
    collection = "documents"
    _run_writer(uri, collection, "seed")
    return uri, collection, LanceVectorStore(uri=uri)


def _mutate_mid_build(
    reader: LanceVectorStore,
    uri: str,
    collection: str,
    phase: str,
) -> None:
    """Fire one separate-process write after the first row of the next scan.

    The hook wraps only the reader's *next* row scans: the writer runs
    once, inside the rebuild's row fetch, so its mutation lands between
    the rebuild's pre-fetch and pre-publish token reads.
    """
    original = reader.iter_documents
    state = {"fired": False}

    def iter_with_mid_build_write(collection_name: str, page_size: int | None = None):
        for row in original(collection_name, page_size):
            yield row
            if not state["fired"]:
                state["fired"] = True
                _run_writer(uri, collection, phase)

    reader.iter_documents = iter_with_mid_build_write  # type: ignore[method-assign]


def test_separate_process_mutation_during_build_is_not_cached(tmp_path: Path) -> None:
    """A subprocess write landing mid-build is discarded, retried, then seen."""
    uri, collection, reader = _seed_from_subprocess(tmp_path)
    retriever = BM25SparseRetriever(collection, store=reader)
    token_before = reader.get_data_version(collection)

    _mutate_mid_build(reader, uri, collection, "upsert")
    results = retriever.query("pangolin", top_n=5)

    assert [row[1] for row in results] == ["mid-build"]
    token_after = reader.get_data_version(collection)
    assert token_after != token_before
    published = BM25SparseRetriever._cache[(reader, collection)]
    assert published.validity_token == token_after
    assert [row.doc_id for row in published.rows] == ["seed", "fill1", "fill2", "mid-build"]


def test_separate_process_recreation_during_build_is_not_cached(tmp_path: Path) -> None:
    """A subprocess delete/recreate landing mid-build forces a fresh build."""
    uri, collection, reader = _seed_from_subprocess(tmp_path)
    retriever = BM25SparseRetriever(collection, store=reader)
    token_before = reader.get_data_version(collection)

    _mutate_mid_build(reader, uri, collection, "recreate")
    results = retriever.query("aardwolf", top_n=5)

    assert [row[1] for row in results] == ["seed"]
    token_after = reader.get_data_version(collection)
    assert token_after != token_before
    published = BM25SparseRetriever._cache[(reader, collection)]
    assert published.validity_token == token_after
    # The published build reflects the recreated incarnation, not the
    # pre-recreation snapshot the first (discarded) attempt read.
    assert [row.doc_id for row in published.rows] == ["seed", "fill1", "fill2"]
