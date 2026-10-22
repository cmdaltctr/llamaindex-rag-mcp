"""Experiment contexts over HTTP: routes, credential binding and runs (task 8.5).

A bearer credential bound to an experiment context runs read-only graphs
in that context only. It cannot reach the live library (read or write),
cannot select another context, and a revoked context refuses its next
run before any side effect. The browser session can use both. An
experiment run records the context backend and index identity, which
differ from the live library identity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bound_bearer,
    build_experiment_app,
    login,
    register,
    save_revision,
    submit,
    wait_run,
)
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

from omrs.compose_experiments import live_backend_identity  # noqa: E402


@pytest.fixture
def live(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def setup(tmp_path: Path, live: Any, effective_settings: Any) -> Any:
    parts = build_experiment_app(tmp_path, live, effective_settings)
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        yield client, parts


# ── Registration routes ──────────────────────────────────────────────────


def test_experiment_routes_are_session_only(setup: Any) -> None:
    client, parts = setup
    token = parts.policy.issue_bearer({"graph", "read", "run"}).token
    header = {"Authorization": f"Bearer {token}"}
    workspace = parts.root / "w"
    workspace.mkdir()
    assert client.get("/v1/experiments", headers=header).status_code == 403
    created = client.post("/v1/experiments", json={"workspace": str(workspace)}, headers=header)
    assert created.status_code == 403
    assert parts.experiments.registry.contexts() == []


def test_register_list_get_and_revoke(setup: Any, tmp_path: Path) -> None:
    client, parts = setup
    body = register(client, parts.root, "exp-a", actions=["read"])
    record, identity = body["experiment"], body["identity"]
    context_id = record["context_id"]
    assert context_id.startswith("exp_") and record["actions"] == ["read"]
    assert record["status"] == "active"
    store = Path(identity["store_path"])
    assert store.is_relative_to((parts.root / "exp-a" / "output").resolve())
    live = live_backend_identity(parts.base)
    assert identity["index_identity"] != live.index_identity
    listed = client.get("/v1/experiments").json()
    assert [entry["experiment"]["context_id"] for entry in listed["experiments"]] == [context_id]
    assert listed["roots"] == [str(parts.root.resolve())]
    assert "filesystem" in listed["trust_notice"]
    one = client.get(f"/v1/experiments/{context_id}").json()
    assert one["identity"] == identity
    revoked = client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    assert revoked.status_code == 200
    assert revoked.json()["experiment"]["status"] == "revoked"
    missing = client.get("/v1/experiments/exp_0000000000000000")
    assert missing.status_code == 404
    assert missing.json()["code"] == "experiment_context_unknown"


@pytest.mark.parametrize(
    ("workspace", "code"),
    [("relative/path", "not_absolute"), ("{outside}", "outside_root"), ("{dotdot}", "traversal")],
)
def test_register_rejects_unapproved_paths(
    setup: Any, tmp_path: Path, workspace: str, code: str
) -> None:
    client, parts = setup
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = workspace.format(outside=outside, dotdot=f"{parts.root}/../elsewhere")
    response = client.post("/v1/experiments", json={"workspace": path}, headers=ORIGIN)
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert parts.experiments.registry.contexts() == []


def test_register_without_approved_roots_is_refused(
    tmp_path: Path, live: Any, effective_settings: Any
) -> None:
    parts = build_experiment_app(
        tmp_path, live, effective_settings, experiment_roots=(), experiments_factory=None
    )
    workspace = tmp_path / "w"
    workspace.mkdir()
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        response = client.post(
            "/v1/experiments", json={"workspace": str(workspace)}, headers=ORIGIN
        )
        listed = client.get("/v1/experiments").json()
    assert response.status_code == 409
    assert "--experiment-root" in response.json()["message"]
    assert listed["experiments"] == [] and listed["roots"] == []


# ── Credential binding ───────────────────────────────────────────────────


def test_credentials_bind_only_to_an_active_context(setup: Any) -> None:
    client, _ = setup
    context_id = register(client, setup[1].root)["experiment"]["context_id"]
    issued = client.post(
        "/v1/credentials",
        json={"scopes": ["run", "read"], "experiment_context": context_id},
        headers=ORIGIN,
    )
    assert issued.status_code == 201
    assert issued.json()["experiment_context"] == context_id
    listed = client.get("/v1/credentials").json()["credentials"]
    assert listed[0]["experiment_context"] == context_id
    unknown = client.post(
        "/v1/credentials",
        json={"scopes": ["run"], "experiment_context": "exp_ffffffffffffffff"},
        headers=ORIGIN,
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "experiment_context_unknown"
    client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    revoked = client.post(
        "/v1/credentials",
        json={"scopes": ["run"], "experiment_context": context_id},
        headers=ORIGIN,
    )
    assert revoked.status_code == 400
    assert revoked.json()["code"] == "experiment_context_revoked"
    assert len(client.get("/v1/credentials").json()["credentials"]) == 1


# ── Runs with a bound credential ─────────────────────────────────────────


def test_bound_bearer_runs_a_read_only_graph_in_its_context(setup: Any, live: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root, actions=["read"])["experiment"]["context_id"]
    header = bound_bearer(client, context_id)
    revision_id = save_revision(client)
    response = submit(client, revision_id, context=context_id, headers=header)
    assert response.status_code == 202, response.text
    run = wait_run(client, response.json()["run"]["run_id"], header)
    assert run["status"] == "succeeded", run["failure"]
    experiment = run["resources"]["experiment"]
    assert experiment["context_id"] == context_id
    assert experiment["graph_identity"] == run["resources"]["graph_identity"]
    backend = experiment["backend"]
    live_identity = live_backend_identity(parts.base)
    assert backend["index_identity"] != live_identity.index_identity
    assert backend["store_path"] != live_identity.store_path
    assert Path(backend["store_path"]).is_relative_to((parts.root / "exp-a" / "output").resolve())
    # The context Engine ran the graph; the live Engine never did.
    assert len(parts.builder.engines) == 1 and len(parts.builder.engines[0].runs) == 1
    assert live.runs == []
    assert parts.builder.calls[0].lancedb_uri == backend["store_path"]
    result = client.get(f"/v1/runs/{run['run_id']}/result", headers=header).json()["result"]
    rows = result["outputs"]["context"]
    assert rows and all(row["text"].startswith("exp text") for row in rows)
    assert parts.experiments.registry.active_leases(context_id) == 0


def test_bound_bearer_cannot_touch_the_live_library(setup: Any, live: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    header = bound_bearer(client, context_id)
    revision_id = save_revision(client)
    refused = submit(client, revision_id, headers=header)
    assert refused.status_code == 403
    assert refused.json() == {
        "status": "error",
        "code": "live_library_target",
        "message": "An experiment credential cannot run graphs against the live library.",
        "context_id": context_id,
    }
    assert client.get("/v1/runs").json()["runs"] == []  # no run record was written
    for method, path, body in (
        ("get", "/v1/collections", None),
        ("get", "/v1/collections/docs/documents", None),
        ("post", "/v1/collections/docs/search", {"query": "x"}),
        ("post", "/v1/collections/docs/answer", {"query": "x"}),
    ):
        response = client.request(method, path, json=body, headers={**ORIGIN, **header})
        assert response.status_code == 403, path
        assert "live library" in response.json()["message"]
    assert live.runs == [] and parts.builder.engines == []


def test_bound_bearer_cannot_select_another_context(setup: Any) -> None:
    client, parts = setup
    first = register(client, parts.root, "exp-a")["experiment"]["context_id"]
    second = register(client, parts.root, "exp-b")["experiment"]["context_id"]
    header = bound_bearer(client, first)
    response = submit(client, save_revision(client), context=second, headers=header)
    assert response.status_code == 403
    assert response.json()["code"] == "experiment_scope_mismatch"
    assert parts.builder.engines == []  # refused before any Engine build


def test_unbound_bearer_cannot_select_a_context(setup: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    token = parts.policy.issue_bearer({"run", "read"}).token
    response = submit(
        client,
        save_revision(client),
        context=context_id,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "experiment_credential_required"


def test_revoked_context_refuses_the_next_run(setup: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    header = bound_bearer(client, context_id)
    revision_id = save_revision(client)
    first = submit(client, revision_id, context=context_id, headers=header)
    assert wait_run(client, first.json()["run"]["run_id"], header)["status"] == "succeeded"
    client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    again = submit(client, revision_id, context=context_id, headers=header)
    assert again.status_code == 403
    assert again.json()["code"] == "experiment_context_revoked"
    assert parts.builder.engines[0]._closed  # last lease released, Engine closed


def test_context_revoked_while_queued_fails_before_the_engine_runs(setup: Any, live: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    revision_id = save_revision(client)
    gate = live.hold()
    blocker = submit(client, revision_id).json()["run"]["run_id"]
    assert live.started.wait(5)
    queued = submit(client, revision_id, context=context_id).json()["run"]["run_id"]
    client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    gate.set()
    assert wait_run(client, blocker)["status"] == "succeeded"
    run = wait_run(client, queued)
    assert run["status"] == "failed"
    assert "experiment_context_revoked" in str(run["failure"]) or "revoked" in str(run["failure"])
    assert parts.builder.engines[0].runs == []


def test_session_can_run_live_and_experiment_graphs(setup: Any, live: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    revision_id = save_revision(client)
    live_run = wait_run(client, submit(client, revision_id).json()["run"]["run_id"])
    exp_run = wait_run(
        client, submit(client, revision_id, context=context_id).json()["run"]["run_id"]
    )
    assert live_run["status"] == exp_run["status"] == "succeeded"
    assert "experiment" not in live_run["resources"]
    assert exp_run["resources"]["experiment"]["context_id"] == context_id
    assert len(live.runs) == 1 and len(parts.builder.engines[0].runs) == 1


def test_bound_bearer_sees_only_its_context_runs(setup: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    header = bound_bearer(client, context_id)
    revision_id = save_revision(client)
    live_run = wait_run(client, submit(client, revision_id).json()["run"]["run_id"])
    own = wait_run(
        client,
        submit(client, revision_id, context=context_id, headers=header).json()["run"]["run_id"],
        header,
    )
    listed = client.get("/v1/runs", headers=header).json()["runs"]
    assert [run["run_id"] for run in listed] == [own["run_id"]]
    for suffix in ("", "/result", "/events"):
        hidden = client.get(f"/v1/runs/{live_run['run_id']}{suffix}", headers=header)
        assert hidden.status_code == 404, suffix
    assert len(client.get("/v1/runs").json()["runs"]) == 2  # the session sees both


def test_cancelled_queued_run_releases_and_retry_stays_in_context(setup: Any, live: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    header = bound_bearer(client, context_id)
    revision_id = save_revision(client)
    gate = live.hold()
    blocker = submit(client, revision_id).json()["run"]["run_id"]
    assert live.started.wait(5)
    queued = submit(client, revision_id, context=context_id, headers=header).json()["run"]["run_id"]
    cancelled = client.post(f"/v1/runs/{queued}/cancel", headers={**ORIGIN, **header})
    assert cancelled.json()["run"]["status"] == "cancelled"
    assert parts.experiments.registry.active_leases(context_id) == 0
    gate.set()
    wait_run(client, blocker)
    retried = client.post(f"/v1/runs/{queued}/retry", headers={**ORIGIN, **header})
    assert retried.status_code == 202, retried.text
    run = wait_run(client, retried.json()["run"]["run_id"], header)
    assert run["status"] == "succeeded"
    assert run["resources"]["experiment"]["context_id"] == context_id
    assert len(live.runs) == 1  # only the session's blocker ran live


def test_run_that_started_finishes_after_revocation(setup: Any) -> None:
    client, parts = setup
    context_id = register(client, parts.root)["experiment"]["context_id"]
    revision_id = save_revision(client)
    parts.experiments.engine(context_id)  # build the context Engine to hold its gate
    engine = parts.builder.engines[0]
    gate = engine.hold()
    run_id = submit(client, revision_id, context=context_id).json()["run"]["run_id"]
    assert engine.started.wait(5)
    client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    assert not engine._closed  # the running job still holds its lease
    assert parts.experiments.registry.active_leases(context_id) == 1
    gate.set()
    assert wait_run(client, run_id)["status"] == "succeeded"
    assert engine._closed and parts.experiments.registry.active_leases(context_id) == 0
