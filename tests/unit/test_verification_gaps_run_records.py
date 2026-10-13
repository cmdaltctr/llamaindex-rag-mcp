"""Run-record gaps from the verification report (section B).

* An explicit repeat of an older revision runs that older document.
* A workspace schema upgrade leaves the vector store bytes unchanged.
* An explicit retry of an interrupted ingestion run relies on the source
  completeness rules: complete sources are reused, a partly written
  source and a missing source are written again.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
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
from tests.unit.test_workspace_service_support import (
    GRAPH,
    GRAPH_CHANGED,
    FakeAdmitter,
    FakeExecutor,
    idle,
    make_service,
    repository,
)

from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.pipelines import CancellationToken, PipelineResult, RunStatus
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.core.workspace import Admission, ArtefactStore, RevisionRecord, RunJob, RunService
from omrg.engine import Engine
from omrg.integrations.workspace_sqlite import SCHEMA_MIGRATIONS, SqliteWorkspaceRepository

# ── Repeat of an older revision ──────────────────────────────────────────


async def test_repeat_of_an_older_revision_runs_that_document(tmp_path: Path) -> None:
    """Revision A, then B; a repeat of A executes A, not the current B."""
    executor, admitter = FakeExecutor(), FakeAdmitter()
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    repo = service.repository
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    old = repo.save_revision(pipeline_id, GRAPH, schema_version=1)
    new = repo.save_revision(pipeline_id, GRAPH_CHANGED, schema_version=1)
    assert repo.get_pipeline(pipeline_id)["current_revision_id"] == new["revision_id"]

    run = service.submit(old["revision_id"], inputs={"name": "old"}, origin="repeat")
    await idle(service)

    job = executor.calls[-1]
    assert job.revision_id == old["revision_id"]
    assert json.loads(job.document_json) == GRAPH
    assert job.graph_hash == old["content_hash"] != new["content_hash"]
    assert admitter.calls[-1][0] == old["revision_id"]
    record = repo.get_run(run["run_id"])
    assert (record["origin"], record["revision_id"]) == ("repeat", old["revision_id"])
    assert record["status"] == "succeeded"
    await service.shutdown()


# ── Schema upgrade leaves the vector store alone ─────────────────────────


def _tree(base: Path) -> dict[str, bytes]:
    """Return every file below ``base`` as relative path to bytes."""
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


async def test_workspace_upgrade_leaves_vector_store_bytes_unchanged(
    tmp_path: Path, effective_settings: Any
) -> None:
    """A real LanceDB store and a planted Chroma file are byte-identical after upgrade."""
    workspace = tmp_path / "ws"
    db_path = workspace / "app.sqlite3"
    SqliteWorkspaceRepository(db_path).create_pipeline("Seeded")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.txt").write_text("A short note about vector stores.\n", encoding="utf-8")
    lance_dir = tmp_path / "lancedb"
    engine = Engine(
        offline_settings(effective_settings),
        store=LanceVectorStore(uri=str(lance_dir)),
        embed_model=LlamaIndexSettings.embed_model,
    )
    await engine.ingest(str(docs), collection_name="kept")
    engine.close()
    chroma_dir = workspace / "chroma"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_bytes(b"chroma bytes")
    before = {"lance": _tree(lance_dir), "chroma": _tree(chroma_dir)}
    assert before["lance"], "the LanceDB store wrote no files"

    upgrade = (2, ("ALTER TABLE pipelines ADD COLUMN description TEXT",))
    SqliteWorkspaceRepository(db_path, migrations=(*SCHEMA_MIGRATIONS, upgrade))

    assert len(list(workspace.glob("*.bak"))) == 1, "the upgrade did not run"
    assert {"lance": _tree(lance_dir), "chroma": _tree(chroma_dir)} == before
    reopened = LanceVectorStore(uri=str(lance_dir))
    assert reopened.count("kept") > 0
    reopened.close()


# ── Retry of an interrupted run and source completeness ──────────────────


class _EngineExecutor:
    """Run-service executor that runs the stored document on a real Engine."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.results: list[PipelineResult] = []

    async def __call__(
        self, job: RunJob, *, on_event: Any, cancellation: CancellationToken
    ) -> PipelineResult:
        result = await self.engine.run_pipeline(
            json.loads(job.document_json),
            inputs=json.loads(job.inputs_json),
            on_event=on_event,
            cancellation=cancellation,
            run_id=job.run_id,
        )
        self.results.append(result)
        return result


def _admit(revision: RevisionRecord, inputs: Mapping[str, Any]) -> Admission:
    return Admission(settings={}, resources={}, payload=None)


def _rows_by_source(store: Any, collection: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for row_id, _text, metadata in store.iter_documents(collection):
        rows.setdefault(Path(metadata["file_path"]).name, []).append(row_id)
    return rows


async def test_retry_of_interrupted_ingestion_uses_source_completeness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Complete source reused; partial and missing sources written again."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    engine = Engine(
        offline_settings(effective_settings),
        store=store,
        embed_model=LlamaIndexSettings.embed_model,
    )
    document = canonical_ingestion_definition("retry").model_dump(mode="json")
    reference = await engine.ingest(str(root), collection_name="reference")
    assert reference["files_indexed"] == 3

    # State a process leaves when it stops part way: guide.md complete,
    # appendix.md partly written, notes.txt never written.
    first = await engine.run_pipeline(document, inputs={"path": str(root)})
    assert first.status is RunStatus.SUCCEEDED, first.error
    effect_of = {u.unit_id: u.effects[0] for u in first.units}
    rows = _rows_by_source(store, "retry")
    assert len(rows["appendix.md"]) >= 2, "appendix.md needs two chunks to be partial"
    store.delete_ids("retry", rows["appendix.md"][:1])
    store.delete_ids("retry", rows["notes.txt"])

    repo = repository(tmp_path)
    pipeline_id = repo.create_pipeline("Ingest")["pipeline_id"]
    revision = repo.save_revision(pipeline_id, document, schema_version=1)
    stale = repo.create_run(
        revision["revision_id"], settings={}, resources={}, inputs={"path": str(root)}
    )
    run_id = stale["run_id"]
    repo.record_update(run_id, kind="run.status", summary={"status": "running"}, status="running")
    repo.record_update(
        run_id,
        kind="effect_committed",
        summary={"data": {"effect": effect_of["guide.md"]}},
        node_id="commit",
    )

    executor = _EngineExecutor(engine)
    service = RunService(
        repo, executor, admit=_admit, artefacts=ArtefactStore(tmp_path / "ws" / "artefacts")
    )
    assert await service.start() == [run_id]
    interrupted = repo.get_run(run_id)
    assert interrupted["status"] == "interrupted"
    assert interrupted["failure"]["completed_effects"] == [effect_of["guide.md"]]

    retried = service.retry(run_id)
    await idle(service, timeout=30)

    record = repo.get_run(retried["run_id"])
    assert record["status"] == "succeeded", record.get("failure")
    assert (record["origin"], record["source_run_id"]) == ("retry", run_id)
    (result,) = executor.results
    statuses = {u.unit_id: u.outputs["summary"]["status"] for u in result.units}
    assert statuses == {
        "guide.md": "skipped_unchanged",
        "nested/appendix.md": "indexed",
        "notes.txt": "indexed",
    }
    assert set(result.completed_effects) == {
        effect_of["nested/appendix.md"],
        effect_of["notes.txt"],
    }
    assert collect_rows(store, "retry", root) == collect_rows(store, "reference", root)
    assert repo.get_run(run_id)["status"] == "interrupted"
    await service.shutdown()
    engine.close()
