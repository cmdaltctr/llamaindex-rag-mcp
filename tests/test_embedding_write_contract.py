"""Red-first contract tests for the embedding write contract.

Pins ``openspec/changes/validate-embedding-write-contract`` (tasks 1.1-1.4)
before the implementation exists:

- ``core/vectordb/validation.py`` exposes one shared structural validator
  (``validate_embedding_batch`` raising ``EmbeddingWriteContractError``)
  that every production write path invokes before any backend SDK or
  persistent-store mutation.
- ``VectorStore.get_collection_dimension`` returns an established
  collection vector dimension, or ``None`` before a vector schema exists,
  without creating backend state.
- ``upsert_precomputed(..., embedding_identity=...)`` requires direct
  callers to supply the provider/model diagnostic explicitly.

Backend coverage mirrors ``tests/test_vectordb_contract.py``: the chroma
parameters skip when the optional extra is absent (they run in the
chroma-extra CI job) and lancedb always runs on an isolated tmp-path
database. The suite stays out of the ``slow`` mark, matching the
existing contract suite.

The new validator module is imported inside helpers rather than at module
level so the red run reports every scenario individually instead of a
single collection error. Once the module lands this is behaviourally
identical to a module-level import.
"""

from __future__ import annotations

import re
from importlib.util import find_spec

import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import BaseNode, TextNode

from rag_mcp.core.vectordb.base import VectorStore
from rag_mcp.core.vectordb.identity import EmbeddingIdentity
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_CHROMA_EXTRA = find_spec("chromadb") is not None

# Provider/model diagnostic every direct precomputed caller must supply
# (spec: "Direct precomputed write supplies its diagnostic").
DIAGNOSTIC = EmbeddingIdentity(provider="test-provider", model="test-model")


def _store_class(backend: str) -> type[VectorStore]:
    """Resolve the concrete class lazily (chromadb may be absent)."""
    if backend == "lancedb":
        return LanceVectorStore
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore

    return ChromaVectorStore


@pytest.fixture(params=["chroma", "lancedb"])
def store(request: pytest.FixtureRequest, tmp_path) -> VectorStore:
    """Return a fresh store per backend (conventions from the contract suite)."""
    if request.param == "chroma":
        pytest.importorskip(
            "chromadb",
            reason="chroma extra not installed; runs in the chroma-extra CI job",
        )
        return _store_class("chroma")()
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


def _contract_error() -> type[Exception]:
    """Return the shared contract error class (lazy import, see module docstring)."""
    from rag_mcp.core.vectordb.validation import EmbeddingWriteContractError

    return EmbeddingWriteContractError


def _validate(
    identifiers: list[str],
    vectors: list[list[float]],
    *,
    collection_name: str = "docs",
    embedding_identity: EmbeddingIdentity = DIAGNOSTIC,
    existing_dimension: int | None = None,
) -> None:
    """Invoke the shared structural validator (lazy import, see module docstring)."""
    from rag_mcp.core.vectordb.validation import validate_embedding_batch

    validate_embedding_batch(
        identifiers,
        vectors,
        collection_name=collection_name,
        embedding_identity=embedding_identity,
        existing_dimension=existing_dimension,
    )


def _assert_diagnostics(
    message: str,
    *,
    collection: str,
    identity: EmbeddingIdentity = DIAGNOSTIC,
    identifiers: list[str] | None = None,
) -> None:
    """Task 1.2: every failure names collection, provider/model, and affected IDs."""
    assert collection in message
    assert identity.provider in message
    assert identity.model in message
    for identifier in identifiers or []:
        assert identifier in message


def _upsert(
    store: VectorStore,
    collection: str,
    ids: list[str],
    vectors: list[list[float]],
    identity: EmbeddingIdentity | None = DIAGNOSTIC,
) -> None:
    """Submit one precomputed batch with an explicit provider/model diagnostic."""
    kwargs: dict = {}
    if identity is not None:
        kwargs["embedding_identity"] = identity
    store.upsert_precomputed(
        collection,
        ids=ids,
        documents=[f"doc-{index}" for index in range(len(ids))],
        metadatas=[{"row": index} for index in range(len(ids))],
        embeddings=[list(vector) for vector in vectors],
        **kwargs,
    )


class _CannedBatchEmbedding(MockEmbedding):
    """MockEmbedding whose batch output is replaced with canned vectors.

    Simulates the Experiment 14 failure mode: a provider returning
    structurally malformed vectors (empty, non-numeric) for normal text.
    """

    # Deliberately untyped: canned vectors include malformed shapes
    # (non-numeric elements) that the validator — not pydantic — must
    # reject at write time.
    batch_vectors: list

    def get_text_embedding_batch(self, texts, **kwargs):  # noqa: ANN001, ARG002
        return [list(vector) for vector in self.batch_vectors]


