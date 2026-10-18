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
from pydantic import Field

from omrg.core.vectordb.base import VectorStore
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb.store import LanceVectorStore

_CHROMA_EXTRA = find_spec("chromadb") is not None

# Provider/model diagnostic every direct precomputed caller must supply
# (spec: "Direct precomputed write supplies its diagnostic").
DIAGNOSTIC = EmbeddingIdentity(provider="test-provider", model="test-model")


def _store_class(backend: str) -> type[VectorStore]:
    """Resolve the concrete class lazily (chromadb may be absent)."""
    if backend == "lancedb":
        return LanceVectorStore
    from omrg.core.vectordb.chroma.store import ChromaVectorStore

    return ChromaVectorStore


@pytest.fixture(params=["chroma", "lancedb"])
def store(request: pytest.FixtureRequest, tmp_path) -> VectorStore:
    """Return a fresh store per backend (conventions from the contract suite)."""
    if request.param == "chroma":
        # Reason deliberately differs from the tripwire's guarded string:
        # only these parametrised cases are Chroma-gated, not the file.
        pytest.importorskip(
            "chromadb",
            reason="chromadb unavailable; chroma adapter cases run in the chroma-extra CI job",
        )
        return _store_class("chroma")()
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


def _contract_error() -> type[Exception]:
    """Return the shared contract error class (lazy import, see module docstring)."""
    from omrg.core.vectordb.validation import EmbeddingWriteContractError

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
    from omrg.core.vectordb.validation import validate_embedding_batch

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
        _assert_diagnostics(str(excinfo.value), collection="docs", identifiers=["row-1"])

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
        _assert_diagnostics(str(excinfo.value), collection="docs", identifiers=["row-bad"])

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
        _assert_diagnostics(str(excinfo.value), collection="docs", identifiers=["row-bad"])

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
        _assert_diagnostics(message, collection="docs", identifiers=["row-2d", "row-3d"])
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

    def test_absent_collection_returns_none_without_backend_state(self, store: VectorStore) -> None:
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

    def test_invalid_batch_rejected_before_collection_creation(self, store: VectorStore) -> None:
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

    def test_atomicity_mixed_valid_invalid_persists_nothing(self, store: VectorStore) -> None:
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
            _CannedBatchEmbedding(embed_dim=2, batch_vectors=[[1.0, 0.0], [0.0, 1.0]]),
        )
        from omrg.core.ingestion.writer import embed_and_write_async

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
        from omrg.core.ingestion.writer import embed_and_write_async

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
            _CannedBatchEmbedding(embed_dim=2, batch_vectors=[[1.0, 0.0], []]),
        )
        from omrg.core.ingestion.writer import embed_and_write_async

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


