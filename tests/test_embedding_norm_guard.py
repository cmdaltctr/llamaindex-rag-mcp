"""Red-first tests for the embedding norm guard (guard-embedding-normalisation).

Pins tasks 2.1 (norm helper), 2.3 (ingest boundary), 2.5 (query boundary),
and the configuration scenarios from the ``embedding-norm-guard`` spec:

- ``core/norm_guard.py`` computes L2 norms and applies the boundary policy
  (fail-closed ingest, warn-and-continue query) from injected settings.
- ``core/ingestion/replacement.py`` aborts the file replacement before any
  node write when a stored-bound vector is off-norm, so failure-safe
  ordering keeps the previous version searchable.
- ``core/retrieval/dense.py`` warns once per process per model on an
  off-norm query vector and attaches a ``norm_guard`` diagnostic to each
  result when diagnostics are enabled.

The guard module is imported inside helpers (matching
``test_embedding_write_contract.py``) so the red run reports every scenario
individually instead of one collection error.

Exact-representable floats are used for the inclusive-boundary scenarios:
0.75/1.25 with tolerance 0.25 are binary-exact, so the boundary comparison
is not perturbed by float representation noise.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding

from rag_mcp.core.vectordb.identity import EmbeddingIdentity
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

# ── Helpers ─────────────────────────────────────────────────────────────


def _norm_guard():
    """Import the guard module lazily (red run: module does not exist yet)."""
    from rag_mcp.core import norm_guard

    return norm_guard


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """Reset warn-once state and the query-embedding cache per test."""
    yield
    try:
        from rag_mcp.core import norm_guard

        norm_guard.reset_warned_norm_models()
    except ImportError:
        pass
    from rag_mcp.core.retrieval.dense import _cached_query_embedding

    _cached_query_embedding.cache_clear()


def _vec(norm: float, dim: int = 1) -> list[float]:
    """Return a vector with the requested L2 norm (all mass on axis 0)."""
    return [norm] + [0.0] * (dim - 1)


class _FixedNormEmbedding(MockEmbedding):
    """MockEmbedding whose outputs are replaced with a fixed-norm vector."""

    norm: float

    def _get_vector(self) -> list[float]:
        return _vec(self.norm, self.embed_dim)


# ── Task 2.1: the norm helper ───────────────────────────────────────────


class TestNormHelper:
    """Pure norm computation and tolerance policy (no store involved)."""

    def test_within_tolerance_passes_and_reports_band(self) -> None:
        """Spec: Unit-norm vectors ingest normally; band is observable."""
        guard = _norm_guard()
        band = guard.check_ingest_vectors(
            [_vec(1.0), _vec(1.0 - 1e-7)],
            model_name="qwen3-embedding:0.6b",
            tolerance=0.001,
        )
        assert band is not None
        assert band[0] <= band[1]
        assert math.isclose(band[0], 1.0 - 1e-7, abs_tol=1e-9)
        assert math.isclose(band[1], 1.0, abs_tol=1e-9)

    @pytest.mark.parametrize("bad_norm", [0.7, 1.4])
    def test_off_norm_rejected_with_actionable_error(self, bad_norm: float) -> None:
        """Spec: norm 0.7 or 1.4 aborts; error names model/norm/tolerance/setting."""
        guard = _norm_guard()
        with pytest.raises(guard.EmbeddingNormViolationError) as excinfo:
            guard.check_ingest_vectors(
                [_vec(1.0), _vec(bad_norm)],
                model_name="qwen3-embedding:0.6b",
                tolerance=0.001,
            )
        message = str(excinfo.value)
        assert "qwen3-embedding:0.6b" in message
        assert f"{bad_norm:.6f}" in message
        assert "0.001" in message
        assert "EMBEDDING__NORM_TOLERANCE" in message

    def test_tolerance_boundary_is_inclusive(self) -> None:
        """Spec: |norm - 1.0| == tolerance is a pass, not a violation.

        0.75/1.25 with tolerance 0.25 are binary-exact, so the comparison
        is exact rather than representation-noise dependent.
        """
        guard = _norm_guard()
        for boundary_norm in (0.75, 1.25):
            band = guard.check_ingest_vectors(
                [_vec(boundary_norm)],
                model_name="m",
                tolerance=0.25,
            )
            assert band is not None

    def test_empty_vector_rejected(self) -> None:
        """An empty vector has norm 0.0 and must fail closed."""
        guard = _norm_guard()
        with pytest.raises(guard.EmbeddingNormViolationError):
            guard.check_ingest_vectors([[]], model_name="m", tolerance=0.001)

    def test_nan_vector_rejected_even_among_clean_neighbours(self) -> None:
        """NaN never wins a deviation comparison; the guard must still reject.

        Regression pin: the first implementation tracked only the worst
        finite deviation, and ``nan > deviation`` is always False, so a
        NaN vector slipped through when a clean neighbour preceded it.
        """
        guard = _norm_guard()
        with pytest.raises(guard.EmbeddingNormViolationError) as excinfo:
            guard.check_ingest_vectors(
                [[1.0, 0.0], [float("nan"), 1.0]],
                model_name="m",
                tolerance=0.001,
            )
        assert "nan" in str(excinfo.value)

    def test_query_nan_norm_is_a_violation(self) -> None:
        guard = _norm_guard()
        check = guard.check_query_vector([float("nan"), 1.0], model_name="m", tolerance=0.001)
        assert check is not None
        assert check.violation is True

    def test_disabled_returns_none_without_checking(self) -> None:
        """Spec: Disable is explicit — no rejection when disabled."""
        guard = _norm_guard()
        band = guard.check_ingest_vectors(
            [_vec(0.7)],
            model_name="m",
            enabled=False,
            tolerance=0.001,
        )
        assert band is None

    def test_worst_deviation_is_named(self) -> None:
        """With several violating vectors the furthest-from-unit is reported."""
        guard = _norm_guard()
        with pytest.raises(guard.EmbeddingNormViolationError) as excinfo:
            guard.check_ingest_vectors(
                [_vec(0.9), _vec(0.7)],
                model_name="m",
                tolerance=0.001,
            )
        assert "0.700000" in str(excinfo.value)

    def test_query_check_returns_state(self) -> None:
        """Query check reports observed norm and violation flag."""
        guard = _norm_guard()
        check = guard.check_query_vector(
            _vec(0.7),
            model_name="m",
            tolerance=0.001,
        )
        assert check is not None
        assert check.violation is True
        assert math.isclose(check.observed_norm, 0.7, abs_tol=1e-9)
        state = check.as_dict()
        assert state["enabled"] is True
        assert state["tolerance"] == 0.001
        assert state["violation"] is True
        assert "observed_norm" in state

    def test_query_check_disabled_returns_none(self) -> None:
        guard = _norm_guard()
        assert (
            guard.check_query_vector(_vec(0.7), model_name="m", enabled=False, tolerance=0.001)
            is None
        )

    def test_query_warn_once_per_model(self, caplog: pytest.LogCaptureFixture) -> None:
        """Spec: warning fires at most once per process per model."""
        import logging

        guard = _norm_guard()
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.norm_guard"):
            for _ in range(3):
                guard.check_query_vector(_vec(0.7), model_name="m", tolerance=0.001)
            # A different model warns again.
            guard.check_query_vector(_vec(0.7), model_name="other", tolerance=0.001)
        warnings = [r for r in caplog.records if "norm" in r.getMessage().lower()]
        # Three calls for model "m" produced one warning; model "other"
        # warned again — two warnings total across four checks.
        assert len(warnings) == 2
        models_warned = {getattr(r, "model", None) for r in warnings}
        assert models_warned == {"m", "other"}


# ── Task 2.3: the ingest boundary ───────────────────────────────────────


def _nodes(vectors: list[list[float]]):
    """Pre-embed nodes so replacement skips the (mocked) provider."""
    from llama_index.core.schema import TextNode

    nodes = []
    for index, vector in enumerate(vectors):
        node = TextNode(text=f"chunk {index}", metadata={"file_path": "doc.txt"})
        node.embedding = list(vector)
        nodes.append(node)
    return nodes


async def _replace(
    store: LanceVectorStore,
    collection: str,
    vectors: list[list[float]],
    *,
    source_id: str = "src_norm_guard",
    norm_guard_enabled: bool = True,
    norm_tolerance: float = 0.001,
):
    from rag_mcp.core.ingestion.replacement import replace_source_nodes_async

    return await replace_source_nodes_async(
        _nodes(vectors),
        file_path="doc.txt",
        source_id=source_id,
        content_hash="a" * 64,
        index_identity="index-identity",
        source_version="source-version",
        collection_name=collection,
        store=store,
        norm_guard_enabled=norm_guard_enabled,
        norm_tolerance=norm_tolerance,
    )


class TestIngestBoundary:
    """Fail-closed guard at the replacement embed step, before any write."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> LanceVectorStore:
        return LanceVectorStore(uri=str(tmp_path / "norm-guard-lance"))

    async def test_unit_vectors_ingest_and_band_recorded(self, store: LanceVectorStore) -> None:
        """Spec: Unit-norm vectors ingest normally; band in the outcome."""
        outcome = await _replace(store, "norm-ok", [_vec(1.0, 2), _vec(1.0, 2)])
        assert outcome.chunks_written == 2
        assert outcome.norm_band is not None
        assert math.isclose(outcome.norm_band[1], 1.0, abs_tol=1e-9)
        assert store.count_where("norm-ok", {"file_path": "doc.txt"}) == 2

    @pytest.mark.parametrize("bad_norm", [0.7, 1.4])
    async def test_off_norm_aborts_before_write_previous_version_intact(
        self, store: LanceVectorStore, bad_norm: float
    ) -> None:
        """Spec: norm 0.7/1.4 aborts before write; previous version searchable."""
        from rag_mcp.core.ingestion.replacement import IngestionStageError

        await _replace(store, "norm-safe", [_vec(1.0)], source_id="src-a")
        generation = store.get_generation("norm-safe")
        guard = _norm_guard()

        with pytest.raises(IngestionStageError) as excinfo:
            await _replace(
                store,
                "norm-safe",
                [_vec(1.0), _vec(bad_norm)],
                source_id="src-b",
            )
        assert excinfo.value.stage == "embedding"
        assert isinstance(excinfo.value.__cause__, guard.EmbeddingNormViolationError)
        cause_message = str(excinfo.value.__cause__)
        assert f"{bad_norm:.6f}" in cause_message
        assert "0.001" in cause_message
        # Failure-safe ordering: the previous version is still searchable.
        assert store.count_where("norm-safe", {"source_id": "src-a"}) == 1
        assert store.get_generation("norm-safe") == generation

    async def test_provider_produced_off_norm_caught_after_embed(
        self, store: LanceVectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guard runs after the embed step, so provider output is checked too."""
        from llama_index.core.schema import TextNode

        monkeypatch.setattr(
            Settings,
            "embed_model",
            _FixedNormEmbedding(embed_dim=2, norm=0.7),
        )
        nodes = [TextNode(text="chunk", metadata={"file_path": "doc.txt"})]
        from rag_mcp.core.ingestion.replacement import (
            IngestionStageError,
            replace_source_nodes_async,
        )

        with pytest.raises(IngestionStageError) as excinfo:
            await replace_source_nodes_async(
                nodes,
                file_path="doc.txt",
                source_id="src-c",
                content_hash="a" * 64,
                index_identity="i",
                source_version="v",
                collection_name="norm-provider",
                store=store,
            )
        assert excinfo.value.stage == "embedding"

    async def test_tolerance_configurable_097_passes(self, store: LanceVectorStore) -> None:
        """Spec scenario: tolerance 0.05 admits a 0.97-norm vector."""
        outcome = await _replace(
            store,
            "norm-tol",
            [_vec(0.97)],
            norm_tolerance=0.05,
        )
        assert outcome.chunks_written == 1
        assert outcome.norm_band is not None
        assert math.isclose(outcome.norm_band[0], 0.97, abs_tol=1e-9)

    async def test_disabled_guard_writes_and_records_no_band(self, store: LanceVectorStore) -> None:
        """Spec: disabled guard performs no rejection and no diagnostic."""
        outcome = await _replace(
            store,
            "norm-off",
            [_vec(0.7)],
            norm_guard_enabled=False,
        )
        assert outcome.chunks_written == 1
        assert outcome.norm_band is None


# ── Task 2.5: the query boundary ────────────────────────────────────────


class TestQueryBoundary:
    """Warn-and-continue guard on the query embedding before dense search."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> LanceVectorStore:
        return LanceVectorStore(uri=str(tmp_path / "norm-guard-query"))

    def _seed(self, store: LanceVectorStore, collection: str = "norm-query") -> None:
        store.upsert_precomputed(
            collection,
            ids=["row-1", "row-2"],
            documents=["alpha chunk", "beta chunk"],
            metadatas=[{"file_path": "a.md"}, {"file_path": "b.md"}],
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            embedding_identity=EmbeddingIdentity(provider="test", model="unit"),
        )

    def test_off_norm_query_returns_results_warns_once(
        self,
        store: LanceVectorStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        effective_settings,
    ) -> None:
        """Spec: off-norm query still returns results; warns once per model."""
        import logging

        self._seed(store)
        monkeypatch.setattr(Settings, "embed_model", _FixedNormEmbedding(embed_dim=2, norm=0.7))
        guard = _norm_guard()
        guard.reset_warned_norm_models()
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.norm_guard"):
            first = search(
                "unique-off-norm-query",
                store=store,
                collection_name="norm-query",
                effective_settings=effective_settings(),
                include_diagnostics=True,
            )
            # Second search: same model — the warn-once set suppresses a
            # repeat warning even though the check itself runs again.
            search(
                "unique-off-norm-query",
                store=store,
                collection_name="norm-query",
                effective_settings=effective_settings(),
            )
        assert first  # results still returned
        warnings = [r for r in caplog.records if "norm" in r.getMessage().lower()]
        assert len(warnings) == 1
        diagnostic = first[0]["norm_guard"]
        assert diagnostic["violation"] is True
        assert math.isclose(diagnostic["observed_norm"], 0.7, abs_tol=1e-9)

    def test_diagnostics_expose_guard_state(
        self,
        store: LanceVectorStore,
        monkeypatch: pytest.MonkeyPatch,
        effective_settings,
    ) -> None:
        """Spec: diagnostics include enable flag, tolerance, observed norm."""
        self._seed(store)
        monkeypatch.setattr(Settings, "embed_model", _FixedNormEmbedding(embed_dim=2, norm=1.0))
        results = search(
            "unique-unit-query",
            store=store,
            collection_name="norm-query",
            effective_settings=effective_settings(norm_tolerance=0.05),
            include_diagnostics=True,
        )
        assert results
        for row in results:
            state = row["norm_guard"]
            assert state["enabled"] is True
            assert state["tolerance"] == 0.05
            assert state["violation"] is False
            assert math.isclose(state["observed_norm"], 1.0, abs_tol=1e-9)

    def test_unit_norm_query_is_silent(
        self,
        store: LanceVectorStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        effective_settings,
    ) -> None:
        """Spec: unit-norm query logs nothing and attaches no diagnostic."""
        import logging

        self._seed(store)
        monkeypatch.setattr(Settings, "embed_model", _FixedNormEmbedding(embed_dim=2, norm=1.0))
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.norm_guard"):
            results = search(
                "unique-silent-query",
                store=store,
                collection_name="norm-query",
                effective_settings=effective_settings(),
            )
        assert results
        assert all("norm_guard" not in row for row in results)
        assert not [r for r in caplog.records if "norm" in r.getMessage().lower()]

    def test_disabled_guard_no_diagnostic_no_warning(
        self,
        store: LanceVectorStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        effective_settings,
    ) -> None:
        """Spec: disabled guard produces no rejection and no diagnostic."""
        import logging

        self._seed(store)
        monkeypatch.setattr(Settings, "embed_model", _FixedNormEmbedding(embed_dim=2, norm=0.7))
        guard = _norm_guard()
        guard.reset_warned_norm_models()
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.norm_guard"):
            results = search(
                "unique-disabled-query",
                store=store,
                collection_name="norm-query",
                effective_settings=effective_settings(**{"embedding.norm_guard_enabled": False}),
                include_diagnostics=True,
            )
        assert results
        assert all("norm_guard" not in row for row in results)
        assert not [r for r in caplog.records if "norm" in r.getMessage().lower()]


# ── Task 2.7: guard configuration ───────────────────────────────────────


class TestGuardConfiguration:
    """Nested settings, validation, and the startup visibility contract."""

    def test_env_nesting_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EMBEDDING__* env vars reach the embedding block."""
        import sys

        monkeypatch.setenv("EMBEDDING__NORM_GUARD_ENABLED", "false")
        monkeypatch.setenv("EMBEDDING__NORM_TOLERANCE", "0.05")
        config_mod = sys.modules.get("rag_mcp.config")
        if config_mod is not None:
            monkeypatch.setattr(config_mod, "_settings", None, raising=False)
        from rag_mcp.config import get_settings

        settings = get_settings()
        assert settings.embedding.norm_guard_enabled is False
        assert settings.embedding.norm_tolerance == 0.05

    def test_defaults(self) -> None:
        from rag_mcp.core.settings import EmbeddingSettings

        block = EmbeddingSettings()
        assert block.norm_guard_enabled is True
        assert block.norm_tolerance == 0.001

    def test_tolerance_must_be_positive(self) -> None:
        from pydantic import ValidationError

        from rag_mcp.core.settings import EmbeddingSettings

        with pytest.raises(ValidationError):
            EmbeddingSettings(norm_tolerance=0)

    def test_effective_settings_carries_embedding_block(self, effective_settings) -> None:
        settings = effective_settings(
            **{"embedding.norm_guard_enabled": False, "embedding.norm_tolerance": 0.05}
        )
        assert settings.embedding.norm_guard_enabled is False
        assert settings.embedding.norm_tolerance == 0.05

    def test_startup_logs_when_disabled(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from rag_mcp.compose import _log_norm_guard_state
        from rag_mcp.config import Settings

        with caplog.at_level(logging.WARNING, logger="rag_mcp.compose"):
            _log_norm_guard_state(Settings(embedding={"norm_guard_enabled": False}))
        assert any("EMBEDDING__NORM_GUARD_ENABLED" in r.getMessage() for r in caplog.records)

    def test_startup_silent_when_enabled(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from rag_mcp.compose import _log_norm_guard_state
        from rag_mcp.config import Settings

        with caplog.at_level(logging.WARNING, logger="rag_mcp.compose"):
            _log_norm_guard_state(Settings())
        assert not caplog.records


def search(*args, **kwargs):  # noqa: ANN001, ANN202 - resolved below
    """Lazily import the retrieval entry point (keeps module import cheap)."""
    from rag_mcp.core.retrieval.pipeline import search as _search

    return _search(*args, **kwargs)