# ── Task 1.1 + 1.2: the shared validator rule set ────────────────────


class TestSharedValidator:
    """The pure validator rule set and its diagnostics (no store involved)."""

    def test_valid_batch_passes(self) -> None:
        """Spec: Valid batch reaches a vector store."""
        _validate(["row-1", "row-2"], [[1.0, 0.0], [0.0, 1.0]])
        _validate(["row-1"], [[1.0, 0.0]], existing_dimension=2)

    def test_empty_batch_rejected(self) -> None:
        """Spec: Empty embedding batch is rejected."""
        for identifiers, vectors in (([], []), (["row-1"], []), ([], [[1.0, 2.0]])):
            with pytest.raises(_contract_error()) as excinfo:
                _validate(identifiers, vectors, collection_name="docs")
            _assert_diagnostics(str(excinfo.value), collection="docs")

    def test_cardinality_mismatch_missing_vectors_rejected(self) -> None:
        """Spec: cardinality mismatch — fewer vectors than identifiers."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-1", "row-2", "row-3"],
                [[1.0, 0.0], [0.0, 1.0]],
                collection_name="docs",
            )
        _assert_diagnostics(
            str(excinfo.value),
            collection="docs",
            identifiers=["row-1", "row-2", "row-3"],
        )

    def test_cardinality_mismatch_surplus_vectors_rejected(self) -> None:
        """Spec: cardinality mismatch — more vectors than identifiers."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(["row-1"], [[1.0, 0.0], [0.0, 1.0]], collection_name="docs")
        _assert_diagnostics(
            str(excinfo.value), collection="docs", identifiers=["row-1"]
        )

    def test_empty_vector_rejected_naming_each_affected_identifier(self) -> None:
        """Spec: Empty vector from an embedding provider (each affected ID named)."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-ok", "row-empty-1", "row-empty-2"],
                [[1.0, 0.0], [], []],
                collection_name="docs",
            )
        _assert_diagnostics(
            str(excinfo.value),
            collection="docs",
            identifiers=["row-empty-1", "row-empty-2"],
        )

    def test_non_numeric_element_rejected(self) -> None:
        """Spec: Non-numeric vector value."""
        malformed: list = [1.0, "not-a-number"]
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-ok", "row-bad"],
                [[1.0, 0.0], malformed],
                collection_name="docs",
            )
        _assert_diagnostics(
            str(excinfo.value), collection="docs", identifiers=["row-bad"]
        )

    @pytest.mark.parametrize(
        "bad_value",
        [float("nan"), float("inf"), float("-inf")],
        ids=["nan", "inf", "neg-inf"],
    )
    def test_non_finite_value_rejected(self, bad_value: float) -> None:
        """Spec: NaN or infinity in a candidate vector."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-ok", "row-bad"],
                [[1.0, 0.0], [bad_value, 1.0]],
                collection_name="docs",
            )
        _assert_diagnostics(
            str(excinfo.value), collection="docs", identifiers=["row-bad"]
        )

    @pytest.mark.parametrize("position", [1, 2])
    def test_non_finite_error_names_batch_position(self, position: int) -> None:
        """Spec: the error identifies the vector's position within the batch."""
        vectors = [[1.0, 0.0]] * 3
        vectors[position] = [float("nan"), 1.0]
        with pytest.raises(_contract_error()) as excinfo:
            _validate(["row-0", "row-1", "row-2"], vectors, collection_name="docs")
        message = str(excinfo.value)
        _assert_diagnostics(message, collection="docs", identifiers=[f"row-{position}"])
        assert re.search(rf"(?i)(index|position|#)\s*#?\s*{position}\b", message)

    def test_mixed_dimensions_rejected_naming_observed_dimensions(self) -> None:
        """Spec: Mixed dimensions in one batch (observed dimensions named)."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-2d", "row-3d"],
                [[1.0, 0.0], [1.0, 2.0, 3.0]],
                collection_name="docs",
            )
        message = str(excinfo.value)
        _assert_diagnostics(
            message, collection="docs", identifiers=["row-2d", "row-3d"]
        )
        assert re.search(r"(?<!\d)2(?!\d)", message)
        assert re.search(r"(?<!\d)3(?!\d)", message)

    def test_existing_dimension_conflict_rejected_naming_both_dimensions(self) -> None:
        """Spec: Existing collection dimension conflicts (both dimensions named)."""
        with pytest.raises(_contract_error()) as excinfo:
            _validate(
                ["row-new"],
                [[1.0, 2.0, 3.0]],
                collection_name="docs",
                existing_dimension=384,
            )
        message = str(excinfo.value)
        _assert_diagnostics(message, collection="docs", identifiers=["row-new"])
        assert re.search(r"(?<!\d)384(?!\d)", message)
        assert re.search(r"(?<!\d)3(?!\d)", message)


# ── Task 2.2 surface: read-only existing-dimension discovery ─────────


class TestDimensionDiscovery:
    """The contract capability the existing-dimension rule depends on."""

    def test_absent_collection_returns_none_without_backend_state(
        self, store: VectorStore
    ) -> None:
        """Discovery on an absent collection returns None and creates nothing."""
        assert store.get_collection_dimension("never-created") is None
        assert store.collection_exists("never-created") is False
        assert store.count("never-created") == 0

    def test_dimension_returned_after_write(self, store: VectorStore) -> None:
        """An established schema exposes its vector dimension."""
        _upsert(store, "dimcheck", ["row-1"], [[1.0, 2.0]])
        assert store.get_collection_dimension("dimcheck") == 2


# ── Task 1.4 (direct path): precomputed writes on both backends ──────


class TestDirectPrecomputedWrites:
    """Direct ``upsert_precomputed`` calls with an explicit diagnostic."""

    def test_valid_precomputed_batch_persists(self, store: VectorStore) -> None:
        """Spec: valid precomputed vectors persist through the selected adapter."""
        _upsert(store, "direct-ok", ["row-1", "row-2"], [[1.0, 0.0], [0.0, 1.0]])
        assert store.count("direct-ok") == 2
        assert store.get_generation("direct-ok") == 1

    def test_missing_explicit_diagnostic_is_rejected(self, store: VectorStore) -> None:
        """Spec: Direct precomputed write supplies its diagnostic."""
        with pytest.raises(TypeError):
            store.upsert_precomputed(
                "direct-diag",
                ids=["row-1"],
                documents=["doc-0"],
                metadatas=[{"row": 0}],
                embeddings=[[1.0, 0.0]],
            )
        assert store.collection_exists("direct-diag") is False

    def test_invalid_batch_rejected_before_collection_creation(
        self, store: VectorStore
    ) -> None:
        """Spec: Rejected batch does not reach a backend SDK mutation (fresh)."""
        with pytest.raises(_contract_error()):
            _upsert(
                store,
                "direct-fresh",
                ["row-ok", "row-bad"],
                [[1.0, 0.0], [float("nan"), 1.0]],
            )
        assert store.collection_exists("direct-fresh") is False
        assert store.count("direct-fresh") == 0
        assert store.get_generation("direct-fresh") == 0

    def test_invalid_batch_rejected_leaves_existing_collection_unchanged(
        self, store: VectorStore
    ) -> None:
        """Spec: Rejected batch does not reach a backend SDK mutation (existing)."""
        _upsert(store, "direct-existing", ["row-old"], [[1.0, 0.0]])
        generation = store.get_generation("direct-existing")

        with pytest.raises(_contract_error()) as excinfo:
            _upsert(
                store,
                "direct-existing",
                ["row-old2", "row-bad"],
                [[1.0, 0.0], []],
            )
        _assert_diagnostics(
            str(excinfo.value),
            collection="direct-existing",
            identifiers=["row-bad"],
        )
        assert store.count("direct-existing") == 1
        assert store.get_generation("direct-existing") == generation

    def test_existing_dimension_conflict_rejected_before_adapter_write(
        self, store: VectorStore
    ) -> None:
        """Spec: Existing collection dimension conflicts (adapter path)."""
        _upsert(store, "direct-dimconflict", ["row-old"], [[1.0, 0.0]])
        assert store.get_collection_dimension("direct-dimconflict") == 2
        generation = store.get_generation("direct-dimconflict")

        with pytest.raises(_contract_error()) as excinfo:
            _upsert(store, "direct-dimconflict", ["row-new"], [[1.0, 2.0, 3.0]])
        message = str(excinfo.value)
        assert re.search(r"(?<!\d)2(?!\d)", message)
        assert re.search(r"(?<!\d)3(?!\d)", message)
        assert store.count("direct-dimconflict") == 1
        assert store.get_generation("direct-dimconflict") == generation

    def test_atomicity_mixed_valid_invalid_persists_nothing(
        self, store: VectorStore
    ) -> None:
        """Spec: Valid and invalid candidates share a batch (task 1.3)."""
        with pytest.raises(_contract_error()):
            _upsert(
                store,
                "atomic-direct",
                ["row-good", "row-bad"],
                [[1.0, 0.0], [1.0, "bad"]],  # type: ignore[list-item]
            )
        assert store.count("atomic-direct") == 0
        assert store.get_generation("atomic-direct") == 0
        assert store.collection_exists("atomic-direct") is False


# ── Task 1.4 (ingestion path): write_nodes-produced embeddings ───────


class TestIngestionWritePath:
    """``embed_and_write_async`` reaches ``write_nodes`` with provider output."""

    async def test_valid_ingestion_persists_and_bumps_generation_once(
        self, store: VectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Control: the contract must keep normal ingestion green."""
        monkeypatch.setattr(
            Settings,
            "embed_model",
            _CannedBatchEmbedding(
                embed_dim=2, batch_vectors=[[1.0, 0.0], [0.0, 1.0]]
            ),
        )
        from rag_mcp.core.ingestion.writer import embed_and_write_async

        written = await embed_and_write_async(
            [TextNode(text="one"), TextNode(text="two")],
            collection_name="ingest-ok",
            store=store,
        )
        assert written == 2
        assert store.count("ingest-ok") == 2
        assert store.get_generation("ingest-ok") == 1

    @pytest.mark.parametrize(
        "vectors",
        [[[], []], [[1.0, "x"], [0.5, 0.5]]],
        ids=["empty", "non-numeric"],
    )
    async def test_malformed_provider_vectors_rejected(
        self,
        store: VectorStore,
        monkeypatch: pytest.MonkeyPatch,
        vectors: list[list[float]],
    ) -> None:
        """Spec: Empty vector / Non-numeric via ingestion (Experiment 14 mode)."""
        monkeypatch.setattr(
            Settings,
            "embed_model",
            _CannedBatchEmbedding(embed_dim=2, batch_vectors=vectors),
        )
        from rag_mcp.core.ingestion.writer import embed_and_write_async

        with pytest.raises(_contract_error()):
            await embed_and_write_async(
                [TextNode(text="one"), TextNode(text="two")],
                collection_name="ingest-bad",
                store=store,
            )
        assert store.collection_exists("ingest-bad") is False
        assert store.count("ingest-bad") == 0
        assert store.get_generation("ingest-bad") == 0

    async def test_mixed_valid_invalid_batch_atomic(
        self, store: VectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec: Valid and invalid candidates share a batch (ingestion path)."""
        monkeypatch.setattr(
            Settings,
            "embed_model",
            _CannedBatchEmbedding(
                embed_dim=2, batch_vectors=[[1.0, 0.0], []]
            ),
        )
        from rag_mcp.core.ingestion.writer import embed_and_write_async

        with pytest.raises(_contract_error()):
            await embed_and_write_async(
                [TextNode(text="good"), TextNode(text="bad")],
                collection_name="ingest-mixed",
                store=store,
            )
        assert store.count("ingest-mixed") == 0
        assert store.get_generation("ingest-mixed") == 0


# ── Task 1.4 (replacement path): failure-safe source replacement ─────


def _replacement_nodes(vectors: list[list[float]]) -> list[BaseNode]:
    """Pre-embed nodes so replacement skips the (mocked) provider."""
    nodes: list[BaseNode] = []
    for index, vector in enumerate(vectors):
        node = TextNode(text=f"chunk {index}", metadata={"file_path": "doc.txt"})
        node.embedding = list(vector)
        nodes.append(node)
    return nodes


async def _replace(
    store: VectorStore, collection: str, vectors: list[list[float]]
):
    from rag_mcp.core.ingestion.replacement import replace_source_nodes_async

    return await replace_source_nodes_async(
        _replacement_nodes(vectors),
        file_path="doc.txt",
        content_hash="a" * 64,
        index_identity="index-identity",
        source_version="source-version",
        collection_name=collection,
        store=store,
    )


class TestReplacementWritePath:
    """Failure-safe replacement must reject malformed vectors before mutation."""

    async def test_valid_replacement_persists(self, store: VectorStore) -> None:
        """Control: the contract must keep failure-safe replacement green."""
        outcome = await _replace(store, "replace-ok", [[1.0, 0.0], [0.0, 1.0]])
        assert outcome.chunks_written == 2
        assert store.count_where("replace-ok", {"file_path": "doc.txt"}) == 2
        assert store.get_generation("replace-ok") == 1

    @pytest.mark.parametrize(
        "bad_vectors",
        [[[1.0, 0.0], []], [[1.0, 0.0], [float("nan"), 1.0]]],
        ids=["empty", "nan"],
    )
    async def test_malformed_replacement_rejected_and_previous_version_intact(
        self, store: VectorStore, bad_vectors: list[list[float]]
    ) -> None:
        """Spec: Rejected batch does not reach a backend SDK mutation (replace)."""
        await _replace(store, "replace-safe", [[1.0, 0.0], [0.0, 1.0]])
        generation = store.get_generation("replace-safe")

        from rag_mcp.core.ingestion.replacement import IngestionStageError

        with pytest.raises(IngestionStageError) as excinfo:
            await _replace(store, "replace-safe", bad_vectors)
        assert excinfo.value.stage == "store_write"
        assert isinstance(excinfo.value.__cause__, _contract_error())
        assert "replace-safe" in str(excinfo.value.__cause__)
        assert store.count_where("replace-safe", {"file_path": "doc.txt"}) == 2
        assert store.get_generation("replace-safe") == generation
