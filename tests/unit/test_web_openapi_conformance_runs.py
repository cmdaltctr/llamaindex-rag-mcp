"""Response conformance for graph, run, event and cleanup routes (task 6.7).

The application uses a real Engine over in-memory fakes (real catalogue
and graph validation, no model calls), the real SQLite workspace
repository and the real run service. Every response, including the
server-sent event frames, is validated against ``openapi.yaml``. The
tests also check job semantics: 202 with an identifier, polling states,
and interruption of unfinished work after a restart.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    TERMINAL,
    build_app,
    graph,
    login,
    make_engine,
)

from omrg.core.workspace import WorkspaceLayout  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrg.transports.api.runs_wiring import TASK_LAYOUT_KEY  # noqa: E402


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def client(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        test_client.policy = policy  # type: ignore[attr-defined]
        test_client.app_ref = app  # type: ignore[attr-defined]
        yield test_client


def _wait(client: TestClient, check: ContractChecker, run_id: str) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + 10
    while True:
        run = check.check(client.get(f"/v1/runs/{run_id}"), 200)["run"]
        if run["status"] in TERMINAL:
            return run
        assert time.monotonic() < deadline, run
        time.sleep(0.02)


def _revision(client: TestClient, check: ContractChecker, **params: Any) -> dict[str, Any]:
    pipeline = check.check(client.post("/v1/pipelines", json={"title": "S"}, headers=ORIGIN), 201)
    pipeline_id = pipeline["pipeline"]["pipeline_id"]
    body = {"document": graph(**(params or {"top_k": 2}))}
    saved = client.post(f"/v1/pipelines/{pipeline_id}/revisions", json=body, headers=ORIGIN)
    return check.check(saved, 201)["revision"]


def _submit(client: TestClient, revision_id: str, **headers: str) -> Any:
    body = {"revision_id": revision_id, "inputs": {"query": "text"}}
    return client.post("/v1/runs", json=body, headers={**ORIGIN, **headers})


def test_graph_responses_conform(client: Any) -> None:
    check = ContractChecker()
    catalogue = check.check(client.get("/v1/pipeline-operations"), 200)
    assert any(op["operation_id"] == "retrieve.dense" for op in catalogue["operations"])
    created = check.check(
        client.post("/v1/pipelines", json={"title": "Search"}, headers=ORIGIN), 201
    )
    pipeline_id = created["pipeline"]["pipeline_id"]
    reserved = {"title": "x", "layout": {TASK_LAYOUT_KEY: "ingest"}}
    check.check(client.post("/v1/pipelines", json=reserved, headers=ORIGIN), 400)
    reader = {"Authorization": f"Bearer {client.policy.issue_bearer({'read'}).token}"}
    check.check(client.post("/v1/pipelines", json={"title": "x"}, headers=reader), 403)
    assert check.check(client.get("/v1/pipelines"), 200)["pipelines"]
    detail = check.check(client.get(f"/v1/pipelines/{pipeline_id}"), 200)
    assert detail["current_revision"] is None
    check.check(client.get("/v1/pipelines/unknown"), 404)
    layout = {"layout": {"nodes": {"a": {"x": 1}}}}
    check.check(client.put(f"/v1/pipelines/{pipeline_id}/layout", json=layout, headers=ORIGIN), 200)
    check.check(client.put("/v1/pipelines/unknown/layout", json=layout, headers=ORIGIN), 404)
    repository = client.app_ref.state.runtime.run_service.service.repository
    job_pipeline = repository.create_pipeline("job", layout={TASK_LAYOUT_KEY: "ingest"})
    job_layout = f"/v1/pipelines/{job_pipeline['pipeline_id']}/layout"
    check.check(client.put(job_layout, json=layout, headers=ORIGIN), 409)
    revisions = f"/v1/pipelines/{pipeline_id}/revisions"
    document = {"document": graph(top_k=2)}
    first = check.check(client.post(revisions, json=document, headers=ORIGIN), 201)
    again = check.check(client.post(revisions, json=document, headers=ORIGIN), 200)
    assert (first["created"], again["created"]) == (True, False)
    bad = {"document": {"schema_version": 99, "nodes": [], "edges": []}}
    issues = check.check(client.post(revisions, json=bad, headers=ORIGIN), 422)["issues"]
    assert issues and issues[0]["code"]
    revision_id = first["revision"]["revision_id"]
    assert check.check(client.get(revisions), 200)["revisions"]
    check.check(client.get(f"{revisions}/{revision_id}"), 200)
    check.check(client.get(f"{revisions}/unknown"), 404)
    assert check.check(client.get(f"/v1/pipelines/{pipeline_id}"), 200)["current_revision"]
    validate = "/v1/pipelines/validate"
    draft = check.check(client.post(validate, json=document, headers=ORIGIN), 200)
    admitted = {**document, "inputs": {"query": "text"}}
    full = check.check(client.post(validate, json=admitted, headers=ORIGIN), 200)
    assert (draft["admitted"], full["admitted"]) == (False, True)
    check.check(client.post(validate, json=bad, headers=ORIGIN), 422)
    assert check.operations >= FAMILIES["graphs"]


def test_run_and_event_responses_conform(client: Any, engine: Any) -> None:
    check = ContractChecker()
    revision = _revision(client, check)
    queued = check.check(_submit(client, revision["revision_id"]), 202)["run"]
    assert queued["status"] == "queued"
    run = _wait(client, check, queued["run_id"])
    assert run["status"] == "succeeded"
    run_id = run["run_id"]
    assert check.check(client.get("/v1/runs", params={"status": "succeeded"}), 200)["runs"]
    check.check(client.get("/v1/runs", params={"limit": 0}), 400)
    check.check(client.get(f"/v1/runs/{run_id}/result"), 200)
    service = client.app_ref.state.runtime.run_service.service
    service.artefacts_for(run).safe_summary(run_id, "event-big", {"text": "x" * 40_000})
    check.check(client.get(f"/v1/runs/{run_id}/artefacts/event-big"), 200)
    check.check(client.get(f"/v1/runs/{run_id}/artefacts/event-none"), 404)
    check.check(client.get(f"/v1/runs/{run_id}/artefacts/%2E%2E"), 400)
    page = check.check(client.get(f"/v1/runs/{run_id}/events"), 200)
    assert page["complete"] and page["last_sequence"] == run["last_sequence"]
    frames = check.check(client.get(f"/v1/runs/{run_id}/events/stream"), 200)
    assert frames[-1]["event"] == "run.end"
    assert [int(f["id"]) for f in frames[1:-1]] == [e["sequence"] for e in page["events"]]
    replay = check.check(
        client.get(f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": "2"}), 200
    )
    assert all(int(f["id"]) > 2 for f in replay[1:-1])
    check.check(client.get(f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": "x"}), 400)
    for path in ("", "/result", "/artefacts/event-big", "/events", "/events/stream"):
        check.check(client.get(f"/v1/runs/unknown{path}"), 404)
    check.check(client.post("/v1/runs/unknown/cancel", headers=ORIGIN), 404)
    check.check(_submit(client, "unknown"), 404)
    invalid = {"revision_id": revision["revision_id"], "inputs": {"unexpected": 1}}
    check.check(client.post("/v1/runs", json=invalid, headers=ORIGIN), 422)
    check.check(client.post(f"/v1/runs/{run_id}/retry", headers=ORIGIN), 409)
    reader = {"Authorization": f"Bearer {client.policy.issue_bearer({'read'}).token}"}
    check.check(_submit(client, revision["revision_id"], **reader), 403)
    check.check(client.get(f"/v1/runs/{run_id}/events/stream", headers=reader), 200)
    anonymous = TestClient(client.app_ref, base_url=BASE)  # same app, no cookie
    check.check(anonymous.get(f"/v1/runs/{run_id}/events/stream"), 401)
    # Cancellation, retry and the bounded queue.
    gate = engine.hold()
    active = check.check(_submit(client, revision["revision_id"]), 202)["run"]["run_id"]
    assert engine.started.wait(5)
    waiting = check.check(_submit(client, revision["revision_id"]), 202)["run"]["run_id"]
    cancelled = check.check(client.post(f"/v1/runs/{waiting}/cancel", headers=ORIGIN), 200)
    assert cancelled["run"]["status"] == "cancelled"
    stopping = check.check(client.post(f"/v1/runs/{active}/cancel", headers=ORIGIN), 200)
    assert stopping["run"]["status"] == "cancelling"
    full = None
    for _ in range(40):
        response = _submit(client, revision["revision_id"])
        if response.status_code == 429:
            full = response
            break
        check.check(response, 202)
    assert full is not None, "the queue never reported full"
    check.check(full, 429)
    gate.set()
    assert _wait(client, check, active)["status"] == "cancelled"
    retried = check.check(client.post(f"/v1/runs/{waiting}/retry", headers=ORIGIN), 202)["run"]
    assert (retried["origin"], retried["source_run_id"]) == ("retry", waiting)
    assert check.operations >= FAMILIES["runs"]


def test_cleanup_responses_conform(client: Any) -> None:
    check = ContractChecker()
    revision = _revision(client, check)
    run_id = check.check(_submit(client, revision["revision_id"]), 202)["run"]["run_id"]
    _wait(client, check, run_id)
    preview_path, apply_path = "/v1/workspace/cleanup/preview", "/v1/workspace/cleanup"
    selector = {"selector": {"statuses": ["succeeded"]}}
    preview = check.check(client.post(preview_path, json=selector, headers=ORIGIN), 200)["preview"]
    assert preview["totals"]["runs"] == 1
    bad = {"selector": {"statuses": ["running"]}}
    check.check(client.post(preview_path, json=bad, headers=ORIGIN), 422)
    unknown = {"selector": {"run_id": "nope"}}
    check.check(client.post(preview_path, json=unknown, headers=ORIGIN), 404)
    reader = {"Authorization": f"Bearer {client.policy.issue_bearer({'read', 'run'}).token}"}
    check.check(client.post(preview_path, json=selector, headers=reader), 403)
    body = {"token": preview["token"]}
    result = check.check(client.post(apply_path, json=body, headers=ORIGIN), 200)["result"]
    assert result["runs_removed"] == 1
    check.check(client.post(apply_path, json=body, headers=ORIGIN), 409)
    check.check(
        client.post(apply_path, json={**body, "selector": bad["selector"]}, headers=ORIGIN), 422
    )
    assert check.operations >= FAMILIES["cleanup"]


def test_unfinished_work_reads_interrupted_after_restart(tmp_path: Path, engine: Any) -> None:
    """A run and a job left unfinished by a stopped server are never repeated."""
    workspace = tmp_path / "ws"
    repository = SqliteWorkspaceRepository(WorkspaceLayout(workspace).records)
    pipeline = repository.create_pipeline("Left over")
    revision = repository.save_revision(pipeline["pipeline_id"], graph(), schema_version=1)
    stale_run = repository.create_run(
        revision["revision_id"], settings={}, resources={}, inputs={"query": "text"}
    )
    job_pipeline = repository.create_pipeline(
        "Workspace job: ingest", layout={TASK_LAYOUT_KEY: "ingest"}
    )
    job_revision = repository.save_revision(
        job_pipeline["pipeline_id"], {"task": "ingest"}, schema_version=1
    )
    stale_job = repository.create_run(
        job_revision["revision_id"], settings={}, resources={}, inputs={"path": "/x"}
    )
    app, policy = build_app(tmp_path, engine, workspace=workspace)
    check = ContractChecker()
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        run = check.check(client.get(f"/v1/runs/{stale_run['run_id']}"), 200)["run"]
        job_id = str(uuid.UUID(stale_job["run_id"]))
        job = check.check(client.get(f"/v1/jobs/{job_id}"), 200)
        assert engine.runs == []  # nothing was repeated automatically
        retry = client.post(f"/v1/runs/{stale_run['run_id']}/retry", headers=ORIGIN)
        retried = check.check(retry, 202)["run"]
        assert _wait(client, check, retried["run_id"])["status"] == "succeeded"
    assert run["status"] == "interrupted" and run["failure"]["reason"] == "interrupted"
    assert job["status"] == "failed" and job["error"]
