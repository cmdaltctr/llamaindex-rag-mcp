"""LanceDB-specific store behaviour: embedding identity and hybrid retrieval.

Identity tests mirror the ChromaDB semantics documented in
``core/vectordb/identity.py`` — legacy stamp-then-reject — asserted
through public ``VectorStore`` ABC methods plus ``EmbeddingIdentity``
only.  Hybrid tests mirror ``test_hybrid_retrieval.py``: the in-memory
BM25 sparse retriever must build its index from ``iter_documents`` and
rebuild whenever a write or delete advances the generation counter (an
explicit LanceDB-spec difference from the Chroma pipeline, where the
ingestion writer owns write-side bumping).

All tests run offline against an isolated on-disk database under
``tmp_path`` using the conftest MockEmbedding (384 dims).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_mcp.core.retrieval.sparse import BM25SparseRetriever
from rag_mcp.core.vectordb.identity import (
    IDENTITY_INDEX_KEY,
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    EmbeddingIdentity,
)
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

# ── Embedding identity (task 6.3) ─────────────────────────────────────


class TestEmbeddingIdentity:
    """Identity stamping and rejection through public ABC methods."""

    def test_identity_round_trip_and_reread(self, tmp_path: Path) -> None:
        """A stored identity survives reconnection and accepts the same identity.

        Store A writes with an identity; a NEW store instance on the same
        uri re-reads the stored identity, so a second write with the SAME
        identity succeeds, and the stored triple is visible through
        ``get_collection_metadata``.
        """
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        identity = EmbeddingIdentity(provider="local", model="nomic-embed-text")

        store_a = LanceVectorStore(uri=uri, embedding_identity=identity)
        store_a.write_nodes([TextNode(text="first", metadata={"file_path": "a.txt"})], "roundtrip")

        store_b = LanceVectorStore(uri=uri, embedding_identity=identity)
        store_b.write_nodes([TextNode(text="second", metadata={"file_path": "b.txt"})], "roundtrip")

        meta = store_b.get_collection_metadata("roundtrip")
        assert meta is not None
        assert meta.get(IDENTITY_PROVIDER_KEY) == "local"
        assert meta.get(IDENTITY_MODEL_KEY) == "nomic-embed-text"

    def test_mismatched_identity_rejected_on_write_and_query(self, tmp_path: Path) -> None:
        """A different identity must be rejected before write AND query.

        The error message must mention the collection name; the exact
        wording is the implementation's concern.
        """
        from llama_index.core import Settings
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        original = EmbeddingIdentity(provider="local", model="model-a")
        other = EmbeddingIdentity(provider="local", model="model-b")

        LanceVectorStore(uri=uri, embedding_identity=original).write_nodes(
            [TextNode(text="seed")], "mismatch"
        )

        reopened = LanceVectorStore(uri=uri, embedding_identity=other)
        with pytest.raises(ValueError, match="mismatch"):
            reopened.write_nodes([TextNode(text="more")], "mismatch")

        embedding = Settings.embed_model.get_query_embedding("seed")
        with pytest.raises(ValueError, match="mismatch"):
            reopened.query_dense("mismatch", list(embedding), n_results=1)

    def test_legacy_collection_stamped_and_profile_preserved(self, tmp_path: Path) -> None:
        """A legacy (unstamped) collection gains the identity on first write.

        Store A runs without an identity (the pre-cloud direct-call path)
        and tags the collection with a profile.  Store B, with an
        identity attached, must stamp the identity AND preserve the
        profile tag — the read-merge-write rule from ``identity.py``.
        """
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        legacy = LanceVectorStore(uri=uri)  # identity=None: never stamps
        legacy.write_nodes([TextNode(text="legacy chunk")], "legacy")
        legacy.update_collection_metadata("legacy", {"profile": "codebase"})

        identity = EmbeddingIdentity(provider="local", model="nomic-embed-text")
        upgraded = LanceVectorStore(uri=uri, embedding_identity=identity)
        upgraded.write_nodes([TextNode(text="after upgrade")], "legacy")

        meta = upgraded.get_collection_metadata("legacy")
        assert meta is not None
        assert meta.get("profile") == "codebase"
        assert meta.get(IDENTITY_MODEL_KEY) == "nomic-embed-text"

    def test_no_identity_never_stamps(self, tmp_path: Path) -> None:
        """identity=None must leave no rag_embed_* keys anywhere."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="plain chunk")], "plain")

        meta = store.get_collection_metadata("plain")
        for key in (IDENTITY_PROVIDER_KEY, IDENTITY_MODEL_KEY, IDENTITY_INDEX_KEY):
            assert key not in (meta or {})

    def test_profile_metadata_survives_reopen(self, tmp_path: Path) -> None:
        """Collection metadata written by one instance is read by the next."""
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        store_a = LanceVectorStore(uri=uri)
        store_a.write_nodes([TextNode(text="seed")], "profiles")
        store_a.update_collection_metadata("profiles", {"profile": "documents"})

        store_b = LanceVectorStore(uri=uri)
        meta = store_b.get_collection_metadata("profiles")
        assert meta is not None
        assert meta.get("profile") == "documents"


