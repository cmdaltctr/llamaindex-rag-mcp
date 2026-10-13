"""Run records name the index, operation versions, node controls and summaries.

A live-library run records the backend identity of the Engine store and,
per referenced collection, the durable data version when the store has
one, else an explicit process-local marker. It also records each node's
operation version and admitted controls with their sources. The stored
result keeps each node summary, bounded and redacted. Real Engine, real
SQLite workspace and real run service; no model call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_engine_pipelines_support import rerank_graph  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    ProcessLocalStore,
    lance_store,
    make_engine,
    seed,
)
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    build_app,
    login,
    save_revision,
    submit,
    wait_run,
)

from omrg.core.workspace import ArtefactStore, RunService  # noqa: E402
from omrg.core.workspace.artefacts import MAX_TEXT_BYTES  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrg.transports.api.runs_wiring import RunAdmitter, build_executor  # noqa: E402

COLLECTION = "documents"


class SilentReranker:
    """Reranker double; an explicitly disabled node never calls it."""

    def rerank(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the disabled rerank node ran inference")


def _engine(store: Any, effective_settings: Any) -> Any:
    seed(store, COLLECTION, "/approved/a.md", 2)
    settings = effective_settings(rerank_enabled=True, collection_name=COLLECTION)
    return make_engine(store, settings, reranker=SilentReranker())


@pytest.fixture
def durable(tmp_path: Path, effective_settings: Any) -> Any:
    return _engine(lance_store(tmp_path), effective_settings)


def _client(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    client = TestClient(app, base_url=BASE)
    client.__enter__()
    login(client, policy)
    return client


def _run(client: Any, document: dict[str, Any]) -> dict[str, Any]:
    revision = save_revision(client, document)
    response = submit(client, revision["revision_id"], query="chunk")
    assert response.status_code == 202, response.text
    return wait_run(client, response.json()["run"]["run_id"])


def test_run_detail_records_the_durable_index_identity(tmp_path: Path, durable: Any) -> None:
    client = _client(tmp_path, durable)
    try:
        expected = durable.store.get_data_version(COLLECTION)
        run = _run(client, rerank_graph(enabled=False))
    finally:
        client.__exit__(None, None, None)
    index = run["resources"]["index"]
    assert index["backend"]["store_kind"] == "lancedb"
    assert index["backend"]["store_class"] == "LanceVectorStore"
    assert index["backend"]["index_identity"]
    version = index["collections"][COLLECTION]
    assert expected is not None
    assert version == {"exists": True, "data_version": expected, "version_scope": "durable"}
    operations = run["resources"]["operations"]
    assert operations["rerank"] == "select.rerank@1"
    assert operations["dense"] == "retrieve.dense@1"


def test_run_detail_records_node_controls_and_sources(tmp_path: Path, durable: Any) -> None:
    client = _client(tmp_path, durable)
    try:
        run = _run(client, rerank_graph(enabled=False))
        result = client.get(f"/v1/runs/{run['run_id']}/result").json()["result"]
    finally:
        client.__exit__(None, None, None)
    controls = {c["lever"]: c for c in run["resources"]["controls"]["rerank"]}
    rerank = controls["retrieval.rerank_enabled"]
    assert (rerank["value"], rerank["source"]) == (False, "node")
    assert "rerank" in rerank["detail"]
    assert result["controls"]["rerank"] == run["resources"]["controls"]["rerank"]
    outcome = next(n for n in result["nodes"] if n["node_id"] == "rerank")
    assert outcome["summary"] == {
        "reranked": False,
        "reason": "disabled by node parameter",
        "rows": 2,
    }


def test_store_without_durable_version_records_a_process_local_marker(
    tmp_path: Path, effective_settings: Any
) -> None:
    engine = _engine(ProcessLocalStore(uri=str(tmp_path / "lancedb")), effective_settings)
    client = _client(tmp_path, engine)
    try:
        run = _run(client, rerank_graph())
    finally:
        client.__exit__(None, None, None)
    version = run["resources"]["index"]["collections"][COLLECTION]
    assert version["data_version"] is None
    assert version["version_scope"] == "process-local"
    assert isinstance(version["generation"], int)


async def test_python_run_record_keeps_index_and_controls(tmp_path: Path, durable: Any) -> None:
    """The stored record from the run service itself, without HTTP."""
    repository = SqliteWorkspaceRepository(tmp_path / "ws" / "workspace.db")
    service = RunService(
        repository,
        build_executor(durable),
        admit=RunAdmitter(durable),
        artefacts=ArtefactStore(tmp_path / "ws" / "artefacts"),
    )
    await service.start()
    pipeline = repository.create_pipeline("Search")
    revision = repository.save_revision(
        pipeline["pipeline_id"], rerank_graph(enabled=False), schema_version=1
    )
    queued = service.submit(revision["revision_id"], inputs={"query": "chunk"})
    await service.wait_idle()
    run = repository.get_run(queued["run_id"])
    await service.shutdown()
    assert run["status"] == "succeeded", run["failure"]
    resources = run["resources"]
    assert resources["index"]["collections"][COLLECTION]["version_scope"] == "durable"
    assert resources["operations"]["rerank"] == "select.rerank@1"
    sources = {c["lever"]: c["source"] for c in resources["controls"]["rerank"]}
    assert sources["retrieval.rerank_enabled"] == "node"


async def test_stored_node_summaries_are_bounded_and_redacted(tmp_path: Path) -> None:
    """A large or secret node summary never reaches the stored result in full."""
    from tests.unit.test_workspace_service_support import (
        SECRET,
        FakeAdmitter,
        FakeExecutor,
        idle,
        make_service,
        saved_revision,
    )

    from omrg.core.pipelines import NodeOutcome, NodeStatus

    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.nodes = (
        NodeOutcome(
            node_id="a",
            status=NodeStatus.SUCCEEDED,
            summary={"note": "x" * (MAX_TEXT_BYTES * 2), "api_key": SECRET},
        ),
    )
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a"})
    await idle(service)
    record = service.repository.get_run(run["run_id"])
    stored = service.artefacts.read_json(record["result_ref"])
    await service.shutdown()
    summary = stored["nodes"][0]["summary"]
    assert len(summary["note"].encode("utf-8")) <= MAX_TEXT_BYTES
    assert SECRET not in str(stored)
