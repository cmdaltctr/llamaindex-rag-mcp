"""Engine ingest on a collection that follows a user profile (design D2, D5, D16, task 5.5)."""

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
from tests.unit.test_engine_profiles_support import (
    PROFILE,
    count_graph_runs,
    make_env,
    resolver_for,
    save_slot,
    slot_graph,
)
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrg.core.vectordb.lancedb.store import LanceVectorStore
from omrg.engine import Engine


class World:
    """An Engine over a LanceDB store with a plain and a user-profile collection."""

    def __init__(self, tmp_path: Path, effective_settings: Any, monkeypatch: Any) -> None:
        pin_detection(monkeypatch)
        self.root = copy_sources(tmp_path)
        self.env = make_env(tmp_path, effective_settings)
        settings = offline_settings(effective_settings)
        self.store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
        self.engine = Engine(
            settings,
            store=self.store,
            embed_model=LlamaIndexSettings.embed_model,
            profile_resolver=resolver_for(self.env, self.store, settings),
        )
        self.runs = count_graph_runs(self.engine)
        self.store.create_collection("graph")
        self.store.update_collection_metadata("graph", {"profile": PROFILE})

    async def ingest(self, collection: str, **kwargs: Any) -> dict[str, Any]:
        return await self.engine.ingest(str(self.root), collection_name=collection, **kwargs)


@pytest.fixture
def world(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, effective_settings, monkeypatch)


async def test_ingest_on_a_user_profile_returns_the_built_in_summary_and_rows(world: World) -> None:
    standard = await world.ingest("standard")
    assert world.runs == []
    result = await world.ingest("graph")
    assert world.runs == ["run_pipeline"]
    assert set(result) == set(standard)
    for key in (
        "status",
        "files_indexed",
        "files_skipped_unchanged",
        "files_skipped_binary",
        "chunks_created",
        "chunks_removed",
        "metadata_degraded",
    ):
        assert result[key] == standard[key], key
    assert result["collection"] == "graph" and result["files_indexed"] == 3
    assert result["peak_rss_bytes"] is None
    assert result["timings"]["total_seconds"] > 0
    assert [d["file"] for d in result["file_details"]] == [
        d["file"] for d in standard["file_details"]
    ]
    assert {d["status"] for d in result["file_details"]} == {"indexed"}
    graph_rows = collect_rows(world.engine._store, "graph", world.root)
    assert graph_rows and graph_rows == collect_rows(world.engine._store, "standard", world.root)


async def test_progress_callback_is_called_once_per_file(world: World) -> None:
    calls: list[tuple[str, int, int]] = []
    await world.ingest("graph", progress_callback=lambda *args: calls.append(args))
    assert [c[1] for c in calls] == [1, 2, 3]
    assert {c[2] for c in calls} == {3}


async def test_an_unchanged_source_is_skipped_on_the_next_ingestion(world: World) -> None:
    await world.ingest("graph")
    again = await world.ingest("graph")
    assert (again["files_indexed"], again["files_skipped_unchanged"]) == (0, 3)
    assert again["status"] == "ok"
    assert {d["status"] for d in again["file_details"]} == {"skipped_unchanged"}
    assert world.runs == ["run_pipeline"] * 2


async def test_a_source_is_processed_again_after_an_ingest_change(world: World) -> None:
    await world.ingest("graph")
    before = collect_rows(world.engine._store, "graph", world.root)
    graph = slot_graph(world.env, "ingest")
    chunk = next(n for n in graph["nodes"] if n["id"] == "chunk")
    chunk["params"] = {"chunk_size": 128, "chunk_overlap": 16}
    save_slot(world.env, "ingest", graph)
    # Saving the revision alone changes nothing.
    assert collect_rows(world.engine._store, "graph", world.root) == before
    result = await world.ingest("graph")
    assert (result["files_indexed"], result["files_skipped_unchanged"]) == (3, 0)
    assert world.runs == ["run_pipeline"] * 2


async def test_a_request_chunk_size_replaces_the_step_setting(world: World) -> None:
    default = await world.ingest("graph")
    small = await world.ingest("graph", chunk_size=64, chunk_overlap=8)
    assert small["files_indexed"] == 3
    assert small["chunks_created"] != default["chunks_created"]
    assert world.runs == ["run_pipeline"] * 2


async def test_a_missing_path_returns_the_built_in_error(world: World, tmp_path: Path) -> None:
    missing = str(tmp_path / "nope")
    standard = await world.engine.ingest(missing, collection_name="standard")
    result = await world.engine.ingest(missing, collection_name="graph")
    assert result["status"] == standard["status"] == "error"
    assert result["message"] == standard["message"]
    assert world.runs == []


async def test_built_in_ingest_never_runs_a_graph(world: World) -> None:
    await world.ingest("standard")
    assert world.runs == []
