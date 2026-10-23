"""Plugin administration and editor routes with fake tools (tasks 8.5, 8.6).

The plugin host uses the real ``PluginRegistry`` and
``NotebookEditorSupervisor`` over the workspace records, with the fake
probe runner and the fake launcher from the plugin tests: no process
starts and marimo is not installed. Every route is session only
(``plugins`` scope). The editor access token reaches the browser once,
in the open response body, and never appears in the log.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_plugin_editor import FakeLauncher  # noqa: E402
from tests.unit.test_plugin_manifest import valid_manifest  # noqa: E402
from tests.unit.test_plugin_registration import FakeRunner  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
    register,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

from omrs.core.plugins import NotebookEditorSupervisor, PluginRegistry  # noqa: E402
from omrs.core.workspace import WorkspaceLayout  # noqa: E402
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrs.transports.api.lifespan import PluginHost, WebConfig  # noqa: E402

TOKEN = "editor-token-for-test-0123456789"  # noqa: S105 - test value


class Tools:
    """Fake runner, launcher and files that one test application uses."""

    def __init__(self, tmp_path: Path) -> None:
        self.runner = FakeRunner()
        self.launcher = FakeLauncher(tmp_path / "launches")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.exe = self.bin / "fakeedit"
        self.exe.write_text("#!/bin/sh\n")
        self.exe.chmod(0o755)
        self.host: PluginHost | None = None

    def factory(self, config: WebConfig) -> PluginHost:
        repository = SqliteWorkspaceRepository(WorkspaceLayout(config.workspace).records)
        registry = PluginRegistry(repository, self.runner)
        editors = NotebookEditorSupervisor(
            registry, self.launcher, ports=(41001, 41002), token_factory=lambda: TOKEN
        )
        plugin_dir = config.workspace / "plugins"
        self.host = PluginHost(
            repository=repository,
            registry=registry,
            editors=editors,
            manifests=(),
            manifest_dir=plugin_dir,
            executable_dirs=(self.bin, plugin_dir),
        )
        return self.host


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any) -> Any:
    tools = Tools(tmp_path)
    parts = build_experiment_app(
        tmp_path, make_engine(effective_settings), effective_settings, plugins_factory=tools.factory
    )
    manifest = tmp_path / "ws" / "plugins" / "fakeedit.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(valid_manifest()))
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        yield client, parts, tools, manifest


def _register(client: TestClient, manifest: Path, exe: Path, **extra: Any) -> Any:
    body = {"manifest_path": str(manifest), "executable_path": str(exe), "approved": True}
    return client.post("/v1/plugins", json={**body, **extra}, headers=ORIGIN)


def _notebook(parts: Any, client: TestClient) -> tuple[str, Path]:
    context_id = register(client, parts.root)["experiment"]["context_id"]
    notebook = parts.root / "exp-a" / "notebooks" / "study.py"
    notebook.parent.mkdir()
    notebook.write_text("import marimo\napp = marimo.App()\n")
    return context_id, notebook


def test_plugin_routes_are_session_only(setup: Any) -> None:
    client, parts, tools, manifest = setup
    header = {
        "Authorization": f"Bearer {parts.policy.issue_bearer({'graph', 'read', 'run'}).token}"
    }
    assert client.get("/v1/plugins", headers=header).status_code == 403
    assert _register(client, manifest, tools.exe, **{}).status_code == 201  # session
    refused = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": "x.py", "experiment_context": "exp_0", "consent": True},
        headers={**ORIGIN, **header},
    )
    assert refused.status_code == 403
    assert tools.launcher.started == []


def test_list_starts_with_no_plugin_and_explains_installation(setup: Any) -> None:
    client, *_ = setup
    body = client.get("/v1/plugins").json()
    assert body["plugins"] == [] and body["editors"] == []
    assert "outside OMRS" in body["install_hint"]
    assert "filesystem" in body["trust_notice"]


def test_register_needs_explicit_approval_and_runs_nothing(setup: Any) -> None:
    client, _, tools, manifest = setup
    refused = _register(client, manifest, tools.exe, approved=False)
    assert refused.status_code == 403
    created = _register(client, manifest, tools.exe)
    assert created.status_code == 201, created.text
    plugin = created.json()["plugin"]
    assert plugin["name"] == "fakeedit" and plugin["status"] == "unchecked"
    assert plugin["launchable"] is False
    assert tools.runner.calls == []  # registration runs no probe


@pytest.mark.parametrize("where", ["outside", "traversal"])
def test_manifest_must_be_in_an_approved_location(setup: Any, tmp_path: Path, where: str) -> None:
    client, _, tools, manifest = setup
    outside = tmp_path / "elsewhere.json"
    outside.write_text(manifest.read_text())
    path = str(outside) if where == "outside" else f"{manifest.parent}/../../elsewhere.json"
    response = _register(client, Path(path), tools.exe)
    assert response.status_code == 403
    assert "manifest" in response.json()["message"]
    assert client.get("/v1/plugins").json()["plugins"] == []


def test_executable_must_be_in_an_approved_location_and_match_the_manifest(
    setup: Any, tmp_path: Path
) -> None:
    client, _, tools, manifest = setup
    stray = tmp_path / "stray" / "fakeedit"
    stray.parent.mkdir()
    stray.write_text("#!/bin/sh\n")
    stray.chmod(0o755)
    assert _register(client, manifest, stray).status_code == 403
    wrong = tools.bin / "other"
    wrong.write_text("#!/bin/sh\n")
    wrong.chmod(0o755)
    mismatch = _register(client, manifest, wrong)
    assert mismatch.status_code == 400
    assert "fakeedit" in mismatch.json()["message"]


def test_invalid_manifest_is_rejected_without_a_process(setup: Any) -> None:
    client, _, tools, manifest = setup
    data = valid_manifest()
    data["recipes"]["probe"]["version_args"] = ["--version; rm -rf /"]
    manifest.write_text(json.dumps(data))
    response = _register(client, manifest, tools.exe)
    assert response.status_code == 400
    assert "invalid plugin manifest" in response.json()["message"]
    assert tools.runner.calls == []


def test_recheck_probes_and_unregister_removes(setup: Any) -> None:
    client, _, tools, manifest = setup
    _register(client, manifest, tools.exe)
    checked = client.post("/v1/plugins/fakeedit/recheck", headers=ORIGIN)
    assert checked.status_code == 200
    assert checked.json()["plugin"]["status"] == "compatible"
    assert checked.json()["plugin"]["version"] == "1.4.2"
    tools.runner.version = "fakeedit 9.0.0"
    stale = client.post("/v1/plugins/fakeedit/recheck", headers=ORIGIN).json()["plugin"]
    assert stale["status"] == "incompatible" and "outside the tested range" in stale["message"]
    assert client.post("/v1/plugins/missing/recheck", headers=ORIGIN).status_code == 404
    removed = client.delete("/v1/plugins/fakeedit", headers=ORIGIN)
    assert removed.status_code == 200
    assert client.get("/v1/plugins").json()["plugins"] == []
    assert client.delete("/v1/plugins/fakeedit", headers=ORIGIN).status_code == 404


def test_open_editor_gives_the_token_once_and_never_logs_it(
    setup: Any, caplog: pytest.LogCaptureFixture
) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, notebook = _notebook(parts, client)
    caplog.set_level(logging.DEBUG)
    opened = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": "notebooks/study.py", "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert body["token_delivery"] == {"method": "response_body_once", "token": TOKEN}
    assert body["url_without_token"] == "http://127.0.0.1:41001/"  # noqa: S105
    assert TOKEN not in body["url_without_token"]
    assert body["experiment_context"] == context_id
    assert opened.headers["cache-control"] == "no-store"
    started = tools.launcher.started[0]
    assert str(notebook.resolve()) in started["argv"]
    listed = client.get("/v1/plugins").json()
    assert [e["launch_id"] for e in listed["editors"]] == [body["launch_id"]]
    assert TOKEN not in json.dumps(listed)
    assert TOKEN not in caplog.text
    busy = client.delete("/v1/plugins/fakeedit", headers=ORIGIN)
    assert busy.status_code == 409
    stopped = client.delete(f"/v1/plugin-editors/{body['launch_id']}", headers=ORIGIN)
    assert stopped.status_code == 200 and tools.launcher.stopped == [body["launch_id"]]
    assert notebook.exists()
    gone = client.delete(f"/v1/plugin-editors/{body['launch_id']}", headers=ORIGIN)
    assert gone.status_code == 404


def test_open_editor_passes_a_bound_connection_and_stop_revokes_it(setup: Any) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, _ = _notebook(parts, client)
    opened = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": "notebooks/study.py", "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert opened.status_code == 201, opened.text
    started = tools.launcher.started[0]
    assert started["environment"] == {
        "OMRS_CONNECTION_FILE": str(started["workdir"] / "omrs_connection.json")
    }
    details = json.loads(started["files"]["omrs_connection.json"])
    assert details["api_url"] == "http://127.0.0.1:8765"
    assert details["experiment_context"] == context_id
    bearer = started["files"]["omrs-api-token"]
    assert bearer in started["secrets"] and bearer not in json.dumps(opened.json())
    principal = parts.policy.authenticate_bearer(bearer)
    assert principal is not None and principal.experiment_context == context_id
    assert principal.scopes == {"graph", "read", "run"}
    client.delete(f"/v1/plugin-editors/{opened.json()['launch_id']}", headers=ORIGIN)
    assert parts.policy.authenticate_bearer(bearer) is None


def test_failed_open_revokes_the_editor_credential(setup: Any) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, _ = _notebook(parts, client)
    tools.launcher.race = {41001, 41002}
    refused = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": "notebooks/study.py", "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert refused.status_code == 409
    issued = client.get("/v1/credentials").json()["credentials"]
    assert issued and all(item["revoked"] for item in issued)


@pytest.mark.parametrize(
    ("notebook", "status"),
    [("/etc/passwd", 400), ("../exp-a/notebooks/study.py", 400), ("missing.py", 404)],
)
def test_open_editor_keeps_the_notebook_inside_the_workspace(
    setup: Any, notebook: str, status: int
) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, _ = _notebook(parts, client)
    response = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": notebook, "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert response.status_code == status
    assert tools.launcher.started == []


def test_open_editor_needs_consent_and_an_active_context(setup: Any) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, _ = _notebook(parts, client)
    body = {"notebook": "notebooks/study.py", "experiment_context": context_id}
    no_consent = client.post(
        "/v1/plugins/fakeedit/editors", json={**body, "consent": False}, headers=ORIGIN
    )
    assert no_consent.status_code == 403
    client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN)
    revoked = client.post(
        "/v1/plugins/fakeedit/editors", json={**body, "consent": True}, headers=ORIGIN
    )
    assert revoked.status_code == 400
    assert revoked.json()["code"] == "experiment_context_revoked"
    assert tools.launcher.started == []


def test_incompatible_plugin_cannot_open(setup: Any) -> None:
    client, parts, tools, manifest = setup
    _register(client, manifest, tools.exe)
    context_id, _ = _notebook(parts, client)
    tools.runner.version = "fakeedit 0.1.0"
    response = client.post(
        "/v1/plugins/fakeedit/editors",
        json={"notebook": "notebooks/study.py", "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert response.status_code == 409
    assert "outside the tested range" in response.json()["message"]
    assert tools.launcher.started == []


def test_plugin_responses_conform(setup: Any) -> None:
    client, parts, tools, manifest = setup
    check = ContractChecker()
    check.check(client.get("/v1/plugins"), 200)
    check.check(_register(client, manifest, tools.exe, approved=False), 403)
    check.check(_register(client, manifest, tools.exe), 201)
    check.check(client.post("/v1/plugins/fakeedit/recheck", headers=ORIGIN), 200)
    check.check(client.post("/v1/plugins/nope/recheck", headers=ORIGIN), 404)
    context_id, _ = _notebook(parts, client)
    opened = check.check(
        client.post(
            "/v1/plugins/fakeedit/editors",
            json={
                "notebook": "notebooks/study.py",
                "experiment_context": context_id,
                "consent": True,
            },
            headers=ORIGIN,
        ),
        201,
    )
    check.check(client.get("/v1/plugins"), 200)
    check.check(client.delete("/v1/plugins/fakeedit", headers=ORIGIN), 409)
    check.check(client.delete(f"/v1/plugin-editors/{opened['launch_id']}", headers=ORIGIN), 200)
    check.check(client.delete(f"/v1/plugin-editors/{opened['launch_id']}", headers=ORIGIN), 404)
    check.check(client.delete("/v1/plugins/fakeedit", headers=ORIGIN), 200)
    assert check.operations >= FAMILIES["plugins"]
