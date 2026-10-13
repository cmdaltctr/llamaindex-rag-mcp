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

from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.pipelines import RunStatus
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.engine import Engine


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


async def test_ingestion_run_builds_and_closes_its_own_ocr_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """With OCR fallback on and no Engine client, the run owns one OCR client."""
    from omrg import capabilities

    clients: list[Any] = []

    class FakeRoutes:
        fingerprint = "fake-ocr"

        def __init__(self, settings: Any) -> None:
            self.closed = False
            clients.append(self)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(capabilities, "build_ocr_routes", FakeRoutes)
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings).model_copy(
        update={"ocr_fallback_enabled": True}
    )
    engine = _engine(tmp_path, settings)
    snapshot = engine.validate_pipeline(
        canonical_ingestion_definition("ocr"), inputs={"path": str(root)}
    )
    assert clients == [], "validation must not build an OCR client"
    host = engine._graph_host(None)
    from omrg.compose_pipelines import plan_run

    plan = plan_run(snapshot, engine._pipelines.catalogue(), host)
    assert plan.resources["ocr"] is clients[0] and plan.units is not None
    plan.close()
    assert clients[0].closed
    engine.close()


def test_retrieval_run_plans_no_ingestion_resources(effective_settings: Any) -> None:
    """A graph without ingestion operations gets no unit split or shape."""
    from tests.unit.test_engine_pipelines_support import build_engine, retrieval_graph

    from omrg.compose_pipelines import plan_run

    engine = build_engine(effective_settings())
    snapshot = engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    plan = plan_run(snapshot, engine._pipelines.catalogue(), engine._graph_host(None))
    assert (plan.resources, plan.units, plan.owned) == ({}, None, [])
