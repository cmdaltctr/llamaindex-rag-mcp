"""Tests for run submission, inspection, cancellation, retry and polling (task 6.6).

A real Engine over in-memory fakes, the real SQLite workspace repository
on ``tmp_path`` and the real ``RunService``. No model calls. Stream
tests are in ``test_web_runs_stream.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    graph,
    login,
    make_engine,
    save_revision,
    submit,
    wait_run,
)

from omrg.core.pipelines import AdmissionSnapshot  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def client(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        test_client.policy = policy  # type: ignore[attr-defined]
        yield test_client
    if engine.gate is not None:
        engine.gate.set()


def test_submitted_run_executes_the_admitted_snapshot(client: Any, engine: Any) -> None:
    validations: list[Any] = []
    original = engine.validate_pipeline

    def counting(*args: Any, **kwargs: Any) -> Any:
        validations.append(kwargs.get("inputs"))
        return original(*args, **kwargs)

    engine.validate_pipeline = counting
    revision = save_revision(client)
    response = submit(client, revision["revision_id"], query="text")
    assert response.status_code == 202, response.text
    queued = response.json()["run"]
    assert queued["status"] == "queued"
    assert queued["revision_id"] == revision["revision_id"]
    assert queued["graph_hash"] == revision["content_hash"]
    assert queued["inputs"] == {"query": "text"}
    run = wait_run(client, queued["run_id"])
    assert run["status"] == "succeeded", run
    # Admission ran once, at submission; the executor ran that snapshot.
    assert validations == [{"query": "text"}]
    assert len(engine.runs) == 1 and isinstance(engine.runs[0], AdmissionSnapshot)
    assert run["resources"]["graph_identity"] == engine.runs[0].graph_identity
    assert run["settings"]["documents"]["profile"]
    result = client.get(f"/v1/runs/{run['run_id']}/result").json()
    assert result["result"]["run_id"] == run["run_id"]
    assert result["result"]["status"] == "succeeded"


def test_polling_returns_ordered_events_after_a_sequence(client: Any) -> None:
    revision = save_revision(client)
    run_id = submit(client, revision["revision_id"]).json()["run"]["run_id"]
    run = wait_run(client, run_id)
    everything = client.get(f"/v1/runs/{run_id}/events").json()
    sequences = [event["sequence"] for event in everything["events"]]
    assert sequences == list(range(1, run["last_sequence"] + 1))
    assert everything["complete"] is True
    assert everything["events"][-1]["summary"]["status"] == "succeeded"
    later = client.get(f"/v1/runs/{run_id}/events", params={"after_sequence": 3}).json()
    assert later["events"] == everything["events"][3:]
    page = client.get(f"/v1/runs/{run_id}/events", params={"limit": 2}).json()
    assert [e["sequence"] for e in page["events"]] == [1, 2]
    assert page["last_sequence"] == 2 and page["complete"] is False


def test_editing_after_submission_keeps_the_admitted_revision(client: Any, engine: Any) -> None:
    gate = engine.hold()
    revision = save_revision(client)
    run_id = submit(client, revision["revision_id"]).json()["run"]["run_id"]
    newer = client.post(
        f"/v1/pipelines/{revision['pipeline_id']}/revisions",
        json={"document": graph(top_k=5)},
        headers=ORIGIN,
    ).json()["revision"]
    assert newer["revision_id"] != revision["revision_id"]
    gate.set()
    run = wait_run(client, run_id)
    assert run["revision_id"] == revision["revision_id"]
    assert run["graph_hash"] == revision["content_hash"]


def test_cancel_queued_and_active_runs(client: Any, engine: Any) -> None:
    gate = engine.hold()
    revision = save_revision(client)
    active = submit(client, revision["revision_id"]).json()["run"]["run_id"]
    assert engine.started.wait(5)
    waiting = submit(client, revision["revision_id"]).json()["run"]["run_id"]
    cancelled = client.post(f"/v1/runs/{waiting}/cancel", headers=ORIGIN)
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "cancelled"
    stopping = client.post(f"/v1/runs/{active}/cancel", headers=ORIGIN).json()["run"]
    assert stopping["status"] == "cancelling"
    gate.set()
    assert wait_run(client, active)["status"] == "cancelled"
    assert len(engine.runs) == 1  # the waiting run never started
    again = client.post(f"/v1/runs/{active}/cancel", headers=ORIGIN)
    assert again.json()["run"]["status"] == "cancelled"


def test_full_queue_returns_429_without_a_record(client: Any, engine: Any) -> None:
    gate = engine.hold()
    revision = save_revision(client)
    submit(client, revision["revision_id"])
    assert engine.started.wait(5)
    for _ in range(16):
        assert submit(client, revision["revision_id"]).status_code == 202
    before = len(client.get("/v1/runs").json()["runs"])
    response = submit(client, revision["revision_id"])
    assert response.status_code == 429
    assert response.json()["status"] == "error"
    assert "queue is full" in response.json()["message"]
    assert len(client.get("/v1/runs").json()["runs"]) == before
    gate.set()


def test_failed_run_can_be_retried_as_a_new_run(client: Any, engine: Any) -> None:
    revision = save_revision(client)
    original = engine.run_pipeline

    async def failing(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("store went away")

    engine.run_pipeline = failing
    run_id = submit(client, revision["revision_id"]).json()["run"]["run_id"]
    failed = wait_run(client, run_id)
    assert failed["status"] == "failed"
    assert "store went away" in failed["failure"]["error"]
    engine.run_pipeline = original

    retried = client.post(f"/v1/runs/{run_id}/retry", headers=ORIGIN)
    assert retried.status_code == 202, retried.text
    new = retried.json()["run"]
    assert new["run_id"] != run_id
    assert new["origin"] == "retry" and new["source_run_id"] == run_id
    assert wait_run(client, new["run_id"])["status"] == "succeeded"
    assert client.get(f"/v1/runs/{run_id}").json()["run"] == failed
    refused = client.post(f"/v1/runs/{new['run_id']}/retry", headers=ORIGIN)
    assert refused.status_code == 409


def test_explicit_repeat_and_input_refusals(client: Any) -> None:
    revision = save_revision(client)
    repeat = client.post(
        "/v1/runs",
        json={"revision_id": revision["revision_id"], "inputs": {"query": "q"}, "origin": "repeat"},
        headers=ORIGIN,
    )
    assert repeat.status_code == 202
    assert repeat.json()["run"]["origin"] == "repeat"
    secret = submit(client, revision["revision_id"], query="q", api_key="sk-live-123")
    assert secret.status_code == 400
    assert "sk-live-123" not in secret.text
    missing = submit(client, "no-such-revision")
    assert missing.status_code == 404


def test_unknown_run_routes_are_404(client: Any) -> None:
    for path in ("/v1/runs/nope", "/v1/runs/nope/events", "/v1/runs/nope/result"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["status"] == "error"
    assert client.post("/v1/runs/nope/cancel", headers=ORIGIN).status_code == 404
    assert client.post("/v1/runs/nope/retry", headers=ORIGIN).status_code == 404


def test_run_scopes(client: Any) -> None:
    revision = save_revision(client)
    client.cookies.clear()
    reader = bearer(client.policy, "read", "graph")
    body = {"revision_id": revision["revision_id"], "inputs": {"query": "q"}}
    assert client.post("/v1/runs", json=body, headers=reader).status_code == 403
    runner = bearer(client.policy, "run")
    accepted = client.post("/v1/runs", json=body, headers=runner)
    assert accepted.status_code == 202
    run_id = accepted.json()["run"]["run_id"]
    assert client.get(f"/v1/runs/{run_id}/events", headers=runner).status_code == 403
    assert client.get(f"/v1/runs/{run_id}/events", headers=reader).status_code == 200
    assert client.get(f"/v1/runs/{run_id}/events").status_code == 401


def test_list_runs_filters_by_pipeline_and_status(client: Any) -> None:
    first = save_revision(client)
    second = save_revision(client, graph(top_k=3))
    a = submit(client, first["revision_id"]).json()["run"]["run_id"]
    b = submit(client, second["revision_id"]).json()["run"]["run_id"]
    wait_run(client, a), wait_run(client, b)
    listed = client.get("/v1/runs").json()["runs"]
    assert [r["run_id"] for r in listed] == [b, a]  # newest first
    only = client.get("/v1/runs", params={"pipeline_id": first["pipeline_id"]}).json()["runs"]
    assert [r["run_id"] for r in only] == [a]
    done = client.get("/v1/runs", params={"status": "succeeded", "limit": 1}).json()["runs"]
    assert len(done) == 1
    assert client.get("/v1/runs", params={"status": "finished"}).status_code == 400


def test_restart_reports_unfinished_runs_as_interrupted(tmp_path: Path, engine: Any) -> None:
    workspace = tmp_path / "ws"
    repository = SqliteWorkspaceRepository(workspace / "workspace.db")
    pipeline = repository.create_pipeline("Left over")
    revision = repository.save_revision(pipeline["pipeline_id"], graph(), schema_version=1)
    stale = repository.create_run(revision["revision_id"], settings={}, resources={}, inputs={})
    app, policy = build_app(tmp_path, engine, workspace=workspace)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        run = client.get(f"/v1/runs/{stale['run_id']}").json()["run"]
    assert run["status"] == "interrupted"
    assert engine.runs == []  # never repeated automatically
