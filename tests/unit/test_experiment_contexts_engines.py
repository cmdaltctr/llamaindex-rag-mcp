"""Experiment Engine contexts through composition (task 8.5, design D10).

Each approved context gets its own Engine with a LanceDB store below its
workspace ``output/`` directory. These tests run the canonical ingestion
graph on tmp_path stores with the conftest mock embedder and the parity
fixture sources. No model, LLM or network call runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_engine_pipelines_support import retrieval_graph
from tests.unit.test_experiment_contexts_support import (
    RecordingBuilder,
    base_settings,
    new_embedder,
    under,
)

from omrg.compose_experiments import (
    ExperimentEngines,
    experiment_registry,
    experiment_settings,
    live_backend_identity,
)
from omrg.core.experiments import (
    ExperimentAdmissionError,
    ExperimentPathError,
    check_credential_target,
)
from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.pipelines import RunStatus
from omrg.core.vectordb.lancedb.store import LanceVectorStore


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    """Return the live library, the experiment root and two workspaces."""
    root = tmp_path / "experiments"
    for name in ("exp-a", "exp-b"):
        (root / name).mkdir(parents=True)
    return {"live": tmp_path / "live" / "lancedb", "root": root, "tmp": tmp_path}


@pytest.fixture
def builder() -> RecordingBuilder:
    """Return a recording engine builder."""
    return RecordingBuilder()


@pytest.fixture
def engines(layout: dict[str, Path], builder: RecordingBuilder) -> Any:
    """Return experiment engines over the approved root; close them afterwards."""
    registry = experiment_registry([layout["root"]])
    service = ExperimentEngines(registry, base_settings(layout["live"]), build_engine=builder)
    yield service
    service.close()


def _ingest(engines: ExperimentEngines, context_id: str, root: Path, **kwargs: Any) -> Any:
    return engines.run(
        context_id,
        canonical_ingestion_definition("graph"),
        inputs={"path": str(root)},
        **kwargs,
    )


async def test_ingestion_experiment_writes_only_below_its_workspace(
    monkeypatch: pytest.MonkeyPatch, layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """The store and rows live in ``output/``; the live library stays empty."""
    pin_detection(monkeypatch)
    sources = copy_sources(layout["tmp"])
    context = engines.registry.register(layout["root"] / "exp-a")

    outcome = await _ingest(engines, context.context_id, sources, session=True)

    assert outcome.result.status is RunStatus.SUCCEEDED, outcome.result.error
    assert len(outcome.result.completed_effects) == 3
    identity = engines.identity(context.context_id)
    assert identity.store_kind == "lancedb"
    assert under(identity.store_path, context.output_dir)
    assert Path(identity.store_path).is_dir()
    assert "graph" in engines.engine(context.context_id).list_collections()
    assert not layout["live"].exists(), "the live library must stay untouched"
    provenance = outcome.provenance
    assert provenance["context_id"] == context.context_id
    assert provenance["graph_identity"] == outcome.result.graph_identity
    assert provenance["backend"] == identity.provenance()
    assert engines.registry.active_leases(context.context_id) == 0


def test_experiment_identity_differs_from_live_and_between_contexts(
    layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """Each context reports its own store path and index identity."""
    first = engines.registry.register(layout["root"] / "exp-a")
    second = engines.registry.register(layout["root"] / "exp-b")
    live = live_backend_identity(base_settings(layout["live"]))
    a, b = engines.identity(first.context_id), engines.identity(second.context_id)

    assert live.context_id is None and under(live.store_path, layout["live"])
    assert len({live.index_identity, a.index_identity, b.index_identity}) == 3
    assert (a.embedding_provider, a.embedding_model) == (
        live.embedding_provider,
        live.embedding_model,
    )
    assert under(a.store_path, first.output_dir) and under(b.store_path, second.output_dir)


async def test_two_contexts_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
    layout: dict[str, Path],
    engines: ExperimentEngines,
    builder: RecordingBuilder,
) -> None:
    """Separate Engines, stores and embedders; rows stay in their context."""
    pin_detection(monkeypatch)
    sources = copy_sources(layout["tmp"])
    first = engines.registry.register(layout["root"] / "exp-a")
    second = engines.registry.register(layout["root"] / "exp-b")

    await _ingest(engines, first.context_id, sources, session=True)
    engine_a, engine_b = engines.engine(first.context_id), engines.engine(second.context_id)

    assert engine_a is engines.engine(first.context_id), "one cached Engine per context"
    assert engine_a is not engine_b
    assert engine_a._embed_model is not engine_b._embed_model
    assert engine_a.store is not engine_b.store
    assert "graph" in engine_a.list_collections()
    assert engine_b.list_collections() == []
    assert [Path(s.lancedb_uri).parent for s in builder.calls] == [
        first.output_dir,
        second.output_dir,
    ]


def test_experiment_credential_cannot_target_the_live_library(
    layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """A bound credential fails on the live route before any store call."""
    context = engines.registry.register(layout["root"] / "exp-a")
    live_store = LanceVectorStore(uri=str(layout["live"]))

    with pytest.raises(ExperimentAdmissionError) as info:
        check_credential_target(
            bound_context=context.context_id, target_context=None, session=False
        )
    assert info.value.code == "live_library_target"
    assert not layout["live"].exists()
    live_store.close()


async def test_bound_credential_cannot_use_another_context(
    layout: dict[str, Path], engines: ExperimentEngines, builder: RecordingBuilder
) -> None:
    """A credential bound to one context is refused for another, before any build."""
    first = engines.registry.register(layout["root"] / "exp-a")
    second = engines.registry.register(layout["root"] / "exp-b")

    for bound in (first.context_id, None):
        with pytest.raises(ExperimentAdmissionError) as info:
            await _ingest(engines, second.context_id, layout["tmp"], bound_context=bound)
        assert info.value.code in {"experiment_scope_mismatch", "experiment_credential_required"}
    assert builder.calls == [], "no Engine is built for a refused credential"
    assert not second.output_dir.exists()


async def test_read_only_context_admits_retrieval_and_rejects_commits(
    layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """Read-only graphs pass; a commit node fails before any write."""
    context = engines.registry.register(layout["root"] / "exp-a", actions=["read"])
    bound = {"bound_context": context.context_id}

    with engines.admit(
        context.context_id, retrieval_graph(), inputs={"query": "q"}, **bound
    ) as admission:
        assert admission.snapshot.graph_identity
        assert engines.registry.active_leases(context.context_id) == 1
    assert engines.registry.active_leases(context.context_id) == 0

    with pytest.raises(ExperimentAdmissionError) as info:
        await _ingest(engines, context.context_id, layout["tmp"], **bound)
    assert info.value.code == "action_not_permitted"
    assert engines.engine(context.context_id).list_collections() == []
    assert engines.registry.active_leases(context.context_id) == 0


async def test_revocation_lets_the_in_flight_run_finish_then_closes_the_engine(
    monkeypatch: pytest.MonkeyPatch, layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """Revocation refuses new admissions; the admitted run completes."""
    pin_detection(monkeypatch)
    sources = copy_sources(layout["tmp"])
    context = engines.registry.register(layout["root"] / "exp-a")
    admission = engines.admit(
        context.context_id,
        canonical_ingestion_definition("graph"),
        inputs={"path": str(sources)},
        session=True,
    )
    engine = admission.engine

    engines.revoke(context.context_id)
    with pytest.raises(ExperimentAdmissionError) as info:
        await _ingest(engines, context.context_id, sources, session=True)
    assert info.value.code == "experiment_context_revoked"

    result = await engine.run_pipeline(admission.snapshot)
    assert result.status is RunStatus.SUCCEEDED
    admission.release()
    assert engines.registry.active_leases(context.context_id) == 0
    with pytest.raises(RuntimeError, match="closed"):
        engine.store  # noqa: B018 - the property raises on a closed Engine
    with pytest.raises(ExperimentAdmissionError):
        engines.engine(context.context_id)


async def test_queued_job_fails_when_its_context_is_revoked_before_execution(
    layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """Execution checks the context again, writes nothing and releases the lease."""
    context = engines.registry.register(layout["root"] / "exp-a")
    admission = engines.admit(
        context.context_id,
        canonical_ingestion_definition("graph"),
        inputs={"path": str(layout["tmp"])},
        session=True,
    )
    engine = admission.engine
    engines.revoke(context.context_id)

    with pytest.raises(ExperimentAdmissionError) as info:
        await engines.execute(admission)
    assert info.value.code == "experiment_context_revoked"
    assert engines.registry.active_leases(context.context_id) == 0
    assert engine._closed


async def test_leases_are_released_after_failure_and_rejection(
    layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """A failing run and a rejected admission leave no lease behind."""
    context = engines.registry.register(layout["root"] / "exp-a", actions=["read"])
    engine = engines.engine(context.context_id)

    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("executor failed")

    with patch.object(engine, "run_pipeline", broken), pytest.raises(RuntimeError):
        await engines.run(
            context.context_id, retrieval_graph(), inputs={"query": "q"}, session=True
        )
    assert engines.registry.active_leases(context.context_id) == 0

    with pytest.raises(ExperimentAdmissionError):
        await _ingest(engines, context.context_id, layout["tmp"], session=True)
    assert engines.registry.active_leases(context.context_id) == 0


def test_close_refuses_while_leased_and_closes_every_engine(
    layout: dict[str, Path], engines: ExperimentEngines, builder: RecordingBuilder
) -> None:
    """Shutdown waits for borrowed contexts, then closes every Engine."""
    first = engines.registry.register(layout["root"] / "exp-a")
    second = engines.registry.register(layout["root"] / "exp-b")
    lease = engines.registry.acquire(first.context_id)
    engines.engine(first.context_id), engines.engine(second.context_id)

    with pytest.raises(RuntimeError, match=first.context_id):
        engines.close()
    assert not any(e._closed for e in builder.engines)
    lease.release()
    engines.close()
    assert all(e._closed for e in builder.engines)


def test_output_link_planted_after_registration_is_rejected_at_build(
    layout: dict[str, Path], engines: ExperimentEngines, builder: RecordingBuilder
) -> None:
    """Composition checks containment again before it builds the store."""
    context = engines.registry.register(layout["root"] / "exp-a")
    outside = layout["tmp"] / "elsewhere"
    outside.mkdir()
    context.output_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExperimentPathError) as info:
        engines.engine(context.context_id)
    assert info.value.code == "symlink_escape"
    assert builder.calls == []


def test_workspace_swapped_for_a_link_creates_nothing_outside(
    layout: dict[str, Path], engines: ExperimentEngines, builder: RecordingBuilder
) -> None:
    """A workspace replaced by a link after registration gets no output directory."""
    context = engines.registry.register(layout["root"] / "exp-a")
    outside = layout["tmp"] / "elsewhere"
    outside.mkdir()
    context.workspace.rmdir()
    context.workspace.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExperimentPathError) as info:
        engines.engine(context.context_id)
    assert info.value.code == "symlink_escape"
    assert list(outside.iterdir()) == [] and builder.calls == []


def test_declared_store_factor_moves_the_store_backend(layout: dict[str, Path]) -> None:
    """A context that declares the store factor gets its own Chroma directory."""
    registry = experiment_registry([layout["root"]])
    context = registry.register(
        layout["root"] / "exp-a", store_backend="chroma", declared_factors=["store"]
    )
    settings, store_dir = experiment_settings(base_settings(layout["live"]), context)

    assert settings.vector_store == "chroma" and settings.chroma_mode == "local"
    assert Path(settings.chroma_persist_dir) == store_dir == context.output_dir / "chroma"
    default = registry.register(layout["root"] / "exp-b")
    settings, store_dir = experiment_settings(base_settings(layout["live"]), default)
    assert settings.vector_store == "lancedb"
    assert Path(settings.lancedb_uri) == store_dir == default.output_dir / "lancedb"


def test_production_builder_composes_through_build_engine(layout: dict[str, Path]) -> None:
    """The default builder is ``compose.build_engine`` with experiment settings."""
    from omrg import compose

    registry = experiment_registry([layout["root"]])
    engines = ExperimentEngines(registry, base_settings(layout["live"]))
    first = registry.register(layout["root"] / "exp-a")
    second = registry.register(layout["root"] / "exp-b")
    global_embedder = LlamaIndexSettings.embed_model

    with (
        patch.object(compose, "build_embed_model", side_effect=lambda s: new_embedder()),
        patch.object(compose, "build_reranker", return_value=None),
    ):
        engine_a = engines.engine(first.context_id)
        engine_b = engines.engine(second.context_id)

    assert engine_a._embed_model is not engine_b._embed_model
    assert compose.EMBEDDING_PROVIDER_SCOPE == "engine"
    assert LlamaIndexSettings.embed_model is global_embedder
    assert under(engine_a.resolve_settings().lancedb_uri, first.output_dir)
    assert under(engine_b.resolve_settings().lancedb_uri, second.output_dir)
    engines.close()


async def test_poisoned_process_defaults_are_untouched(
    monkeypatch: pytest.MonkeyPatch, layout: dict[str, Path], engines: ExperimentEngines
) -> None:
    """Registration, build, admission and run read no process default."""
    import omrg.core.settings as core_settings
    import omrg.core.vectordb as vectordb

    pin_detection(monkeypatch)
    sources = copy_sources(layout["tmp"])
    original = vectordb.get_default_store
    installed_store = original()
    hits: list[str] = []

    def poisoned(name: str) -> Any:
        def _fail(*args: Any, **kwargs: Any) -> Any:
            hits.append(name)
            raise AssertionError(f"process default {name} must not be read")

        return _fail

    monkeypatch.setattr(core_settings, "get_default_effective_settings", poisoned("settings"))
    monkeypatch.setattr(vectordb, "get_default_store", poisoned("store"))
    context = engines.registry.register(layout["root"] / "exp-a")

    outcome = await _ingest(engines, context.context_id, sources, session=True)

    assert outcome.result.status is RunStatus.SUCCEEDED, outcome.result.error
    assert hits == []
    assert original() is installed_store
