"""The per-file upload limit as a workspace setting and a launch option (design D4).

Tasks 3.2 and 3.3 of add-run-output-inspection-and-upload-limit: the
``/v1/settings/upload-limit`` routes, the startup order (launch, then
saved, then default), the single-read limit of an upload in progress and
``omrg web --max-upload-mib`` with ``WEB_MAX_UPLOAD_MIB``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from omrg.core.workspace import WorkspaceLayout  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402
from omrg.transports.api.uploads import UploadStore  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
MIB = 1024 * 1024
URL = "/v1/settings/upload-limit"
LAUNCH_MESSAGE = (
    "The upload limit was set when the server started. Remove --max-upload-mib or "
    "WEB_MAX_UPLOAD_MIB and restart to change it here."
)
runner = CliRunner()


class FakeEngine:
    def close(self) -> None:
        return None


def _app(workspace: Path, launch_mib: int | None = None) -> tuple[Any, AccessPolicy]:
    config = WebConfig(
        workspace=workspace, port=8765, static_dir=None, launch_upload_limit_mib=launch_mib
    )
    policy = AccessPolicy.for_launch("127.0.0.1", 8765)
    return create_app(config, policy=policy, engine_factory=FakeEngine), policy


def _client(workspace: Path, launch_mib: int | None = None) -> Any:
    app, policy = _app(workspace, launch_mib)
    client = TestClient(app, base_url=BASE)
    client.__enter__()
    response = client.post(
        "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text
    client.policy = policy  # type: ignore[attr-defined]
    return client


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


@pytest.fixture
def web(workspace: Path) -> Any:
    client = _client(workspace)
    yield client
    client.__exit__(None, None, None)


def _saved(workspace: Path) -> int | None:
    return WorkspaceSettings(WorkspaceLayout(workspace).records).get_upload_limit_mib()


def _save(workspace: Path, mib: int) -> None:
    records = WorkspaceLayout(workspace).records
    SqliteWorkspaceRepository(records)
    WorkspaceSettings(records).set_upload_limit_mib(mib)


def _state(max_mib: int, source: str, saved: int | None) -> dict[str, Any]:
    return {
        "status": "ok",
        "max_bytes": max_mib * MIB,
        "source": source,
        "saved_mib": saved,
        "default_mib": 50,
        "min_mib": 1,
        "max_mib": 2048,
    }


def _preflight(client: Any, size: int) -> Any:
    return client.post("/v1/uploads/preflight", json={"name": "a.md", "size": size}, headers=ORIGIN)


# ── 3.2 Settings routes ──────────────────────────────────────────────────


def test_get_reports_the_default_and_the_range(web: Any) -> None:
    response = web.get(URL)
    assert response.status_code == 200, response.text
    assert response.json() == _state(50, "default", None)


def test_put_applies_at_once_and_survives_a_restart(web: Any, workspace: Path) -> None:
    assert _preflight(web, 120 * MIB).status_code == 413
    response = web.put(URL, json={"max_mib": 200}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.json() == _state(200, "saved", 200)
    assert _preflight(web, 120 * MIB).status_code == 200
    assert _saved(workspace) == 200
    web.__exit__(None, None, None)
    again = _client(workspace)
    try:
        assert again.get(URL).json() == _state(200, "saved", 200)
        assert _preflight(again, 120 * MIB).status_code == 200
    finally:
        again.__exit__(None, None, None)


def test_put_null_returns_to_the_default(web: Any, workspace: Path) -> None:
    web.put(URL, json={"max_mib": 200}, headers=ORIGIN)
    response = web.put(URL, json={"max_mib": None}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.json() == _state(50, "default", None)
    assert _saved(workspace) is None
    assert _preflight(web, 51 * MIB).status_code == 413


@pytest.mark.parametrize(
    "body",
    [
        {"max_mib": 0},
        {"max_mib": 4096},
        {"max_mib": 1.5},
        {"max_mib": "10"},
        {"max_mib": 10, "extra": 1},
        {},
    ],
)
def test_put_rejects_invalid_values_and_changes_nothing(
    web: Any, workspace: Path, body: dict
) -> None:
    web.put(URL, json={"max_mib": 200}, headers=ORIGIN)
    response = web.put(URL, json=body, headers=ORIGIN)
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert web.get(URL).json() == _state(200, "saved", 200)
    assert _saved(workspace) == 200


def test_a_bearer_can_read_but_not_change_the_limit(web: Any, workspace: Path) -> None:
    web.cookies.clear()
    every_scope = {
        "Authorization": f"Bearer {web.policy.issue_bearer({'graph', 'read', 'run'}).token}"
    }
    assert web.get(URL, headers=every_scope).status_code == 200
    refused = web.put(URL, json={"max_mib": 200}, headers=every_scope)
    assert refused.status_code == 403
    assert _saved(workspace) is None


def test_a_failed_save_changes_nothing(web: Any, workspace: Path) -> None:
    runtime = web.app.state.runtime
    with (
        patch.object(WorkspaceSettings, "set_upload_limit_mib", side_effect=OSError("disk")),
        pytest.raises(OSError),
    ):
        web.put(URL, json={"max_mib": 200}, headers=ORIGIN)
    assert runtime.uploads.max_bytes == 50 * MIB
    assert web.get(URL).json() == _state(50, "default", None)


# ── 3.2 Upload in progress ───────────────────────────────────────────────


async def test_an_upload_in_progress_keeps_its_start_limit(tmp_path: Path) -> None:
    store = UploadStore(tmp_path / "uploads", max_bytes=100)
    store.prepare()

    async def lowered_midway() -> AsyncIterator[bytes]:
        yield b"x" * 40
        store.max_bytes = 10
        yield b"x" * 40

    record = await store.receive("a.md", lowered_midway(), None, [".md"])
    assert record["size"] == 80

    async def next_upload() -> AsyncIterator[bytes]:
        yield b"x" * 40

    with pytest.raises(Exception, match="10 byte"):
        await store.receive("b.md", next_upload(), None, [".md"])


# ── 3.3 Launch option ────────────────────────────────────────────────────


def test_a_launch_value_beats_the_saved_value_and_locks_settings(workspace: Path) -> None:
    _save(workspace, 200)
    client = _client(workspace, launch_mib=400)
    try:
        assert client.get(URL).json() == _state(400, "launch", 200)
        refused = client.put(URL, json={"max_mib": 100}, headers=ORIGIN)
        assert refused.status_code == 409
        assert refused.json()["message"] == LAUNCH_MESSAGE
        assert client.get(URL).json() == _state(400, "launch", 200)
        assert _saved(workspace) == 200
        assert _preflight(client, 300 * MIB).status_code == 200
    finally:
        client.__exit__(None, None, None)


def _launch(workspace: Path, *args: str, env: dict[str, str] | None = None) -> tuple[Any, Any]:
    """Run ``omrg web`` with the bind, the app and the server replaced."""
    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)
    with (
        patch("omrg.transports.cli.web._bind_socket", return_value=sock) as bind,
        patch("omrg.transports.cli.web._serve", return_value=True),
        patch("omrg.transports.api.app.create_app") as create,
    ):
        result = runner.invoke(
            cli_app, ["web", "--workspace", str(workspace), *args], env=env or {}
        )
    return result, bind, create


@pytest.mark.parametrize(
    ("args", "env", "expected"),
    [
        (("--max-upload-mib", "400"), {"WEB_MAX_UPLOAD_MIB": "300"}, 400),
        ((), {"WEB_MAX_UPLOAD_MIB": "300"}, 300),
        ((), {}, None),
    ],
)
def test_the_flag_beats_the_environment(
    workspace: Path, args: tuple[str, ...], env: dict[str, str], expected: int | None
) -> None:
    result, _, create = _launch(workspace, *args, env=env)
    assert result.exit_code == 0, result.output
    assert create.call_args.args[0].launch_upload_limit_mib == expected


@pytest.mark.parametrize("value", ["0", "5000", "big"])
def test_an_invalid_environment_value_stops_the_launch(workspace: Path, value: str) -> None:
    result, bind, create = _launch(workspace, env={"WEB_MAX_UPLOAD_MIB": value})
    assert result.exit_code == 2
    assert "WEB_MAX_UPLOAD_MIB" in result.output
    assert "--max-upload-mib" in result.output
    assert "1<=x<=2048" in result.output or "from 1 to 2048" in result.output
    bind.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize("value", ["0", "5000", "big"])
def test_an_invalid_flag_value_stops_the_launch(workspace: Path, value: str) -> None:
    result, bind, _ = _launch(workspace, "--max-upload-mib", value)
    assert result.exit_code == 2
    assert "--max-upload-mib" in result.output
    assert "No such option" not in result.output
    bind.assert_not_called()