async def _replace(store: VectorStore, collection: str, vectors: list[list[float]]):
    from omrg.core.ingestion.replacement import replace_source_nodes_async

    return await replace_source_nodes_async(
        _replacement_nodes(vectors),
        file_path="doc.txt",
        source_id="src_embed_write_contract",
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
        """Spec: Rejected batch does not reach a backend SDK mutation (replace).

        Since the embedding norm guard (guard-embedding-normalisation),
        these shapes are caught one stage EARLIER: an empty vector has
        norm 0.0 and a NaN vector has norm NaN, both outside the unit-norm
        tolerance, so the guard aborts at the attributed embedding stage
        before the store validator ever runs. Rejection before mutation
        and previous-version intactness — the contract's substance — are
        unchanged; the store-level validator still guards direct
        ``upsert_precomputed`` callers (covered above).
        """
        await _replace(store, "replace-safe", [[1.0, 0.0], [0.0, 1.0]])
        generation = store.get_generation("replace-safe")

        from omrg.core.ingestion.replacement import IngestionStageError
        from omrg.core.norm_guard import EmbeddingNormViolationError

        with pytest.raises(IngestionStageError) as excinfo:
            await _replace(store, "replace-safe", bad_vectors)
        assert excinfo.value.stage == "embedding"
        assert isinstance(excinfo.value.__cause__, EmbeddingNormViolationError)
        assert store.count_where("replace-safe", {"file_path": "doc.txt"}) == 2
        assert store.get_generation("replace-safe") == generation


# ── Engine isolation: writes never fall back to the global embedder ──


class _PoisonedGlobalEmbedding(MockEmbedding):
    """Valid ``BaseEmbedding`` whose every embedding call fails.

    Installed on the LlamaIndex global so any code path that embeds
    through ``Settings.embed_model`` raises instead of silently
    producing vectors from the wrong model.
    """

    def _get_query_embedding(self, query: str) -> list[float]:
        raise AssertionError("the LlamaIndex global embedder embedded a query")

    def get_text_embedding_batch(self, texts, **kwargs):  # noqa: ANN001, ARG002
        raise AssertionError("the LlamaIndex global embedder embedded texts")


class TestInjectedEmbedderNeverReadsGlobal:
    """``write_nodes`` with an injected embedder never uses the global.

    The LlamaIndex ``VectorStoreIndex`` constructor resolves
    ``embed_model or Settings.embed_model`` before processing the
    (already embedded) nodes, so the adapter must pass the injected
    model through: omitting it resolves the global even though no
    embedding happens inside the index.
    """

    def test_write_passes_injected_model_to_index(self, store: VectorStore) -> None:
        nodes = [
            TextNode(text="alpha", id_="global-forbidden-1"),
            TextNode(text="beta", id_="global-forbidden-2"),
        ]
        embed = MockEmbedding(embed_dim=8, model_name="injected-write-model")

        from llama_index.core.indices.vector_store.base import VectorStoreIndex

        captured: dict = {}
        real_init = VectorStoreIndex.__init__

        def spy_init(index_self: object, *args: object, **kwargs: object) -> None:
            captured.update(kwargs)
            real_init(index_self, *args, **kwargs)  # type: ignore[arg-type]

        previous = Settings.embed_model
        Settings.embed_model = _PoisonedGlobalEmbedding(embed_dim=8)  # type: ignore[assignment]
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(VectorStoreIndex, "__init__", spy_init)
                store.write_nodes(nodes, "global_forbidden", embed_model=embed)
        finally:
            Settings.embed_model = previous

        # Decisive: the adapter passed the injected model to the index
        # constructor, so the global-resolution branch never runs.
        assert captured.get("embed_model") is embed
        assert store.count("global_forbidden") == 2

    def test_close_clears_process_local_state(self, store: VectorStore) -> None:
        """Closing drops generation counters; a second close is a no-op."""
        _upsert(store, "close-state", ["row-1"], [[1.0, 0.0]])
        assert store.get_generation("close-state") == 1
        store.close()
        assert store.get_generation("close-state") == 0
        store.close()


# ── ADR-081: a write supplies its own embedding identity ──────────────────

_IDENTITY_A = EmbeddingIdentity(provider="ollama", model="model-a")
_IDENTITY_B = EmbeddingIdentity(provider="ollama", model="model-b")


@pytest.fixture(params=["chroma", "lancedb"])
def identity_store(request: pytest.FixtureRequest, tmp_path) -> VectorStore:
    """Return a store composed with identity A for each backend."""
    if request.param == "chroma":
        pytest.importorskip("chromadb", reason="chroma extra not installed")
        return _store_class("chroma")(embedding_identity=_IDENTITY_A)
    return LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY_A)


def _text_nodes(prefix: str) -> list[BaseNode]:
    return [TextNode(text="alpha", id_=f"{prefix}-1"), TextNode(text="beta", id_=f"{prefix}-2")]


class TestWriteSuppliesEmbeddingIdentity:
    """``write_nodes(..., embedding_identity=B)`` replaces the composed identity A."""

    def test_new_collection_is_stamped_with_the_supplied_identity(
        self, identity_store: VectorStore
    ) -> None:
        embed = MockEmbedding(embed_dim=8, model_name="model-b")
        identity_store.write_nodes(
            _text_nodes("new"), "supplied", embed_model=embed, embedding_identity=_IDENTITY_B
        )
        metadata = identity_store.get_collection_metadata("supplied") or {}
        assert metadata["rag_embed_model"] == "model-b"
        assert metadata["rag_embed_provider"] == "ollama"

    def test_supplied_identity_conflicting_with_the_stamp_fails_before_mutation(
        self, identity_store: VectorStore
    ) -> None:
        embed = MockEmbedding(embed_dim=8, model_name="model-a")
        identity_store.write_nodes(_text_nodes("a"), "stamped-a", embed_model=embed)
        generation = identity_store.get_generation("stamped-a")
        with pytest.raises(ValueError, match="model-b"):
            identity_store.write_nodes(
                _text_nodes("b"), "stamped-a", embed_model=embed, embedding_identity=_IDENTITY_B
            )
        assert identity_store.count("stamped-a") == 2
        assert identity_store.get_generation("stamped-a") == generation

    def test_without_a_supplied_identity_the_composed_rule_still_applies(
        self, identity_store: VectorStore
    ) -> None:
        embed = MockEmbedding(embed_dim=8, model_name="model-b")
        identity_store.write_nodes(
            _text_nodes("b"), "stamped-b", embed_model=embed, embedding_identity=_IDENTITY_B
        )
        with pytest.raises(ValueError, match="model-a"):
            identity_store.write_nodes(_text_nodes("a"), "stamped-b", embed_model=embed)
        assert identity_store.count("stamped-b") == 2

    def test_malformed_vector_diagnostic_names_the_supplied_model(
        self, identity_store: VectorStore
    ) -> None:
        embed = _CannedBatchEmbedding(embed_dim=8, model_name="model-b", batch_vectors=[[]])
        with pytest.raises(_contract_error()) as excinfo:
            identity_store.write_nodes(
                [TextNode(text="x", id_="bad-1")],
                "diag",
                embed_model=embed,
                embedding_identity=_IDENTITY_B,
            )
        assert "model-b" in str(excinfo.value)
        assert "model-a" not in str(excinfo.value)


