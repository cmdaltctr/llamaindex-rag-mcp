"""Open editor delivers a private connection file to the editor (task 8.6).

The production plugin host runs the fake marimo executable. The fake reads
``OMRG_CONNECTION_FILE`` from its environment and records what it sees.
The test then proves that the connection file and the API token file are
private (mode 600) and outside the experiment workspace, that the API
credential is new, bound to the experiment context and able to run a graph
there, and that no token reaches argv, the environment or the log. Stop
and application shutdown each delete both files and revoke the credential.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_plugin_marimo_manifest import MANIFEST  # noqa: E402
from tests.unit.test_process_launcher_support import (  # noqa: E402
    free_port,
    make_fake_editor,
    read_record,
    wait_gone,
)
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
    register,
    save_revision,
    submit,
    wait_run,
)
from tests.unit.test_web_plugins_launch import _kill_leftover  # noqa: E402
from tests.unit.test_web_runs_support import make_engine  # noqa: E402


@pytest.fixture
def lab(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    exe = make_fake_editor(tmp_path / "tool")
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    parts = build_experiment_app(
        tmp_path, make_engine(effective_settings), effective_settings, plugin_ports=(free_port(),)
    )
    try:
        yield parts, exe
    finally:
        _kill_leftover(exe.parent)


def _open(client: TestClient, parts: Any, exe: Path) -> tuple[dict[str, Any], str]:
    login(client, parts.policy)
    body = {"manifest_path": str(MANIFEST), "executable_path": str(exe), "approved": True}
    assert client.post("/v1/plugins", json=body, headers=ORIGIN).status_code == 201
    assert client.post("/v1/plugins/marimo/recheck", headers=ORIGIN).status_code == 200
    context_id = register(client, parts.root, actions=["read"])["experiment"]["context_id"]
    (parts.root / "exp-a" / "study.py").write_text("import marimo\napp = marimo.App()\n")
    opened = client.post(
        "/v1/plugins/marimo/editors",
        json={"notebook": "study.py", "experiment_context": context_id, "consent": True},
        headers=ORIGIN,
    )
    assert opened.status_code == 201, opened.text
    return opened.json(), context_id


def _check_files(record: dict[str, Any], parts: Any, context_id: str) -> tuple[Path, Path]:
    connection = Path(record["connection_path"])
    token_file = Path(record["connection"]["token_file"])
    assert connection.name == "omrg_connection.json"
    assert record["connection_mode"] == 0o600 and record["api_token_mode"] == 0o600
    assert token_file.parent == connection.parent
    launch_dir = connection.parent.resolve()
    assert launch_dir.is_relative_to((parts.root.parent / "ws" / "run" / "editors").resolve())
    assert not launch_dir.is_relative_to(parts.root.resolve())  # not in the experiment
    assert record["connection"] == {
        "api_url": "http://127.0.0.1:8765",
        "experiment_context": context_id,
        "token_file": str(token_file),
    }
    return connection, token_file


def test_editor_gets_a_private_bound_connection_until_stop(
    lab: Any, caplog: pytest.LogCaptureFixture
) -> None:
    parts, exe = lab
    caplog.set_level(logging.DEBUG)
    with TestClient(parts.app, base_url=BASE) as client:
        opened, context_id = _open(client, parts, exe)
        record = read_record(exe.parent)
        connection, token_file = _check_files(record, parts, context_id)
        bearer = record["api_token"]
        assert bearer.startswith("omrg_bt_")
        assert bearer != opened["token_delivery"]["token"]
        assert bearer not in json.dumps(record["argv"]) + json.dumps(record["env"])
        assert bearer not in json.dumps(opened)
        # A new credential, bound to the context, with the notebook scopes.
        listed = client.get("/v1/credentials").json()["credentials"]
        assert len(listed) == 1
        assert listed[0]["experiment_context"] == context_id
        assert listed[0]["scopes"] == ["graph", "read", "run"] and not listed[0]["revoked"]
        # It runs a graph in its experiment context.
        header = {"Authorization": f"Bearer {bearer}"}
        response = submit(client, save_revision(client), context=context_id, headers=header)
        assert response.status_code == 202, response.text
        run = wait_run(client, response.json()["run"]["run_id"], header)
        assert run["status"] == "succeeded", run["failure"]
        assert run["resources"]["experiment"]["context_id"] == context_id
        # Stop deletes both files and revokes the credential.
        stopped = client.delete(f"/v1/plugin-editors/{opened['launch_id']}", headers=ORIGIN)
        assert stopped.status_code == 200
        assert wait_gone(record["pid"])
        assert not connection.exists() and not token_file.exists()
        assert client.get("/v1/runs", headers=header).status_code == 401
        assert client.get("/v1/credentials").json()["credentials"][0]["revoked"] is True
    assert bearer not in caplog.text


def test_application_shutdown_revokes_and_deletes(lab: Any) -> None:
    parts, exe = lab
    with TestClient(parts.app, base_url=BASE) as client:
        _, context_id = _open(client, parts, exe)
        record = read_record(exe.parent)
        connection, token_file = _check_files(record, parts, context_id)
        bearer = record["api_token"]
        assert parts.policy.authenticate_bearer(bearer) is not None
    assert wait_gone(record["pid"])
    assert not connection.exists() and not token_file.exists()
    assert parts.policy.authenticate_bearer(bearer) is None
