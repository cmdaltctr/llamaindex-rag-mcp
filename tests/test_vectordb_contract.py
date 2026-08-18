"""Integration test exercising every VectorStore ABC method.

Verifies the contract documented in ``core/vectordb/base.py`` against
every shipped backend: the suite is parametrised over ``chroma`` (the
in-memory EphemeralClient monkeypatched by ``conftest._patch_chromadb``,
so no disk I/O occurs) and ``lancedb`` (an isolated on-disk database
under ``tmp_path``).  Both backends must pass identical assertions —
this file is the contract-parity evidence required by the
``lancedb-vector-store`` spec.

The test covers every operation enumerated in Phase 3 task 1.3:
collection creation, document write (upsert), dense query with metadata
filter, paged metadata/document reads, count + count-by-filter, delete
by filter, delete collection, list collections, collection metadata
read/update, and generation bumping.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from rag_mcp.core.vectordb.base import VectorStore
from rag_mcp.core.vectordb.chroma import ChromaVectorStore
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

# Backend name → concrete class, for the ABC-compliance checks that
# inspect the class itself rather than a constructed instance.
_STORE_CLASSES = {
    "chroma": ChromaVectorStore,
    "lancedb": LanceVectorStore,
}


@pytest.fixture(params=["chroma", "lancedb"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> VectorStore:
    """Return a fresh store for each backend under test.

    ``chroma`` relies on the in-memory EphemeralClient monkeypatched by
    ``conftest._patch_chromadb`` so no disk I/O occurs.  ``lancedb``
    points at an isolated database under ``tmp_path``, giving each test
    a clean on-disk store; the embedded LanceDB writer is fast enough
    to stay out of the ``slow`` mark.
    """
    if request.param == "chroma":
        return ChromaVectorStore()
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


# ── ABC compliance ────────────────────────────────────────────────────


class TestABCCompliance:
    """Every backend implementation must satisfy the ABC contract."""

    def test_store_is_vector_store(self, store: VectorStore) -> None:
        """The parametrised store must be a VectorStore instance."""
        assert isinstance(store, VectorStore)

    @pytest.mark.parametrize("backend", ["chroma", "lancedb"])
    def test_all_abstract_methods_implemented(self, backend: str) -> None:
        """Every ABC method must have a concrete implementation."""
        abstract_methods = {
            "create_collection",
            "collection_exists",
            "delete_collection",
            "list_collections",
            "write_nodes",
            "query_dense",
            "iter_metadatas",
            "iter_documents",
            "count",
            "count_where",
            "delete_where",
            "get_collection_metadata",
            "update_collection_metadata",
            "bump_generation",
            "get_generation",
        }
        implemented = set(_STORE_CLASSES[backend].__abstractmethods__)
        assert implemented == set(), f"Unimplemented abstract methods: {implemented}"
        # Verify the ABC actually declares the expected surface.
        abc_methods = {name for name in dir(VectorStore) if callable(getattr(VectorStore, name))}
        for method in abstract_methods:
            assert method in abc_methods, f"Missing ABC method: {method}"


# ── Collection lifecycle ──────────────────────────────────────────────


class TestCollectionLifecycle:
    def test_create_collection_idempotent(self, store: VectorStore) -> None:
        """Creating a collection twice must not raise."""
        store.create_collection("docs")
        store.create_collection("docs")
        assert store.collection_exists("docs")

    def test_collection_exists_false_for_missing(self, store: VectorStore) -> None:
        assert not store.collection_exists("nonexistent")

    def test_list_collections(self, store: VectorStore) -> None:
        store.create_collection("alpha")
        store.create_collection("beta")
        names = set(store.list_collections())
        assert {"alpha", "beta"}.issubset(names)

    def test_delete_collection(self, store: VectorStore) -> None:
        store.create_collection("temp")
        store.delete_collection("temp")
        assert not store.collection_exists("temp")


# ── Document write + query ────────────────────────────────────────────


class TestWriteAndQuery:
    def test_write_nodes_then_query(self, store: VectorStore) -> None:
        """Written nodes must be retrievable via dense query."""
        from llama_index.core.schema import TextNode

        nodes = [
            TextNode(text="hello world", metadata={"file_path": "a.txt"}),
            TextNode(text="goodbye world", metadata={"file_path": "b.txt"}),
        ]
        store.write_nodes(nodes, "docs")

        # Query with a dummy embedding (MockEmbedding is active in tests).
        from llama_index.core import Settings

        embedding = Settings.embed_model.get_query_embedding("hello")
        results = store.query_dense("docs", list(embedding), n_results=2)
        assert len(results) == 2
        assert "document" in results[0]
        assert "metadata" in results[0]
        assert "id" in results[0]
        assert results[0]["score_kind"] == "dense_similarity_v1"
        assert 0.0 < results[0]["score"] <= 1.0
        assert "distance" not in results[0]

    def test_precomputed_vectors_have_cross_store_semantic_score_parity(
        self, store: VectorStore
    ) -> None:
        """Both adapters expose the same ranking/range/kind invariants.

        Exact numeric equality is intentionally not asserted: ChromaDB and
        LanceDB may report differently scaled native L2 distances. The
        canonical contract is bounded, higher-is-better, and monotonic.
        """
        store.upsert_precomputed(
            "semantic_scores",
            ids=["exact", "near", "far"],
            documents=["exact", "near", "far"],
            metadatas=[{"rank": 1}, {"rank": 2}, {"rank": 3}],
            embeddings=[[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]],
        )

        rows = store.query_dense("semantic_scores", [1.0, 0.0], n_results=3)

        assert [row["id"] for row in rows] == ["exact", "near", "far"]
        assert all(row["score_kind"] == "dense_similarity_v1" for row in rows)
        scores = [row["score"] for row in rows]
        assert scores[0] == pytest.approx(1.0)
        assert all(0.0 < score <= 1.0 for score in scores)
        assert scores == sorted(scores, reverse=True)

    def test_query_with_metadata_filter(self, store: VectorStore) -> None:
        """A metadata filter must restrict results to matching chunks."""
        from llama_index.core.schema import TextNode

        nodes = [
            TextNode(text="python code", metadata={"category": "AI"}),
            TextNode(text="biology text", metadata={"category": "Biology"}),
        ]
        store.write_nodes(nodes, "filtered")

        from llama_index.core import Settings

        embedding = Settings.embed_model.get_query_embedding("code")
        results = store.query_dense(
            "filtered", list(embedding), n_results=2, where={"category": "AI"}
        )
        assert len(results) == 1
        assert results[0]["metadata"]["category"] == "AI"

    def test_query_empty_collection_returns_empty(self, store: VectorStore) -> None:
        store.create_collection("empty")
        results = store.query_dense("empty", [0.0] * 384, n_results=5)
        assert results == []


class TestNativeMetricAssumptions:
    """Adapters must pin or reject metrics outside the canonical contract."""

    def test_chroma_rejects_explicit_non_l2_collection(self) -> None:
        store = ChromaVectorStore()
        collection = store._get_client().get_or_create_collection(
            "unsupported_cosine_metric",
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=["row"],
            documents=["row"],
            metadatas=[{"kind": "probe"}],
            embeddings=[[1.0, 0.0]],
        )

        with pytest.raises(ValueError, match="requires hnsw:space='l2'"):
            store.query_dense("unsupported_cosine_metric", [1.0, 0.0], 1)

    def test_lance_query_pins_l2_instead_of_relying_on_default(self) -> None:
        source = inspect.getsource(LanceVectorStore.query_dense)
        assert '.distance_type("l2")' in source


# ── Paged reads ───────────────────────────────────────────────────────


class TestPagedReads:
    def test_iter_metadatas(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        nodes = [TextNode(text=f"chunk {i}", metadata={"file_path": f"f{i}.txt"}) for i in range(5)]
        store.write_nodes(nodes, "paged")

        metadatas = list(store.iter_metadatas("paged"))
        assert len(metadatas) == 5
        assert all(isinstance(m, dict) for m in metadatas)

    def test_iter_metadatas_small_page(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        nodes = [TextNode(text=f"chunk {i}", metadata={"idx": i}) for i in range(5)]
        store.write_nodes(nodes, "smallpage")

        metadatas = list(store.iter_metadatas("smallpage", page_size=2))
        assert len(metadatas) == 5

    def test_iter_metadatas_invalid_page_size(self, store: VectorStore) -> None:
        store.create_collection("badpage")
        with pytest.raises(ValueError, match="positive"):
            list(store.iter_metadatas("badpage", page_size=0))

    def test_iter_documents(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        nodes = [TextNode(text=f"doc {i}", metadata={"i": i}) for i in range(3)]
        store.write_nodes(nodes, "docs_iter")

        rows = list(store.iter_documents("docs_iter"))
        assert len(rows) == 3
        for chunk_id, text, meta in rows:
            assert isinstance(chunk_id, str)
            assert isinstance(text, str)
            assert isinstance(meta, dict)


# ── Count ─────────────────────────────────────────────────────────────


class TestCount:
    def test_count_empty(self, store: VectorStore) -> None:
        assert store.count("nope") == 0

    def test_count_after_write(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        store.write_nodes([TextNode(text="a"), TextNode(text="b")], "counted")
        assert store.count("counted") == 2

    def test_count_where(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        store.write_nodes(
            [
                TextNode(text="x", metadata={"k": "v1"}),
                TextNode(text="y", metadata={"k": "v2"}),
                TextNode(text="z", metadata={"k": "v1"}),
            ],
            "countwhere",
        )
        assert store.count_where("countwhere", {"k": "v1"}) == 2
        assert store.count_where("countwhere", {"k": "v2"}) == 1
        assert store.count_where("countwhere", {"k": "missing"}) == 0

    def test_missing_field_filter_semantics_match_chroma(self, store: VectorStore) -> None:
        """Absent-key filtering must behave identically on both backends.

        ChromaDB treats a metadata key a row lacks as "not equal":
        ``$ne``/``$nin`` match such rows; equality/membership do not.
        A field absent from every row (and the schema) follows the same
        rule. Both backends must agree on all four shapes — this is
        the parity the review found diverging under SQL NULL rules.
        """
        from llama_index.core.schema import TextNode

        store.write_nodes(
            [
                TextNode(text="no tag", metadata={"file_path": "a.txt"}),
                TextNode(text="tagged", metadata={"file_path": "b.txt", "tag": "x"}),
            ],
            "missingkeys",
        )

        # Rows lacking `tag`: only the second row carries it.
        assert store.count_where("missingkeys", {"tag": "x"}) == 1
        assert store.count_where("missingkeys", {"tag": {"$ne": "x"}}) == 1
        assert store.count_where("missingkeys", {"tag": {"$in": ["x"]}}) == 1
        assert store.count_where("missingkeys", {"tag": {"$nin": ["x"]}}) == 1

        # A field no row carries: equality matches nothing, inequality
        # everything. All four operator shapes are pinned so a
        # regression in schema-absent $in/$nin handling cannot pass.
        assert store.count_where("missingkeys", {"nope": "x"}) == 0
        assert store.count_where("missingkeys", {"nope": {"$ne": "x"}}) == 2
        assert store.count_where("missingkeys", {"nope": {"$in": ["x"]}}) == 0
        assert store.count_where("missingkeys", {"nope": {"$nin": ["x"]}}) == 2


# ── Delete ────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_where(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        store.write_nodes(
            [
                TextNode(text="keep", metadata={"file_path": "keep.txt"}),
                TextNode(text="drop", metadata={"file_path": "drop.txt"}),
            ],
            "deltest",
        )
        assert store.count("deltest") == 2
        store.delete_where("deltest", {"file_path": "drop.txt"})
        assert store.count("deltest") == 1

    def test_delete_where_empty_filter_rejected(self, store: VectorStore) -> None:
        """An empty where must be rejected, never treated as delete-all.

        ChromaDB raises ValueError ("Expected where to have exactly one
        operator"); LanceDB must reject the same call rather than
        translate ``{}`` to "no filter" and delete every row.
        """
        from llama_index.core.schema import TextNode

        store.write_nodes(
            [TextNode(text="safe", metadata={"file_path": "a.txt"})],
            "delempty",
        )
        with pytest.raises(ValueError):
            store.delete_where("delempty", {})
        assert store.count("delempty") == 1


# ── Collection metadata (Phase 4 prep) ────────────────────────────────


class TestCollectionMetadata:
    def test_get_metadata_none_for_new(self, store: VectorStore) -> None:
        store.create_collection("meta")
        result = store.get_collection_metadata("meta")
        # ChromaDB returns None or {} for a fresh collection.
        assert result is None or result == {}

    def test_update_then_get_metadata(self, store: VectorStore) -> None:
        store.create_collection("meta2")
        store.update_collection_metadata("meta2", {"profile": "codebase"})
        result = store.get_collection_metadata("meta2")
        assert result is not None
        assert result.get("profile") == "codebase"

    def test_update_metadata_merges(self, store: VectorStore) -> None:
        store.create_collection("meta3")
        store.update_collection_metadata("meta3", {"a": 1})
        store.update_collection_metadata("meta3", {"b": 2})
        result = store.get_collection_metadata("meta3")
        assert result is not None
        assert result.get("a") == 1
        assert result.get("b") == 2


# ── Generation counter ────────────────────────────────────────────────


class TestGenerationCounter:
    def test_initial_generation_zero(self, store: VectorStore) -> None:
        assert store.get_generation("never_written") == 0

    def test_bump_advances_counter(self, store: VectorStore) -> None:
        assert store.get_generation("g") == 0
        store.bump_generation("g")
        assert store.get_generation("g") == 1
        store.bump_generation("g")
        assert store.get_generation("g") == 2

    def test_upsert_precomputed_advances_generation(self, store: VectorStore) -> None:
        """A direct precomputed upsert invalidates the BM25 cache.

        Pipeline writes are bumped by the ingestion writer; this direct-use
        API has no wrapper, so the store must keep the contract itself.
        """
        store.create_collection("precomputed")
        assert store.get_generation("precomputed") == 0
        store.upsert_precomputed(
            "precomputed",
            ids=["row-1"],
            documents=["probe"],
            metadatas=[{"k": "v"}],
            embeddings=[[0.1, 0.2]],
        )
        assert store.get_generation("precomputed") == 1

    def test_each_successful_mutation_advances_exactly_once(self, store: VectorStore) -> None:
        """Direct store callers get the same invalidation ownership as pipelines."""
        from llama_index.core.schema import TextNode

        name = "exactly_once"
        assert store.get_generation(name) == 0
        store.write_nodes(
            [TextNode(text="keep", metadata={"kind": "keep"})],
            name,
        )
        assert store.get_generation(name) == 1

        store.delete_where(name, {"kind": "keep"})
        assert store.get_generation(name) == 2

        store.delete_collection(name)
        assert store.get_generation(name) == 3

    @pytest.mark.asyncio
    async def test_pipeline_mutations_do_not_add_caller_owned_bumps(
        self, store: VectorStore
    ) -> None:
        """Writer orchestration observes one bump per store mutation."""
        from llama_index.core.schema import TextNode

        from rag_mcp.core.ingestion.writer import embed_and_write_async, remove_document

        name = "pipeline_exactly_once"
        written = await embed_and_write_async(
            [TextNode(text="pipeline row", metadata={"file_path": "pipeline.txt"})],
            collection_name=name,
            store=store,
            embed_concurrency=1,
        )
        assert written == 1
        assert store.get_generation(name) == 1

        result = remove_document("pipeline.txt", collection_name=name, store=store)
        assert result["status"] == "ok"
        assert result["chunks_removed"] == 1
        assert store.get_generation(name) == 2

    def test_generations_are_per_collection(self, store: VectorStore) -> None:
        store.bump_generation("a")
        store.bump_generation("a")
        store.bump_generation("b")
        assert store.get_generation("a") == 2
        assert store.get_generation("b") == 1


# ── Dimension locking (spec MUST scenario) ────────────────────────────


class TestDimensionLocking:
    def test_dimension_locked_on_first_write(self, store: VectorStore) -> None:
        """Writing nodes of a different dimension MUST fail with a clear error.

        Verifies the spec's dimension-locking scenario: the vector
        dimension is fixed at creation time and mismatched writes raise.
        """
        from llama_index.core import Settings
        from llama_index.core.schema import TextNode

        # First write with the test MockEmbedding (384 dims).
        store.write_nodes([TextNode(text="initial")], "dimlock")

        # Swap to a different embedding dimension and try again.
        from llama_index.core.embeddings import MockEmbedding

        original = Settings.embed_model
        try:
            Settings.embed_model = MockEmbedding(embed_dim=128)
            with pytest.raises(Exception):
                store.write_nodes([TextNode(text="wrong dim")], "dimlock")
        finally:
            Settings.embed_model = original


# ── Missing-collection behaviour ──────────────────────────────────────


class TestMissingCollection:
    def test_count_missing_returns_zero(self, store: VectorStore) -> None:
        assert store.count("does_not_exist") == 0

    def test_count_where_missing_returns_zero(self, store: VectorStore) -> None:
        assert store.count_where("nope", {"k": "v"}) == 0

    def test_delete_where_missing_no_error(self, store: VectorStore) -> None:
        store.delete_where("nope", {"k": "v"})

    def test_get_collection_metadata_missing(self, store: VectorStore) -> None:
        assert store.get_collection_metadata("nope") is None

    def test_iter_metadatas_missing_empty(self, store: VectorStore) -> None:
        assert list(store.iter_metadatas("nope")) == []

    def test_iter_documents_missing_empty(self, store: VectorStore) -> None:
        assert list(store.iter_documents("nope")) == []

    def test_query_dense_missing_empty(self, store: VectorStore) -> None:
        assert store.query_dense("nope", [0.0] * 384, 5) == []