# ── The model stamp is checked before embedding and shape validation ──────


class _CountingEmbedding(MockEmbedding):
    """``MockEmbedding`` that records every text batch it is asked to embed."""

    seen: list[list[str]] = Field(default_factory=list)

    def get_text_embedding_batch(self, texts, **kwargs):  # noqa: ANN001
        self.seen.append(list(texts))
        return super().get_text_embedding_batch(texts, **kwargs)


def _stamp_collection_a(store: VectorStore, name: str) -> None:
    """Stamp *name* with identity A using 16-dimension vectors."""
    embed = MockEmbedding(embed_dim=16, model_name="model-a")
    store.write_nodes(_text_nodes(f"{name}-seed"), name, embed_model=embed)


class TestStampCheckedBeforeEmbedding:
    """A wrong-model write names both models and costs no embedding call."""

    @pytest.mark.parametrize("dim_b", [8, 16], ids=["other-size", "same-size"])
    def test_wrong_model_is_refused_before_embedding(
        self, identity_store: VectorStore, dim_b: int
    ) -> None:
        _stamp_collection_a(identity_store, "stamped")
        generation = identity_store.get_generation("stamped")
        embed_b = _CountingEmbedding(embed_dim=dim_b, model_name="model-b")
        with pytest.raises(ValueError) as excinfo:
            identity_store.write_nodes(
                _text_nodes("b"), "stamped", embed_model=embed_b, embedding_identity=_IDENTITY_B
            )
        message = str(excinfo.value)
        assert "model-a" in message
        assert "model-b" in message
        assert "Invalid embedding batch" not in message
        assert embed_b.seen == []
        assert identity_store.count("stamped") == 2
        assert identity_store.get_generation("stamped") == generation

    def test_legacy_collection_is_stamped_after_the_write(self, tmp_path) -> None:
        legacy = LanceVectorStore(uri=str(tmp_path / "legacy"))
        embed = MockEmbedding(embed_dim=8, model_name="model-b")
        legacy.write_nodes(_text_nodes("old"), "legacy", embed_model=embed)
        assert "rag_embed_model" not in (legacy.get_collection_metadata("legacy") or {})
        legacy.write_nodes(
            _text_nodes("new"), "legacy", embed_model=embed, embedding_identity=_IDENTITY_B
        )
        assert (legacy.get_collection_metadata("legacy") or {})["rag_embed_model"] == "model-b"

    def test_absent_collection_is_embedded_and_not_created_by_the_check(
        self, identity_store: VectorStore
    ) -> None:
        identity_store.check_embedding_identity("absent", _IDENTITY_B)
        assert not identity_store.collection_exists("absent")
        embed = _CountingEmbedding(embed_dim=8, model_name="model-b")
        identity_store.write_nodes(
            _text_nodes("n"), "absent", embed_model=embed, embedding_identity=_IDENTITY_B
        )
        assert ["alpha", "beta"] in embed.seen

    def test_matching_stamp_writes(self, identity_store: VectorStore) -> None:
        _stamp_collection_a(identity_store, "match")
        embed = MockEmbedding(embed_dim=16, model_name="model-a")
        identity_store.write_nodes(_text_nodes("again"), "match", embed_model=embed)
        assert identity_store.count("match") == 4

    def test_check_changes_nothing(self, identity_store: VectorStore) -> None:
        _stamp_collection_a(identity_store, "readonly")
        generation = identity_store.get_generation("readonly")
        metadata = identity_store.get_collection_metadata("readonly")
        with pytest.raises(ValueError, match="model-b"):
            identity_store.check_embedding_identity("readonly", _IDENTITY_B)
        identity_store.check_embedding_identity("readonly", _IDENTITY_A)
        assert identity_store.get_generation("readonly") == generation
        assert identity_store.get_collection_metadata("readonly") == metadata
