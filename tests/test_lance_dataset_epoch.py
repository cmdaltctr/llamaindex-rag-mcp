"""Durable dataset-epoch behaviour for the LanceDB vector store.

Stage 2 of ``fix-retrieval-freshness-and-context-assembly-2`` (tasks
2.2, 2.5 and 2.6): pins the lifecycle of the Lance durable
data-version token — ``(omrg_dataset_epoch, table.version)`` — against
ordinary mutations, overwrite-based rebuilds, delete/recreate
collisions on the numeric version, legacy unmarked tables, version
cleanup/optimisation, and cross-process rebuilds observed through the
store's per-call table reopen.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
import pytest

from rag_mcp.core.vectordb.identity import EmbeddingIdentity
from rag_mcp.core.vectordb.lance_epoch import (
    durable_data_token,
    parse_durable_data_token,
)
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_PRECOMPUTED_IDENTITY = EmbeddingIdentity(provider="test", model="mock")
_EMBEDDING = [1.0, 0.0]


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
        extra_metadata: Additional metadata keys applied to every row;
            a key absent from the table schema triggers the store's
            overwrite-based struct evolution (the rebuild path).
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
        embeddings=[list(_EMBEDDING) for _ in rows],
        embedding_identity=_PRECOMPUTED_IDENTITY,
    )


def _epoch_and_version(store: LanceVectorStore, collection: str) -> tuple[str, int]:
    """Return the ``(epoch, numeric_version)`` components of the token."""
    token = store.get_data_version(collection)
    assert token is not None, f"Collection {collection!r} has no durable token."
    return parse_durable_data_token(token)


def _create_legacy_table(uri: str, name: str, rows: list[tuple[str, str, str]]) -> None:
    """Create an adapter-shaped Lance table with no OMRG dataset epoch.

    Simulates a table written by an older OMRG version or an external
    writer: the schema matches what the store produces, but the schema
    metadata carries no ``omrg_dataset_epoch`` key.
    """
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("doc_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), len(_EMBEDDING))),
            pa.field("text", pa.string()),
            pa.field("metadata", pa.struct([pa.field("file_path", pa.string())])),
        ]
    )
    data = [
        {
            "id": row_id,
            "doc_id": None,
            "vector": list(_EMBEDDING),
            "text": text,
            "metadata": {"file_path": file_path},
        }
        for row_id, text, file_path in rows
    ]
    lancedb.connect(uri).create_table(name, data=data, schema=schema, mode="create")


def _numeric_table_version(uri: str, collection: str) -> int:
    """Return the raw Lance table version, bypassing the store adapter."""
    return lancedb.connect(uri).open_table(collection).version


# ── Ordinary mutations (task 2.5) ──────────────────────────────────────


class TestOrdinaryMutationsPreserveEpoch:
    """Row mutations keep the epoch and advance the numeric version."""

    def test_token_is_tagged_and_parseable(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lance"))
        _upsert(store, "docs", [("a", "alpha", "a.txt")])

        token = store.get_data_version("docs")

        assert token is not None
        assert token.count(":") == 2  # tag : epoch : version
        epoch, version = parse_durable_data_token(token)
        assert len(epoch) == 36  # UUID4 string form.
        assert version >= 1
        assert durable_data_token(epoch, version) == token

    def test_upsert_write_delete_where_delete_ids_preserve_epoch(self, tmp_path: Path) -> None:
        uri = str(tmp_path / "lance")
        store = LanceVectorStore(uri=uri)
        _upsert(
            store,
            "docs",
            [("a", "alpha", "a.txt"), ("b", "beta", "b.txt"), ("c", "gamma", "c.txt")],
        )
        epoch, version = _epoch_and_version(store, "docs")

        _upsert(store, "docs", [("d", "delta", "d.txt")])
        epoch_write, version_write = _epoch_and_version(store, "docs")
        assert epoch_write == epoch
        assert version_write > version

        store.delete_where("docs", {"file_path": "d.txt"})
        epoch_del, version_del = _epoch_and_version(store, "docs")
        assert epoch_del == epoch
        assert version_del > version_write
        assert store.count("docs") == 3

        store.delete_ids("docs", ["a", "b"])
        epoch_ids, version_ids = _epoch_and_version(store, "docs")
        assert epoch_ids == epoch
        assert version_ids > version_del
        assert store.count("docs") == 1

    def test_adapter_write_nodes_path_preserves_epoch(self, tmp_path: Path) -> None:
        """The LlamaIndex adapter write path keeps an installed epoch.

        Nodes carry a SOURCE relationship (as pipeline nodes do) so the
        second write is an ordinary append, not the TDR-012 null-column
        widen — which is a rebuild and mints a new epoch by design.
        """
        from llama_index.core.schema import (
            NodeRelationship,
            RelatedNodeInfo,
            TextNode,
        )

        def pipeline_node(text: str, file_path: str, source_id: str) -> TextNode:
            node = TextNode(text=text, metadata={"file_path": file_path})
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=source_id)
            return node

        store = LanceVectorStore(uri=str(tmp_path / "lance"))
        store.write_nodes([pipeline_node("first row", "a.txt", "source-a")], "docs")
        epoch, version = _epoch_and_version(store, "docs")

        store.write_nodes([pipeline_node("adapter row", "n.txt", "source-n")], "docs")

        epoch_after, version_after = _epoch_and_version(store, "docs")
        assert epoch_after == epoch
        assert version_after > version


# ── Rebuild and recreation (task 2.5) ─────────────────────────────────


class TestRebuildAndRecreationReplaceEpoch:
    """Overwrite rebuilds and recreations mint a fresh epoch."""

    def test_overwrite_rebuild_replaces_epoch(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lance"))
        _upsert(store, "docs", [("a", "alpha", "a.txt")])
        epoch_before, _ = _epoch_and_version(store, "docs")

        # A metadata key absent from the schema forces the store's
        # overwrite-based struct evolution — the rebuild path.
        _upsert(store, "docs", [("b", "beta", "b.txt")], extra_metadata={"new_key": "v"})

        epoch_after, _ = _epoch_and_version(store, "docs")
        assert epoch_after != epoch_before

    def test_delete_recreate_replaces_epoch_on_colliding_numeric_version(
        self, tmp_path: Path
    ) -> None:
        """A recreation reaching the cached numeric version still differs."""
        uri = str(tmp_path / "lance")
        collection = "docs"
        store = LanceVectorStore(uri=uri)
        _upsert(
            store,
            collection,
            [("a", "alpha", "a.txt"), ("b", "beta", "b.txt")],
        )
        epoch_cached, target_version = _epoch_and_version(store, collection)
        token_cached = store.get_data_version(collection)

        store.delete_collection(collection)
        # Recreate and walk the restarted version history back to the
        # exact numeric version the reader already cached.
        _upsert(store, collection, [("a", "recreated alpha", "a.txt")])
        for cycle in range(target_version + 5):
            if _numeric_table_version(uri, collection) == target_version:
                break
            _upsert(
                store,
                collection,
                [(f"filler-{cycle}", f"filler {cycle}", f"f{cycle}.txt")],
            )
        else:
            raise AssertionError("Recreated table never reached the target version.")
        assert _numeric_table_version(uri, collection) == target_version

        epoch_new, version_new = _epoch_and_version(store, collection)
        assert version_new == target_version
        assert epoch_new != epoch_cached
        assert store.get_data_version(collection) != token_cached


# ── Cross-process observation (task 2.5) ──────────────────────────────


_REBUILDER_SCRIPT = textwrap.dedent(
    """
    import sys

    from rag_mcp.core.vectordb.identity import EmbeddingIdentity
    from rag_mcp.core.vectordb.lancedb import LanceVectorStore

    uri, collection = sys.argv[1], sys.argv[2]
    store = LanceVectorStore(uri=uri)
    # The rebuild_marker key is absent from the seeded schema, so this
    # upsert takes the overwrite-based struct-evolution path and mints
    # a fresh dataset epoch in the child process.
    store.upsert_precomputed(
        collection,
        ids=["subproc-row"],
        documents=["subprocess rebuilt row"],
        metadatas=[{"file_path": "subproc.txt", "rebuild_marker": "stage-2"}],
        embeddings=[[1.0, 0.0]],
        embedding_identity=EmbeddingIdentity(provider="test", model="mock"),
    )
    """
)


def test_long_lived_reader_observes_subprocess_rebuild_epoch(tmp_path: Path) -> None:
    """A reader holding an open store sees a child's new epoch on reopen.

    LanceDB table handles pin a manifest version, so the durable read
    must re-open the table per call (the supported refresh path) for a
    long-lived reader to observe another process's rebuild without a
    restart.
    """
    uri = str(tmp_path / "lance")
    reader = LanceVectorStore(uri=uri)
    _upsert(reader, "docs", [("a", "alpha", "a.txt")])
    epoch_before, _ = _epoch_and_version(reader, "docs")

    completed = subprocess.run(
        [sys.executable, "-c", _REBUILDER_SCRIPT, uri, "docs"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, f"Rebuilder subprocess failed:\n{completed.stderr}"

    epoch_after, _ = _epoch_and_version(reader, "docs")
    assert epoch_after != epoch_before


# ── Legacy unmarked tables (task 2.6) ─────────────────────────────────


class TestLegacyTables:
    """Tables without an epoch read as unavailable and never mutate."""

    def test_reads_return_none_and_never_mutate(self, tmp_path: Path) -> None:
        uri = str(tmp_path / "lance")
        _create_legacy_table(uri, "legacy", [("x", "legacy row", "x.txt")])
        store = LanceVectorStore(uri=uri)
        version_before = _numeric_table_version(uri, "legacy")

        assert store.get_data_version("legacy") is None
        assert store.get_data_version("legacy") is None

        assert _numeric_table_version(uri, "legacy") == version_before

    def test_next_omrg_mutation_installs_epoch_before_row_mutation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The epoch write must precede the row mutation on a legacy table."""
        uri = str(tmp_path / "lance")
        _create_legacy_table(uri, "legacy", [("x", "legacy row", "x.txt")])
        store = LanceVectorStore(uri=uri)
        order: list[str] = []

        original_ensure = LanceVectorStore.ensure_dataset_epoch

        def spy_ensure(self: LanceVectorStore, collection_name: str) -> None:
            order.append("ensure_epoch")
            original_ensure(self, collection_name)

        table_class = type(lancedb.connect(uri).open_table("legacy"))
        original_delete = table_class.delete

        def spy_delete(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("delete")
            return original_delete(self, *args, **kwargs)

        monkeypatch.setattr(LanceVectorStore, "ensure_dataset_epoch", spy_ensure)
        monkeypatch.setattr(table_class, "delete", spy_delete)

        store.delete_where("legacy", {"file_path": "x.txt"})

        assert order == ["ensure_epoch", "delete"]
        assert store.get_data_version("legacy") is not None
        assert store.count("legacy") == 0

    def test_delete_ids_installs_epoch_on_legacy_table(self, tmp_path: Path) -> None:
        uri = str(tmp_path / "lance")
        _create_legacy_table(uri, "legacy_ids", [("x", "legacy row", "x.txt")])
        store = LanceVectorStore(uri=uri)

        store.delete_ids("legacy_ids", ["x"])

        assert store.get_data_version("legacy_ids") is not None

    def test_external_recreation_without_marker_returns_none(self, tmp_path: Path) -> None:
        """A recreation by an unmarked external writer inherits nothing."""
        uri = str(tmp_path / "lance")
        store = LanceVectorStore(uri=uri)
        _upsert(store, "docs", [("a", "alpha", "a.txt")])
        assert store.get_data_version("docs") is not None

        raw = lancedb.connect(uri)
        raw.drop_table("docs")
        _create_legacy_table(uri, "docs", [("y", "external row", "y.txt")])

        assert store.get_data_version("docs") is None


# ── Cleanup and optimisation (task 2.6) ───────────────────────────────


def test_cleanup_and_optimisation_preserve_epoch(tmp_path: Path) -> None:
    """Version-history pruning must not erase the current-table epoch."""
    uri = str(tmp_path / "lance")
    store = LanceVectorStore(uri=uri)
    _upsert(
        store,
        "docs",
        [("a", "alpha", "a.txt"), ("b", "beta", "b.txt"), ("c", "gamma", "c.txt")],
    )
    epoch, version = _epoch_and_version(store, "docs")

    table = lancedb.connect(uri).open_table("docs")
    table.to_lance().cleanup_old_versions(older_than=0, delete_unverified=False)
    lancedb.connect(uri).open_table("docs").optimize()

    epoch_after, _ = _epoch_and_version(store, "docs")
    assert epoch_after == epoch

    # The next ordinary mutation must still change the complete token.
    _upsert(store, "docs", [("d", "delta", "d.txt")])
    epoch_next, version_next = _epoch_and_version(store, "docs")
    assert epoch_next == epoch
    assert version_next > version
