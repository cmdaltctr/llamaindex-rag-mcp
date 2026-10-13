"""Per-launch environment of an owned editor: the connection-file variable only (task 8.6).

The launcher passes the allow-listed inherited variables plus a per-launch
``OMRG_CONNECTION_FILE``. No other per-launch name is accepted, and no
secret may appear in a per-launch value. The variable never leaks in from
the server's own environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tests.unit.test_process_launcher_support import free_port, make_fake_editor, read_record

from omrg.integrations import process_launcher
from omrg.integrations.process_launcher import OwnedProcessLauncher

HOST = "127.0.0.1"
TOKEN = "editor-token-value"  # noqa: S105 - test value
BEARER = "omrg_bt_abc.def-bearer-value"  # noqa: S105 - test value


@pytest.fixture
def launcher(tmp_path: Path):
    owned = OwnedProcessLauncher(
        tmp_path / "runtime",
        grace_seconds=1.0,
        ready_timeout=10.0,
        environment={**os.environ, "OMRG_CONNECTION_FILE": "/server/own/value"},
    )
    yield owned
    owned.stop_all()


def _start(
    launcher: OwnedProcessLauncher,
    tool: Path,
    tmp_path: Path,
    *,
    connection: bool = True,
    extra: dict[str, str] | None = None,
) -> tuple[str, Path]:
    workdir = launcher.create_launch_dir()
    notebook = tmp_path / "nb.py"
    notebook.write_text("import marimo\n")
    port = free_port()
    argv = [
        str(tool), "edit", str(notebook), "--host", HOST, "--port", str(port),
        "--token-password-file", str(workdir / "access-token"),
    ]  # fmt: skip
    details = {
        "api_url": "http://127.0.0.1:8765",
        "experiment_context": "exp_1",
        "token_file": str(workdir / "omrg-api-token"),
    }
    files = {
        "access-token": TOKEN,
        "omrg_connection.json": json.dumps(details),
        "omrg-api-token": BEARER,
    }
    environment = dict(extra or {})
    if connection:
        environment["OMRG_CONNECTION_FILE"] = str(workdir / "omrg_connection.json")
    launch_id = launcher.start(
        argv=argv,
        workdir=workdir,
        host=HOST,
        port=port,
        files=files,
        secrets=[TOKEN, BEARER],
        environment=environment,
    )
    return launch_id, workdir


def test_connection_variable_is_in_the_per_launch_allow_list_only() -> None:
    assert process_launcher.LAUNCH_ENV_ALLOWLIST == ("OMRG_CONNECTION_FILE",)
    assert "OMRG_CONNECTION_FILE" not in process_launcher.ENV_ALLOWLIST


def test_per_launch_connection_file_reaches_the_editor(
    launcher: OwnedProcessLauncher, tmp_path: Path
) -> None:
    tool = make_fake_editor(tmp_path / "tool")
    launch_id, workdir = _start(launcher, tool, tmp_path)
    path = workdir / "omrg_connection.json"
    record = read_record(tool.parent)
    assert record["env"]["OMRG_CONNECTION_FILE"] == str(path)
    assert record["connection_mode"] == 0o600 and record["api_token_mode"] == 0o600
    assert record["api_token"] == BEARER
    assert BEARER not in json.dumps(record["env"]) + json.dumps(record["argv"])
    assert BEARER not in json.dumps(record["connection"])
    assert BEARER not in "".join(launcher.recent_output(launch_id))
    launcher.stop(launch_id)
    assert not path.exists() and not workdir.exists()


def test_server_value_of_the_variable_is_not_inherited(
    launcher: OwnedProcessLauncher, tmp_path: Path
) -> None:
    tool = make_fake_editor(tmp_path / "tool")
    launch_id, _ = _start(launcher, tool, tmp_path, connection=False)
    record = read_record(tool.parent)
    assert "OMRG_CONNECTION_FILE" not in record["env"]
    launcher.stop(launch_id)


@pytest.mark.parametrize(
    "extra",
    [
        {"OMRG_API_URL": "http://127.0.0.1:1"},
        {"PATH": "/tmp/evil"},
        {"OMRG_CONNECTION_FILE": f"/tmp/{BEARER}"},
        {"OMRG_CONNECTION_FILE": "/tmp/a\x00b"},
    ],
)
def test_unsafe_per_launch_environment_is_refused(
    launcher: OwnedProcessLauncher, tmp_path: Path, extra: dict[str, str]
) -> None:
    tool = make_fake_editor(tmp_path / "tool")
    with pytest.raises(ValueError, match="environment|secret"):
        _start(launcher, tool, tmp_path, connection=False, extra=extra)
    assert launcher.owned_ids() == []
    assert not (tool.parent / "record.json").exists()
