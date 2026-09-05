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
from importlib.util import find_spec
from pathlib import Path

import pytest

from omrg.core.vectordb.base import VectorStore
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.core.vectordb.paged import PagedReadMixin

# Task 5.1: the ChromaDB adapter import is lazy so this shared contract
# module collects (and runs every LanceDB parameter) in the base install
# without the optional chroma extra. The chroma parameters skip by design
# with a named reason and run in the chroma-extra CI job.
_CHROMA_EXTRA = find_spec("chromadb") is not None
_PRECOMPUTED_IDENTITY = EmbeddingIdentity(provider="test", model="mock")


def _store_class(backend: str) -> type[VectorStore]:
    """Resolve the concrete class lazily (chromadb may be absent)."""
    if backend == "lancedb":
        return LanceVectorStore
    from omrg.core.vectordb.chroma import ChromaVectorStore

    return ChromaVectorStore


@pytest.fixture(params=["chroma", "lancedb"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> VectorStore:
    """Return a fresh store for each backend under test.

    ``chroma`` relies on the in-memory EphemeralClient monkeypatched by
    ``conftest._patch_chromadb`` so no disk I/O occurs; it skips when the
    optional chroma extra is absent (task 5.1). ``lancedb``
    points at an isolated database under ``tmp_path``, giving each test
    a clean on-disk store; the embedded LanceDB writer is fast enough
    to stay out of the ``slow`` mark.
    """
    if request.param == "chroma":
        pytest.importorskip(
            "chromadb",
            reason="chroma extra not installed; runs in the chroma-extra CI job",
        )
        return _store_class("chroma")()
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
        if backend == "chroma" and not _CHROMA_EXTRA:
            pytest.skip(
                "chroma extra not installed (uv sync --extra chroma); "
                "runs in the chroma-extra CI job"
            )
        abstract_methods = {
            "create_collection",
            "collection_exists",
            "delete_collection",
            "list_collections",
            "write_nodes",
            "query_dense",
            "iter_metadatas",
            "iter_documents",
            "iter_filtered_documents",
            "count",
            "count_where",
            "delete_where",
            "get_collection_metadata",
            "update_collection_metadata",
            "bump_generation",
            "get_generation",
            "get_data_version",
        }
        implemented = set(_store_class(backend).__abstractmethods__)
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
            embedding_identity=_PRECOMPUTED_IDENTITY,
        )

        rows = store.query_dense("semantic_scores", [1.0, 0.0], n_results=3)

        assert [row["id"] for row in rows] == ["exact", "near", "far"]
        assert all(row["score_kind"] == "dense_similarity_v1" for row in rows)
        scores = [row["score"] for row in rows]
        assert scores[0] == pytest.approx(1.0)
        assert all(0.0 < score <= 1.0 for score in scores)
        assert scores == sorted(scores, reverse=True)

    def test_native_squared_l2_is_rooted_before_canonical_score(self, store: VectorStore) -> None:
        """A native squared distance of 4 must score 1/(1+sqrt(4)) = 1/3.

        ChromaDB and LanceDB report *squared* L2 for their l2 metric.
        The canonical ``dense_similarity_v1`` contract consumes the true
        distance, so each adapter roots the native value before the
        ``1 / (1 + d)`` transform while ``native_distance`` keeps the
        raw squared value for diagnostics.
        """
        store.upsert_precomputed(
            "squared_l2_probe",
            ids=["two_away"],
            documents=["two units away"],
            metadatas=[{"rank": 1}],
            embeddings=[[2.0, 0.0]],
            embedding_identity=_PRECOMPUTED_IDENTITY,
        )

        rows = store.query_dense("squared_l2_probe", [0.0, 0.0], n_results=1)

        assert len(rows) == 1
        # Native field stays the raw squared distance: (2-0)**2 = 4.
        assert rows[0]["native_distance"] == pytest.approx(4.0)
        # Canonical score uses the rooted distance: 1/(1+sqrt(4)) = 1/3.
        assert rows[0]["score"] == pytest.approx(1.0 / 3.0)

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
        if not _CHROMA_EXTRA:
            pytest.skip("chroma extra not installed; runs in the chroma-extra CI job")
        store = _store_class("chroma")()
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
            embedding_identity=_PRECOMPUTED_IDENTITY,
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

        from omrg.core.ingestion.source_state import (
            build_source_id,
            stamp_source_lineage,
        )
        from omrg.core.ingestion.writer import embed_and_write_async, remove_document

        name = "pipeline_exactly_once"
        # remove_document deletes by the derived source_id, so the seeded
        # row must carry production lineage like a real pipeline write.
        source_path = "/virtual/pipeline.txt"
        node = TextNode(text="pipeline row", metadata={"file_path": source_path})
        stamp_source_lineage(
            [node],
            file_path=source_path,
            source_id=build_source_id(source_path),
            content_hash="c" * 64,
            index_identity="i" * 64,
            source_version="v" * 64,
            source_attempt="attempt",
        )
        written = await embed_and_write_async(
            [node],
            collection_name=name,
            store=store,
            embed_concurrency=1,
        )
        assert written == 1
        assert store.get_generation(name) == 1

        result = remove_document(source_path, collection_name=name, store=store)
        assert result["status"] == "ok"
        assert result["chunks_removed"] == 1
        assert store.get_generation(name) == 2

    def test_generations_are_per_collection(self, store: VectorStore) -> None:
        store.bump_generation("a")
        store.bump_generation("a")
        store.bump_generation("b")
        assert store.get_generation("a") == 2
        assert store.get_generation("b") == 1


# ── Durable data version (fix-retrieval-freshness stage 2) ────────────


class TestDataVersionCapability:
    """Differential contract for the durable data-version capability.

    LanceDB returns a tagged ``(omrg_dataset_epoch, table.version)``
    token; ChromaDB has no durable cross-process collection version,
    so it stays on the ABC default and reports ``None`` explicitly
    rather than repackaging the process-local generation counter.
    """

    def test_absent_collection_reports_absence(self, store: VectorStore) -> None:
        assert store.get_data_version("never_created") is None

    def test_stable_between_reads_without_mutation(self, store: VectorStore) -> None:
        store.upsert_precomputed(
            "dv_stable",
            ids=["a"],
            documents=["row"],
            metadatas=[{"k": "v"}],
            embeddings=[[1.0, 0.0]],
            embedding_identity=_PRECOMPUTED_IDENTITY,
        )
        assert store.get_data_version("dv_stable") == store.get_data_version("dv_stable")

    def test_backend_capability_semantics(self, store: VectorStore) -> None:
        """Lance advances a token on mutation; Chroma reports ``None``."""
        store.upsert_precomputed(
            "dv_mutation",
            ids=["a"],
            documents=["row"],
            metadatas=[{"k": "v"}],
            embeddings=[[1.0, 0.0]],
            embedding_identity=_PRECOMPUTED_IDENTITY,
        )
        if isinstance(store, LanceVectorStore):
            before = store.get_data_version("dv_mutation")
            assert before is not None
            assert before.startswith("lancedb-durable-v1:")
            store.upsert_precomputed(
                "dv_mutation",
                ids=["b"],
                documents=["second"],
                metadatas=[{"k": "w"}],
                embeddings=[[1.0, 0.0]],
                embedding_identity=_PRECOMPUTED_IDENTITY,
            )
            assert store.get_data_version("dv_mutation") != before
        else:
            # No durable version available: the capability must be
            # reported unavailable, never the local generation counter.
            assert store.get_data_version("dv_mutation") is None


# ── Filtered row reads (fix-retrieval-freshness stage 2) ─────────────


class TestFilteredDocuments:
    """Differential contract for bounded filtered row reads."""

    @staticmethod
    def _seed(store: VectorStore, collection: str = "filtered_docs") -> None:
        """Write three lineage-tagged rows across two sources."""
        store.upsert_precomputed(
            collection,
            ids=["s1c0", "s1c1", "s2c0"],
            documents=["source one first", "source one second", "source two first"],
            metadatas=[
                {"source_id": "s1", "source_chunk_index": 0, "source_chunk_count": 2},
                {"source_id": "s1", "source_chunk_index": 1, "source_chunk_count": 2},
                {"source_id": "s2", "source_chunk_index": 0, "source_chunk_count": 1},
            ],
            embeddings=[[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
            embedding_identity=_PRECOMPUTED_IDENTITY,
        )

    def test_equality_filter_returns_source_rows_with_lineage(self, store: VectorStore) -> None:
        self._seed(store)
        rows = list(store.iter_filtered_documents("filtered_docs", {"source_id": "s1"}))
        assert sorted(row[0] for row in rows) == ["s1c0", "s1c1"]
        for _row_id, text, metadata in rows:
            assert metadata["source_id"] == "s1"
            assert metadata["source_chunk_count"] == 2
            assert text.startswith("source one")

    def test_compound_equality_filter_ands_keys(self, store: VectorStore) -> None:
        self._seed(store)
        rows = list(
            store.iter_filtered_documents(
                "filtered_docs", {"source_id": "s1", "source_chunk_index": 1}
            )
        )
        assert [row[0] for row in rows] == ["s1c1"]

    def test_absent_collection_yields_nothing(self, store: VectorStore) -> None:
        assert list(store.iter_filtered_documents("nope", {"source_id": "s1"})) == []

    def test_no_matches_yields_nothing(self, store: VectorStore) -> None:
        self._seed(store)
        assert list(store.iter_filtered_documents("filtered_docs", {"source_id": "absent"})) == []

    def test_empty_filter_rejected(self, store: VectorStore) -> None:
        """An empty where must raise, never scan the whole collection."""
        self._seed(store)
        with pytest.raises(ValueError, match="non-empty where"):
            list(store.iter_filtered_documents("filtered_docs", {}))

    def test_filter_is_pushed_into_each_backend(self) -> None:
        """Both adapters must hand the filter to the backend engine.

        Mirrors ``test_lance_query_pins_l2_instead_of_relying_on_default``:
        the pushdown is a structural property, so pin it in the source
        rather than hoping a behavioural test catches a Python-side
        full scan.
        """
        import inspect

        from omrg.core.vectordb.lance_paged import LancePagedReadMixin
        from omrg.core.vectordb.paged import PagedReadMixin

        lance_source = inspect.getsource(LancePagedReadMixin.iter_filtered_documents)
        assert "translate_where" in lance_source
        assert "filter=filter_sql" in lance_source

        chroma_source = inspect.getsource(PagedReadMixin.iter_filtered_documents)
        assert "_chroma_where(where)" in chroma_source
        assert "where=chroma_where" in chroma_source


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


# ── ChromaDB where-clause translation ────────────────────────────────
# CI evidence (PR #80): chromadb rejects multi-key equality dicts
# ("Expected where to have exactly one operator"), so the store-neutral
# filter must be wrapped in {"$and": [...]}. These tests pin the
# translation against a duck-typed collection handle and run in the
# base install — no chromadb required (ADR-049 keeps it quarantined).


class _WhereCapturingCollection:
    """Duck-typed Chroma collection recording the where clause it received."""

    def __init__(self, rows: list[tuple[str, str, dict]]) -> None:
        self._rows = rows
        self.seen_where: list[dict] = []

    def get(self, where: dict, include: list, limit: int, offset: int) -> dict:
        self.seen_where.append(dict(where))
        matched = [
            (row_id, text, meta)
            for row_id, text, meta in self._rows
            if all(meta.get(k) == v for k, v in where.items())
            or (
                "$and" in where
                and all(meta.get(k) == v for clause in where["$and"] for k, v in clause.items())
            )
        ][offset : offset + limit]
        return {
            "ids": [row[0] for row in matched],
            "documents": [row[1] for row in matched],
            "metadatas": [row[2] for row in matched],
        }


class _StubPagedStore(PagedReadMixin):
    """Minimal host satisfying the mixin's supplied-attribute contract."""

    def __init__(self, collection: _WhereCapturingCollection) -> None:
        self._collection = collection

    def _get_collection(self, name: str):  # noqa: ANN202 - duck-typed host
        return self._collection

    def _default_page_size(self) -> int:
        return 100

    def bump_generation(self, name: str) -> None:
        pass


class TestChromaWhereTranslation:
    ROWS = [
        ("c0", "alpha", {"source_id": "s1", "source_chunk_index": 0}),
        ("c1", "beta", {"source_id": "s1", "source_chunk_index": 1}),
        ("c2", "gamma", {"source_id": "s2", "source_chunk_index": 1}),
    ]

    def test_single_key_filter_passes_through_unchanged(self) -> None:
        collection = _WhereCapturingCollection(self.ROWS)
        store = _StubPagedStore(collection)
        rows = list(store.iter_filtered_documents("docs", {"source_id": "s1"}))
        assert collection.seen_where == [{"source_id": "s1"}]
        assert [row[0] for row in rows] == ["c0", "c1"]

    def test_compound_filter_is_wrapped_in_and(self) -> None:
        collection = _WhereCapturingCollection(self.ROWS)
        store = _StubPagedStore(collection)
        rows = list(
            store.iter_filtered_documents("docs", {"source_id": "s1", "source_chunk_index": 1})
        )
        assert collection.seen_where == [{"$and": [{"source_id": "s1"}, {"source_chunk_index": 1}]}]
        assert [row[0] for row in rows] == ["c1"]

    def test_compound_filter_key_order_is_preserved(self) -> None:
        from omrg.core.vectordb.paged import _chroma_where

        where = _chroma_where({"b": 2, "a": 1})
        assert where == {"$and": [{"b": 2}, {"a": 1}]}

    def test_empty_filter_still_rejected(self) -> None:
        store = _StubPagedStore(_WhereCapturingCollection(self.ROWS))
        with pytest.raises(ValueError, match="non-empty where filter"):
            list(store.iter_filtered_documents("docs", {}))