# ── Hybrid retrieval + generation counter (task 6.4) ─────────────────


class TestHybridRetrieval:
    """BM25 sparse retrieval over a LanceDB-backed collection."""

    def test_bm25_builds_index_from_iter_documents(self, tmp_path: Path) -> None:
        """The in-memory BM25 retriever must rank rare terms first.

        Mirrors the exact-rare-term test in ``test_hybrid_retrieval.py``,
        with the real store substituted for the FakeStore double.
        """
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        nodes = [
            TextNode(
                text="Ancient amphitheatres hosted spectacles.",
                metadata={"file_path": "semantic.txt"},
            ),
            TextNode(
                text="The continuity note contains ZXQ-77 for the Colosseum.",
                metadata={"file_path": "rare.txt"},
            ),
            TextNode(
                text="Modern stadium design uses concrete.",
                metadata={"file_path": "noise.txt"},
            ),
        ]
        collection = "lance_bm25_build"
        store.write_nodes(nodes, collection)

        retriever = BM25SparseRetriever(collection_name=collection, store=store)
        results = retriever.query("ZXQ-77", top_n=3)

        assert results
        rank, _doc_id, text, metadata = results[0]
        assert rank == 1
        assert "ZXQ-77" in text
        assert metadata["file_path"] == "rare.txt"

    def test_write_and_delete_advance_generation_and_rebuild_bm25(self, tmp_path: Path) -> None:
        """Every write and delete must advance the generation counter.

        The LanceDB spec is deliberately stronger than the Chroma
        pipeline here: the store itself advances the counter on write
        and delete, so the BM25 index rebuilds without an external
        bump from the ingestion writer.
        """
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        nodes = [
            TextNode(text="raredelete token", metadata={"file_path": "gone.txt"}),
            TextNode(text="filler alpha content", metadata={"file_path": "fill1.txt"}),
            TextNode(text="filler beta content", metadata={"file_path": "fill2.txt"}),
        ]
        collection = "lance_generation"
        store.write_nodes(nodes, collection)
        assert store.get_generation(collection) > 0
        generation_after_write = store.get_generation(collection)

        retriever = BM25SparseRetriever(collection_name=collection, store=store)
        first_pass = retriever.query("raredelete", top_n=5)
        assert first_pass
        assert "raredelete" in first_pass[0][2]

        store.delete_where(collection, {"file_path": "gone.txt"})
        assert store.get_generation(collection) > generation_after_write

        # The generation advance must invalidate the cached BM25 index:
        # the deleted chunk can no longer be retrieved.
        assert retriever.query("raredelete", top_n=5) == []


# ── Bulk reads, pagination, and lifecycle edges ──────────────────────


