"""``omrg web`` port selection and the web-port settings API (design D5; tasks 3.1 to 3.3)."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from typer.testing import CliRunner  # noqa: E402

from omrg.core.workspace import WorkspaceLayout  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402
from omrg.transports.cli.web import DEFAULT_PORT, resolve_port  # noqa: E402

runner = CliRunner()


def _save_port(workspace: Path, port: int | None, *, raw: str | None = None) -> None:
    """Create the workspace database and save a port (or a raw stored value)."""
    records = WorkspaceLayout(workspace).records
    SqliteWorkspaceRepository(records)
    if raw is not None:
        import sqlite3

        conn = sqlite3.connect(records)
        conn.execute("INSERT INTO workspace_settings VALUES ('web_port', ?)", (raw,))
        conn.commit()
        conn.close()
    else:
        WorkspaceSettings(records).set_web_port(port)


def _launch(workspace: Path, *args: str) -> tuple[Any, MagicMock]:
    """Run ``omrg web`` with the bind and the server replaced; return result and bind mock."""
    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)
    with (
        patch("omrg.transports.cli.web._bind_socket", return_value=sock) as bind,
        patch("omrg.transports.cli.web._serve", return_value=True),
    ):
        result = runner.invoke(cli_app, ["web", "--workspace", str(workspace), *args])
    return result, bind


# ── 3.1 Resolution order ─────────────────────────────────────────────────


def test_default_port_is_8765() -> None:
    assert DEFAULT_PORT == 8765


@pytest.mark.parametrize(
    ("given", "saved", "expected"),
    [
        (None, None, 8765),
        (None, 9100, 9100),
        (7000, 9100, 7000),
        (7000, None, 7000),
        (0, 9100, 0),
        (0, None, 0),
    ],
)
def test_resolve_port_order(given: int | None, saved: int | None, expected: int) -> None:
    assert resolve_port(given, saved) == expected


def test_launch_without_flag_or_saved_port_binds_8765(tmp_path: Path) -> None:
    result, bind = _launch(tmp_path / "ws")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 8765)


def test_launch_uses_the_saved_port(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(workspace, 9100)
    result, bind = _launch(workspace)
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 9100)


def test_port_flag_wins_over_the_saved_port(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(workspace, 9100)
    result, bind = _launch(workspace, "--port", "7000")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 7000)


def test_port_zero_still_picks_a_free_port(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(workspace, 9100)
    result, bind = _launch(workspace, "--port", "0")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 0)


def test_an_invalid_saved_port_falls_back_to_8765(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(workspace, None, raw="80")
    result, bind = _launch(workspace)
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 8765)


# ── 3.2 Taken port ───────────────────────────────────────────────────────


def test_taken_port_exits_one_with_an_actionable_message(tmp_path: Path) -> None:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    taken = holder.getsockname()[1]
    try:
        with patch("omrg.transports.cli.web._serve") as serve:
            result = runner.invoke(
                cli_app, ["web", "--workspace", str(tmp_path / "ws"), "--port", str(taken)]
            )
    finally:
        holder.close()

    assert result.exit_code == 1
    assert f"Port {taken} is in use" in result.stderr
    assert "--port" in result.stderr
    assert "Settings" in result.stderr
    assert result.stdout == ""
    serve.assert_not_called()


# ── 3.3 Settings API ─────────────────────────────────────────────────────


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.policy = policy  # type: ignore[attr-defined]
        client.workspace = tmp_path / "ws"  # type: ignore[attr-defined]
        yield client


def test_get_reports_saved_and_bound(web: Any) -> None:
    response = web.get("/v1/settings/web-port")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "saved": None, "bound": 8765}


def test_put_saves_the_port_without_rebinding(web: Any) -> None:
    response = web.put("/v1/settings/web-port", json={"port": 9100}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "saved": 9100, "bound": 8765}
    assert web.get("/v1/settings/web-port").json() == {"status": "ok", "saved": 9100, "bound": 8765}
    assert WorkspaceSettings(WorkspaceLayout(web.workspace).records).get_web_port() == 9100


def test_put_null_clears_the_saved_port(web: Any) -> None:
    web.put("/v1/settings/web-port", json={"port": 9100}, headers=ORIGIN)
    response = web.put("/v1/settings/web-port", json={"port": None}, headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "saved": None, "bound": 8765}


@pytest.mark.parametrize("body", [{"port": 1023}, {"port": 65536}, {"port": 0}, {"port": "x"}, {}])
def test_put_rejects_invalid_ports(web: Any, body: dict) -> None:
    response = web.put("/v1/settings/web-port", json=body, headers=ORIGIN)
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert web.get("/v1/settings/web-port").json()["saved"] is None


def test_bearer_can_read_but_not_change_the_port(web: Any) -> None:
    web.cookies.clear()
    read = web.get("/v1/settings/web-port", headers=bearer(web.policy, "read"))
    assert read.status_code == 200
    every_scope = bearer(web.policy, "graph", "read", "run")
    refused = web.put("/v1/settings/web-port", json={"port": 9100}, headers=every_scope)
    assert refused.status_code == 403
    assert WorkspaceSettings(WorkspaceLayout(web.workspace).records).get_web_port() is None


def test_unauthenticated_requests_are_refused(web: Any) -> None:
    web.cookies.clear()
    assert web.get("/v1/settings/web-port").status_code == 401
    assert web.put("/v1/settings/web-port", json={"port": 9100}).status_code == 401


def test_serve_limits_the_graceful_shutdown_wait() -> None:
    """An open MCP event stream must not keep Ctrl+C waiting for ever."""
    from omrg.transports.cli.web import _serve

    with (
        patch("uvicorn.Config") as config,
        patch("uvicorn.Server.run"),
        patch("omrg.transports.api.security.install_log_redaction"),
    ):
        _serve(MagicMock(), MagicMock())
    assert 0 < config.call_args.kwargs["timeout_graceful_shutdown"] <= 10
