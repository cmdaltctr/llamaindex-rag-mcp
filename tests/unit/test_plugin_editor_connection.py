"""Editor launch plan with an OMRS connection file (task 8.6).

When the caller gives an :class:`EditorConnection`, the plan adds two
private files to the launch directory (the connection file and a separate
API token file) and one per-launch variable, ``OMRS_CONNECTION_FILE``,
that names the connection file. The API token is only in the token file.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_plugin_editor import setup, supervisor  # noqa: F401 - fixture

from omrs.core.plugins.editor import (
    API_TOKEN_FILE_NAME,
    CONNECTION_ENV,
    CONNECTION_FILE_NAME,
    EditorConnection,
)

BEARER = "omrs_bt_0123.bearer-for-test"  # noqa: S105 - test value
CONNECTION = EditorConnection("http://127.0.0.1:8765", "exp_abc", BEARER)


def test_connection_names_are_fixed() -> None:
    assert (CONNECTION_FILE_NAME, API_TOKEN_FILE_NAME, CONNECTION_ENV) == (
        "omrs_connection.json",
        "omrs-api-token",
        "OMRS_CONNECTION_FILE",
    )


def test_open_with_connection_writes_private_files_and_one_variable(setup) -> None:  # noqa: F811
    registry, launcher, notebook, _ = setup
    session = supervisor(registry, launcher).open(
        "fakeedit", notebook, consent=True, connection=CONNECTION
    )
    call = launcher.started[0]
    workdir = call["workdir"]
    assert call["environment"] == {CONNECTION_ENV: str(workdir / CONNECTION_FILE_NAME)}
    details = json.loads(call["files"][CONNECTION_FILE_NAME])
    assert details == {
        "api_url": "http://127.0.0.1:8765",
        "experiment_context": "exp_abc",
        "token_file": str(workdir / API_TOKEN_FILE_NAME),
    }
    assert call["files"][API_TOKEN_FILE_NAME] == BEARER
    assert BEARER not in call["files"][CONNECTION_FILE_NAME]
    assert sorted(call["secrets"]) == sorted(["T0KEN", BEARER])
    assert not any(BEARER in arg for arg in call["argv"])
    assert BEARER not in repr(CONNECTION) and BEARER not in repr(session)


def test_open_without_connection_adds_nothing(setup) -> None:  # noqa: F811
    registry, launcher, notebook, _ = setup
    supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    call = launcher.started[0]
    assert call["environment"] == {}
    assert CONNECTION_FILE_NAME not in call["files"]
    assert API_TOKEN_FILE_NAME not in call["files"]


def test_each_port_attempt_names_its_own_launch_directory(setup) -> None:  # noqa: F811
    registry, launcher, notebook, _ = setup
    launcher.race = {41001}
    supervisor(registry, launcher).open("fakeedit", notebook, consent=True, connection=CONNECTION)
    call = launcher.started[0]
    assert call["port"] == 41002
    path = Path(call["environment"][CONNECTION_ENV])
    assert path.parent == call["workdir"]
    assert json.loads(call["files"][CONNECTION_FILE_NAME])["token_file"].startswith(
        str(call["workdir"])
    )
