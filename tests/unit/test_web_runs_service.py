"""Tests for the run-service composition of ``omrg web`` (task 6.6).

Covers the exclusive workspace lock, the CLI wiring (run-service factory
and the signal hook that closes admission before the connection drain),
document jobs on the shared run-service queue, and previewed workspace
cleanup.
"""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    login,
    make_engine,
    save_revision,
    submit,
    wait_run,
)
from typer.testing import CliRunner  # noqa: E402

from omrg.transports.api.lifespan import WorkspaceLock, WorkspaceLocked  # noqa: E402
from omrg.transports.api.runs_wiring import WorkspaceRuns  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402

runner = CliRunner()


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


# ── Workspace lock ───────────────────────────────────────────────────────


def test_workspace_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    first = WorkspaceLock.acquire(tmp_path / "ws")
    with pytest.raises(WorkspaceLocked, match="different --workspace"):
        WorkspaceLock.acquire(tmp_path / "ws")
    first.release()
    first.release()  # safe twice
    WorkspaceLock.acquire(tmp_path / "ws").release()
    assert (tmp_path / "ws" / ".lock").stat().st_mode & 0o777 == 0o600


def test_second_server_on_the_same_workspace_does_not_start(
    tmp_path: Path, engine: Any, effective_settings: Any
) -> None:
    app, _ = build_app(tmp_path, engine)
    other, _ = build_app(tmp_path, make_engine(effective_settings))
    with TestClient(app, base_url=BASE):
        with pytest.raises(WorkspaceLocked), TestClient(other, base_url=BASE):
            pass
    # The first server released the lock at shutdown.
    with TestClient(other, base_url=BASE) as client:
        assert client.get("/v1/health").status_code == 200


def test_cli_refuses_a_locked_workspace_on_stderr(tmp_path: Path) -> None:
    held = WorkspaceLock.acquire(tmp_path / "ws")
    try:
        with patch("omrg.transports.cli.web._serve") as serve:
            # --port 0: a login item on this machine can hold the default port 8765.
            result = runner.invoke(
                cli_app, ["web", "--port", "0", "--workspace", str(tmp_path / "ws")]
            )
    finally:
        held.release()
    assert result.exit_code == 1
    assert "Another OMRG web server is using the workspace" in result.stderr
    assert result.stdout == ""
    serve.assert_not_called()


