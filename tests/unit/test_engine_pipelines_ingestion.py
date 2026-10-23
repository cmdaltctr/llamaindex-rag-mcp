"""Ingestion graphs through ``Engine.run_pipeline`` (task 4.3).

The canonical ingestion graph runs on a temporary LanceDB store over the
parity fixtures. It must write the same rows as ``Engine.ingest``. The
Engine plans the run from the admitted snapshot: the per-source unit split,
the ingestion shape resource and the OCR client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    pin_detection,
)
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.pipelines import RunStatus
from omrs.core.vectordb.lancedb.store import LanceVectorStore
from omrs.engine import Engine


def _engine(tmp_path: Path, settings: Any, **kwargs: Any) -> Engine:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    return Engine(settings, store=store, embed_model=LlamaIndexSettings.embed_model, **kwargs)


async def test_ingestion_graph_writes_the_same_rows_as_engine_ingest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """The canonical graph, run per source unit, equals ``Engine.ingest``."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    engine = _engine(tmp_path, offline_settings(effective_settings))
    standard = await engine.ingest(str(root), collection_name="standard")
    events: list[Any] = []

    async def sink(event: Any) -> None:
        events.append(event)

    result = await engine.run_pipeline(
        canonical_ingestion_definition("graph"), inputs={"path": str(root)}, on_event=sink
    )

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert [u.unit_id for u in result.units] == ["guide.md", "nested/appendix.md", "notes.txt"]
    assert len(result.completed_effects) == standard["files_indexed"] == 3
    graph_rows = collect_rows(engine._store, "graph", root)
    assert graph_rows and graph_rows == collect_rows(engine._store, "standard", root)
    assert any(e.kind == "unit_completed" for e in events)
    engine.close()


class FakeRoutes:
    """OCR route client double that records construction and closing."""

    built: list[FakeRoutes] = []
    fingerprint = "fake-ocr"

    def __init__(self, settings: Any) -> None:
        self.closed = 0
        FakeRoutes.built.append(self)

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def fake_ocr(monkeypatch: pytest.MonkeyPatch) -> list[FakeRoutes]:
    """Replace the OCR route builder; return the list of built clients."""
    from omrs import capabilities

    FakeRoutes.built = []
    monkeypatch.setattr(capabilities, "build_ocr_routes", FakeRoutes)
    return FakeRoutes.built


def _ocr_engine(tmp_path: Path, effective_settings: Any) -> Engine:
    settings = offline_settings(effective_settings).model_copy(
        update={"ocr_fallback_enabled": True}
    )
    return _engine(tmp_path, settings)


async def test_graph_runs_borrow_one_engine_owned_ocr_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings: Any,
    fake_ocr: list[FakeRoutes],
) -> None:
    """Runs never build or close an OCR client; the Engine builds one and owns it."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    engine = _ocr_engine(tmp_path, effective_settings)
    snapshot = engine.validate_pipeline(
        canonical_ingestion_definition("ocr"), inputs={"path": str(root)}
    )
    assert fake_ocr == [], "validation must not build an OCR client"
    from omrs.compose_pipeline_runs import plan_run

    plan = plan_run(snapshot, engine._pipelines.catalogue(), engine._graph_host(None))
    again = plan_run(snapshot, engine._pipelines.catalogue(), engine._graph_host(None))
    assert plan.resources["ocr"] is again.resources["ocr"] is fake_ocr[0]
    assert plan.units is not None

    for _ in range(2):
        result = await engine.run_pipeline(
            canonical_ingestion_definition("ocr"), inputs={"path": str(root)}
        )
        assert result.status is RunStatus.SUCCEEDED, result.error
    assert len(fake_ocr) == 1, "two runs must share one Engine-owned client"
    assert fake_ocr[0].closed == 0, "a run must not close the Engine's client"
    engine.close()
    assert fake_ocr[0].closed == 1


async def test_engine_ingest_keeps_its_operation_owned_ocr_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings: Any,
    fake_ocr: list[FakeRoutes],
) -> None:
    """``Engine.ingest`` without an Engine client still builds and closes its own."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    engine = _ocr_engine(tmp_path, effective_settings)
    await engine.run_pipeline(canonical_ingestion_definition("graph"), inputs={"path": str(root)})
    shared = fake_ocr[0]
    await engine.ingest(str(root), collection_name="standard")
    assert len(fake_ocr) == 2 and fake_ocr[1] is not shared
    assert fake_ocr[1].closed == 1, "the ingest operation closes the client it built"
    assert shared.closed == 0
    engine.close()
    assert shared.closed == 1 and fake_ocr[1].closed == 1


def test_injected_ocr_client_is_borrowed_and_never_rebuilt(
    tmp_path: Path, effective_settings: Any, fake_ocr: list[FakeRoutes]
) -> None:
    """An Engine composed with a client lends that client to runs."""
    from omrs.compose_pipeline_runs import plan_run

    injected = FakeRoutes(None)
    settings = offline_settings(effective_settings).model_copy(
        update={"ocr_fallback_enabled": True}
    )
    engine = _engine(tmp_path, settings, ocr_client=injected)
    snapshot = engine.validate_pipeline(
        canonical_ingestion_definition("ocr"), inputs={"path": str(tmp_path)}
    )
    plan = plan_run(snapshot, engine._pipelines.catalogue(), engine._graph_host(None))
    assert plan.resources.get("ocr", engine._graph_host(None).resources["ocr"]) is injected
    assert fake_ocr == [injected]
    engine.close()
    assert injected.closed == 1


def test_retrieval_run_plans_no_ingestion_resources(effective_settings: Any) -> None:
    """A graph without ingestion operations gets no unit split or shape."""
    from tests.unit.test_engine_pipelines_support import build_engine, retrieval_graph

    from omrs.compose_pipeline_runs import plan_run

    engine = build_engine(effective_settings())
    snapshot = engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    plan = plan_run(snapshot, engine._pipelines.catalogue(), engine._graph_host(None))
    assert (plan.resources, plan.units) == ({}, None)
