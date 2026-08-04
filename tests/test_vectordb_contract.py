"""Integration test exercising every VectorStore ABC method.

Verifies the contract documented in ``core/vectordb/base.py`` against
the ChromaDB implementation.  Uses the in-memory EphemeralClient
monkeypatched by ``conftest._patch_chromadb`` so no disk I/O occurs.

The test covers every operation enumerated in Phase 3 task 1.3:
collection creation, document write (upsert), dense query with metadata
filter, paged metadata/document reads, count + count-by-filter, delete
by filter, delete collection, list collections, collection metadata
read/update, and generation bumping.
"""

from __future__ import annotations

import pytest

from rag_mcp.core.vectordb.base import VectorStore
from rag_mcp.core.vectordb.chroma import ChromaVectorStore


@pytest.fixture
def store() -> VectorStore:
    """Return a fresh ChromaVectorStore for each test."""
    return ChromaVectorStore()


# ── ABC compliance ────────────────────────────────────────────────────


class TestABCCompliance:
    """The ChromaDB implementation must satisfy the ABC contract."""

    def test_chroma_is_vector_store(self, store: VectorStore) -> None:
        """ChromaVectorStore must be a VectorStore instance."""
        assert isinstance(store, VectorStore)

    def test_all_abstract_methods_implemented(self) -> None:
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
        implemented = set(ChromaVectorStore.__abstractmethods__)
        assert implemented == set(), (
            f"Unimplemented abstract methods: {implemented}"
        )
        # Verify the ABC actually declares the expected surface.
        abc_methods = {
            name for name in dir(VectorStore) if callable(getattr(VectorStore, name))
        }
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


# ── Paged reads ───────────────────────────────────────────────────────


class TestPagedReads:
    def test_iter_metadatas(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        nodes = [
            TextNode(text=f"chunk {i}", metadata={"file_path": f"f{i}.txt"})
            for i in range(5)
        ]
        store.write_nodes(nodes, "paged")

        metadatas = list(store.iter_metadatas("paged"))
        assert len(metadatas) == 5
        assert all(isinstance(m, dict) for m in metadatas)

    def test_iter_metadatas_small_page(self, store: VectorStore) -> None:
        from llama_index.core.schema import TextNode

        nodes = [
            TextNode(text=f"chunk {i}", metadata={"idx": i}) for i in range(5)
        ]
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

        store.write_nodes(
            [TextNode(text="a"), TextNode(text="b")], "counted"
        )
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

    def test_generations_are_per_collection(self, store: VectorStore) -> None:
        store.bump_generation("a")
        store.bump_generation("a")
        store.bump_generation("b")
        assert store.get_generation("a") == 2
        assert store.get_generation("b") == 1