def test_cli_wires_the_workspace_run_service(tmp_path: Path, engine: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_serve(application: Any, sock: Any) -> None:
        captured["app"] = application
        sock.close()

    with (
        patch("omrg.transports.cli.web._serve", side_effect=fake_serve),
        patch("omrg.transports.api.app.default_engine_factory", return_value=engine),
    ):
        result = runner.invoke(cli_app, ["web", "--port", "0", "--workspace", str(tmp_path / "ws")])
        assert result.exit_code == 0, result.output
        application = captured["app"]
        with TestClient(application, base_url=BASE):
            assert isinstance(application.state.runtime.run_service, WorkspaceRuns)
    assert (tmp_path / "ws" / "workspace.db").exists()


def test_signal_closes_admission_before_the_server_drains(tmp_path: Path) -> None:
    import socket

    from omrg.transports.cli import web as web_cli

    seen: list[str] = []

    def fake_run(self: Any, sockets: Any = None) -> None:
        self.handle_exit(signal.SIGINT, None)
        seen.append(f"should_exit={self.should_exit}")

    sock = socket.socket()
    try:
        with (
            patch("uvicorn.Server.run", fake_run),
            patch("omrg.transports.api.security.install_log_redaction"),
            patch(
                "omrg.transports.api.lifespan.request_shutdown",
                side_effect=lambda app: seen.append("request_shutdown"),
            ),
        ):
            web_cli._serve(object(), sock)
    finally:
        sock.close()
    assert seen == ["request_shutdown", "should_exit=True"]


# ── Document jobs share the run service ──────────────────────────────────


def test_jobs_and_graph_runs_share_one_bounded_queue(tmp_path: Path, engine: Any) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    app, policy = build_app(tmp_path, engine, roots=(root,))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        gate = engine.hold()
        revision = save_revision(client)
        submit(client, revision["revision_id"])
        assert engine.started.wait(5)
        for _ in range(16):
            assert submit(client, revision["revision_id"]).status_code == 202
        job = client.post("/v1/ingestions", json={"path": str(root)}, headers=ORIGIN)
        gate.set()
    assert job.status_code == 429
    assert job.json()["status"] == "error"


def test_jobs_are_persisted_and_hidden_from_graph_listings(
    tmp_path: Path, engine: Any, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    calls: list[tuple[str, str]] = []

    async def ingest(path: str, *, collection_name: str) -> dict[str, Any]:
        calls.append((path, collection_name))
        return {"status": "ok", "files_processed": 2}

    monkeypatch.setattr(engine, "ingest", ingest)
    workspace = tmp_path / "ws"
    app, policy = build_app(tmp_path, engine, workspace=workspace, roots=(root,))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        job = client.post("/v1/ingestions", json={"path": str(root)}, headers=ORIGIN).json()
        status = wait_job(client, job["job_id"])
        assert status["result"] == {"status": "ok", "files_processed": 2}
        assert client.get("/v1/pipelines").json()["pipelines"] == []
        assert client.get("/v1/runs").json()["runs"] == []
        hex_id = job["job_id"].replace("-", "")
        assert client.get(f"/v1/runs/{hex_id}").status_code == 404
        assert client.post(f"/v1/runs/{hex_id}/retry", headers=ORIGIN).status_code == 404
        # A graph submission cannot start a job revision (that would skip the grant check).
        job_revision = client.get(f"/v1/runs/{hex_id}").json()  # hidden, so look it up directly
        assert job_revision["status"] == "error"
        repository = app.state.runtime.run_service.service.repository
        revision_id = repository.get_run(hex_id)["revision_id"]
        smuggled = submit(client, revision_id, path="/etc", collection="documents")
        assert smuggled.status_code == 404
    again, policy = build_app(tmp_path, make_engine(effective_settings), workspace=workspace)
    with TestClient(again, base_url=BASE) as client:
        login(client, policy)
        after_restart = client.get(f"/v1/jobs/{job['job_id']}").json()
    assert after_restart == status
    assert calls == [(str(root.resolve()), "documents")]


def wait_job(client: Any, job_id: str) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + 10
    while True:
        body = client.get(f"/v1/jobs/{job_id}").json()
        if body["status"] in {"completed", "failed"}:
            return body
        assert time.monotonic() < deadline, body
        time.sleep(0.02)


def test_graph_runs_are_not_jobs(tmp_path: Path, engine: Any) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        revision = save_revision(client)
        run = wait_run(client, submit(client, revision["revision_id"]).json()["run"]["run_id"])
        assert client.get(f"/v1/jobs/{run['run_id']}").status_code == 404
        assert client.get("/v1/jobs/not-a-uuid").status_code == 404


# ── Previewed workspace cleanup ──────────────────────────────────────────


@pytest.fixture
def two_runs(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.policy = policy  # type: ignore[attr-defined]
        revision = save_revision(client)
        ids = [
            wait_run(client, submit(client, revision["revision_id"]).json()["run"]["run_id"])[
                "run_id"
            ]
            for _ in range(2)
        ]
        yield client, ids


def _preview(client: Any, selector: dict[str, Any]) -> Any:
    return client.post("/v1/workspace/cleanup/preview", json={"selector": selector}, headers=ORIGIN)


def test_cleanup_removes_exactly_the_previewed_runs(two_runs: Any) -> None:
    client, (first, second) = two_runs
    preview = _preview(client, {"run_id": first})
    assert preview.status_code == 200, preview.text
    body = preview.json()["preview"]
    assert [run["run_id"] for run in body["runs"]] == [first]
    assert body["totals"]["runs"] == 1 and body["token"].startswith("wc_")
    assert client.get(f"/v1/runs/{first}").status_code == 200  # nothing removed yet
    applied = client.post("/v1/workspace/cleanup", json={"token": body["token"]}, headers=ORIGIN)
    assert applied.status_code == 200, applied.text
    result = applied.json()["result"]
    assert result["runs_removed"] == 1 and result["events_removed"] == body["totals"]["events"]
    assert client.get(f"/v1/runs/{first}").status_code == 404
    assert client.get(f"/v1/runs/{second}").status_code == 200


def test_cleanup_token_is_single_use_and_bound_to_the_selector(two_runs: Any) -> None:
    client, (first, _) = two_runs
    token = _preview(client, {"statuses": ["succeeded"]}).json()["preview"]["token"]
    wrong = client.post(
        "/v1/workspace/cleanup",
        json={"token": token, "selector": {"run_id": first}},
        headers=ORIGIN,
    )
    assert wrong.status_code == 409
    assert "Preview again" in wrong.json()["message"]
    used = client.post("/v1/workspace/cleanup", json={"token": token}, headers=ORIGIN)
    assert used.status_code == 409  # every call spends the token
    assert client.get(f"/v1/runs/{first}").status_code == 200


def test_cleanup_refusals(two_runs: Any) -> None:
    client, _ = two_runs
    assert _preview(client, {}).status_code == 422  # no criterion
    assert _preview(client, {"statuses": ["running"]}).status_code == 422
    assert _preview(client, {"run_id": "nope"}).status_code == 404
    client.cookies.clear()
    notebook = bearer(client.policy, "read", "run", "graph")
    response = client.post(
        "/v1/workspace/cleanup/preview",
        json={"selector": {"statuses": ["succeeded"]}},
        headers=notebook,
    )
    assert response.status_code == 403