class TestBulkAndPagedReads:
    """``fetch_all`` shapes and multi-page iteration."""

    @staticmethod
    def _seed(store: LanceVectorStore, collection: str) -> None:
        from llama_index.core.schema import TextNode

        store.write_nodes(
            [
                TextNode(text="alpha", metadata={"file_path": "a.txt"}),
                TextNode(text="beta", metadata={"file_path": "b.txt"}),
                TextNode(text="gamma", metadata={"file_path": "c.txt"}),
            ],
            collection,
        )

    def test_fetch_all_missing_collection_returns_none(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        assert store.fetch_all("nope", ["metadatas"]) is None

    @pytest.mark.parametrize(
        "include",
        [
            ["metadatas"],
            ["documents"],
            ["embeddings"],
            ["metadatas", "documents", "embeddings"],
        ],
        ids=["metadatas", "documents", "embeddings", "all"],
    )
    def test_fetch_all_returns_requested_fields(self, tmp_path: Path, include: list) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        self._seed(store, "bulk")

        payload = store.fetch_all("bulk", include)
        assert payload is not None
        assert len(payload["ids"]) == 3
        for field in include:
            assert len(payload[field]) == 3
        if "metadatas" in include:
            assert all(isinstance(m, dict) for m in payload["metadatas"])
            assert {"a.txt", "b.txt", "c.txt"} == {m["file_path"] for m in payload["metadatas"]}
        if "documents" in include:
            assert set(payload["documents"]) == {"alpha", "beta", "gamma"}
        if "embeddings" in include:
            assert all(len(e) == 384 for e in payload["embeddings"])

    def test_fetch_all_intent_only_collection_returns_none(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.create_collection("intentonly")
        assert store.fetch_all("intentonly", ["documents"]) is None

    def test_iter_documents_walks_multiple_pages(self, tmp_path: Path) -> None:
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes(
            [TextNode(text=f"row {i}", metadata={"i": i}) for i in range(5)],
            "paged",
        )
        rows = list(store.iter_documents("paged", page_size=2))
        assert len(rows) == 5
        assert [r[2]["i"] for r in rows] == sorted(r[2]["i"] for r in rows)

    def test_default_page_size_used_when_omitted(self, tmp_path: Path) -> None:
        """page_size=None reads the composition-root default scan size."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="one", metadata={"k": "v"})], "defaultpage")
        assert len(list(store.iter_metadatas("defaultpage"))) == 1


class TestLifecycleEdges:
    """Delete-collection branches and the open-table race guard."""

    def test_delete_missing_collection_raises(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        with pytest.raises(ValueError, match="does not exist"):
            store.delete_collection("never_there")

    def test_delete_intent_only_collection_succeeds(self, tmp_path: Path) -> None:
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.create_collection("ghost")
        store.delete_collection("ghost")
        assert not store.collection_exists("ghost")

    def test_open_table_race_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """A table dropped between listing and open reads as absent."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="x")], "race")
        connection = store._get_connection()
        original_open = connection.open_table

        def _raise(_name):
            raise ValueError("Table 'race' was not found")

        monkeypatch.setattr(connection, "open_table", _raise)
        try:
            assert store._open_table("race") is None
            assert store.count("race") == 0
        finally:
            monkeypatch.setattr(connection, "open_table", original_open)


class TestUpsertAndMetadataEdges:
    """Precomputed upserts into adapter tables and metadata decoding."""

    def test_upsert_into_written_collection(self, tmp_path: Path) -> None:
        """Upserting after a node write reuses the live table schema."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="seed", metadata={"k": "v"})], "mixed")
        from llama_index.core import Settings

        embedding = Settings.embed_model.get_query_embedding("probe")
        store.upsert_precomputed(
            "mixed",
            ids=["row-1"],
            documents=["probe"],
            metadatas=[{"k": "w"}],
            embeddings=[list(embedding)],
        )
        assert store.count("mixed") == 2
        assert store.count_where("mixed", {"k": "w"}) == 1

    def test_non_json_metadata_value_falls_back_to_raw_string(self, tmp_path: Path) -> None:
        """A value written without JSON encoding still reads back."""
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        store = LanceVectorStore(uri=uri)
        store.write_nodes([TextNode(text="x")], "rawmeta")
        table = store._get_connection().open_table("rawmeta")
        table.to_lance().update_schema_metadata({"legacy_key": "not-json"})

        reopened = LanceVectorStore(uri=uri)
        meta = reopened.get_collection_metadata("rawmeta")
        assert meta is not None
        assert meta["legacy_key"] == "not-json"

    def test_index_identity_stamped_and_enforced(self, tmp_path: Path) -> None:
        """A full identity triple, including index_identity, round-trips."""
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        identity = EmbeddingIdentity(provider="local", model="m", index_identity="corpus-hash-1")
        LanceVectorStore(uri=uri, embedding_identity=identity).write_nodes(
            [TextNode(text="x")], "indexed"
        )
        reopened = LanceVectorStore(uri=uri, embedding_identity=identity)
        meta = reopened.get_collection_metadata("indexed")
        assert meta is not None
        assert meta[IDENTITY_INDEX_KEY] == "corpus-hash-1"


# ── Metadata struct evolution ────────────────────────────────────────


class TestSchemaEvolution:
    """Later writes introducing new metadata keys must not lose them.

    LanceDB fixes the ``metadata`` struct on the first write; without
    evolution a node write raises and a precomputed upsert silently
    drops the new key (review finding: incremental ingestion breaks
    whenever metadata keys vary between batches).
    """

    def test_write_nodes_introduces_new_field(self, tmp_path: Path) -> None:
        """A second node write with a new key succeeds and stores it."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="one", metadata={"k": "v"})], "evo")
        store.write_nodes([TextNode(text="two", metadata={"k": "w", "category": "AI"})], "evo")

        assert store.count("evo") == 2
        assert store.count_where("evo", {"category": "AI"}) == 1
        metadatas = list(store.iter_metadatas("evo"))
        assert next(m for m in metadatas if m and m.get("k") == "w")["category"] == "AI"

    def test_upsert_precomputed_introduces_new_field(self, tmp_path: Path) -> None:
        """A precomputed upsert with a new key stores it (no silent drop)."""
        from llama_index.core import Settings

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        embedding = list(Settings.embed_model.get_query_embedding("x"))
        store.upsert_precomputed(
            "evo", ids=["1"], documents=["one"], metadatas=[{"k": "v"}], embeddings=[embedding]
        )
        store.upsert_precomputed(
            "evo",
            ids=["2"],
            documents=["two"],
            metadatas=[{"category": "AI"}],
            embeddings=[embedding],
        )

        assert store.count_where("evo", {"category": "AI"}) == 1

    def test_upsert_into_adapter_table_introduces_new_field(self, tmp_path: Path) -> None:
        """Upserting after an adapter write grows the adapter-made struct."""
        from llama_index.core import Settings
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="one", metadata={"k": "v"})], "mixed")
        embedding = list(Settings.embed_model.get_query_embedding("x"))
        store.upsert_precomputed(
            "mixed",
            ids=["row-1"],
            documents=["two"],
            metadatas=[{"new_key": "yes"}],
            embeddings=[embedding],
        )
        assert store.count_where("mixed", {"new_key": "yes"}) == 1

    def test_write_nodes_into_upsert_table_adds_internal_keys(self, tmp_path: Path) -> None:
        """An adapter write into an upsert-created table must not fail.

        The adapter writes its internal keys into the metadata struct;
        an upsert-created struct lacks them, so evolution must add
        them before the adapter write.
        """
        from llama_index.core import Settings
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        embedding = list(Settings.embed_model.get_query_embedding("x"))
        store.upsert_precomputed(
            "upsert_first",
            ids=["1"],
            documents=["one"],
            metadatas=[{"k": "v"}],
            embeddings=[embedding],
        )
        store.write_nodes([TextNode(text="two", metadata={"k": "w"})], "upsert_first")
        assert store.count("upsert_first") == 2

    def test_evolution_preserves_identity_and_profile(self, tmp_path: Path) -> None:
        """The table rewrite carries the identity triple and profile tags."""
        from llama_index.core.schema import TextNode

        uri = str(tmp_path / "lancedb")
        identity = EmbeddingIdentity(provider="local", model="nomic-embed-text")
        store = LanceVectorStore(uri=uri, embedding_identity=identity)
        store.write_nodes([TextNode(text="one", metadata={"k": "v"})], "keep")
        store.update_collection_metadata("keep", {"profile": "documents"})

        store.write_nodes([TextNode(text="two", metadata={"k": "w", "category": "AI"})], "keep")

        meta = store.get_collection_metadata("keep")
        assert meta is not None
        assert meta.get("profile") == "documents"
        assert meta.get(IDENTITY_MODEL_KEY) == "nomic-embed-text"

    def test_non_string_evolved_field_type(self, tmp_path: Path) -> None:
        """A new integer-valued field keeps its type through evolution."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="one", metadata={"k": "v"})], "typed")
        store.write_nodes([TextNode(text="two", metadata={"rank": 7})], "typed")
        assert store.count_where("typed", {"rank": {"$gt": 5}}) == 1


# ── Collection-drop generation invalidation ──────────────────────────


class TestDeleteCollectionGeneration:
    """Dropping a collection must invalidate a cached BM25 index."""

    def test_drop_advances_generation(self, tmp_path: Path) -> None:
        """Direct store-level drop bumps the generation counter."""
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes([TextNode(text="x")], "dropme")
        before = store.get_generation("dropme")
        store.delete_collection("dropme")
        assert store.get_generation("dropme") > before

    def test_drop_intent_only_advances_generation(self, tmp_path: Path) -> None:
        """Dropping a never-written collection also invalidates."""
        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.create_collection("ghost")
        assert store.get_generation("ghost") == 0
        store.delete_collection("ghost")
        assert store.get_generation("ghost") > 0

    def test_drop_invalidates_cached_bm25_index(self, tmp_path: Path) -> None:
        """A BM25 index built before the drop returns nothing after it.

        Three documents: the rare term must rank before the drop and
        vanish after it (single-document corpora clip IDF to zero, so
        the corpus mirrors the sibling hybrid test's shape).
        """
        from llama_index.core.schema import TextNode

        store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        store.write_nodes(
            [
                TextNode(text="orphantoken content", metadata={"file_path": "gone.txt"}),
                TextNode(text="filler alpha", metadata={"file_path": "fill1.txt"}),
                TextNode(text="filler beta", metadata={"file_path": "fill2.txt"}),
            ],
            "bm25drop",
        )
        retriever = BM25SparseRetriever(collection_name="bm25drop", store=store)
        assert retriever.query("orphantoken", top_n=5)

        store.delete_collection("bm25drop")
        assert retriever.query("orphantoken", top_n=5) == []
