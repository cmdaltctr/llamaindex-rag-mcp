"""``omrg web`` port selection and the web-port API (ADR-087: ``web_port`` in ``omrg.jsonc``)."""

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

from omrg.config.settings_file import read_settings_file  # noqa: E402
from omrg.config.user_config import user_config_dir  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402
from omrg.transports.cli.web import DEFAULT_PORT, resolve_port  # noqa: E402

runner = CliRunner()


def _save_port(port: int | None, *, raw: str | None = None) -> None:
    """Write ``web_port`` to ``omrg.jsonc`` (or a raw, possibly invalid, JSON value)."""
    folder = user_config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    value = raw if raw is not None else ("null" if port is None else str(port))
    (folder / "omrg.jsonc").write_text(f'{{ "web_port": {value} }}', encoding="utf-8")


def _file_port() -> object:
    return read_settings_file().values.get("web_port")


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


def test_launch_uses_the_port_in_the_config_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(9100)
    result, bind = _launch(workspace)
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 9100)


def test_port_flag_wins_over_the_config_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(9100)
    result, bind = _launch(workspace, "--port", "7000")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 7000)


def test_port_zero_still_picks_a_free_port(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _save_port(9100)
    result, bind = _launch(workspace, "--port", "0")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 0)


@pytest.mark.parametrize("raw", ["80", "70000", '"9100"', "true", "9100.5"])
def test_an_invalid_port_in_the_file_falls_back_to_8765(tmp_path: Path, raw: str) -> None:
    workspace = tmp_path / "ws"
    _save_port(None, raw=raw)
    result, bind = _launch(workspace)
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 8765)


def test_an_unreadable_file_falls_back_to_8765(tmp_path: Path) -> None:
    folder = user_config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "omrg.jsonc").write_text("{ not json", encoding="utf-8")
    result, bind = _launch(tmp_path / "ws")
    assert result.exit_code == 0, result.output
    assert bind.call_args.args == ("127.0.0.1", 8765)


def test_the_database_no_longer_sets_the_port(tmp_path: Path) -> None:
    import sqlite3

    from omrg.core.workspace import WorkspaceLayout
    from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository

    records = WorkspaceLayout(tmp_path / "ws").records
    SqliteWorkspaceRepository(records)
    conn = sqlite3.connect(records)
    conn.execute("INSERT INTO workspace_settings VALUES ('web_port', '9100')")
    conn.commit()
    conn.close()
    result, bind = _launch(tmp_path / "ws")
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
    assert response.json() == {
        "status": "ok",
        "revision": "absent",
        "saved": None,
        "bound": 8765,
        "differs": False,
    }


def test_put_saves_the_port_without_rebinding(web: Any) -> None:
    response = web.put("/v1/settings/web-port", json={"port": 9100}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["saved"], body["bound"], body["differs"]) == (9100, 8765, True)
    assert body["revision"] == read_settings_file().revision
    assert _file_port() == 9100
    assert '"web_port": 9100' in (user_config_dir() / "omrg.jsonc").read_text(encoding="utf-8")
    assert web.get("/v1/settings/web-port").json() == body


def test_a_hand_edit_of_the_port_is_reported_as_different(web: Any) -> None:
    _save_port(9200)
    body = web.get("/v1/settings/web-port").json()
    assert (body["saved"], body["bound"], body["differs"]) == (9200, 8765, True)


def test_put_null_clears_the_saved_port(web: Any) -> None:
    web.put("/v1/settings/web-port", json={"port": 9100}, headers=ORIGIN)
    response = web.put("/v1/settings/web-port", json={"port": None}, headers=ORIGIN)
    assert response.status_code == 200
    assert (response.json()["saved"], response.json()["differs"]) == (None, False)
    assert _file_port() is None
    assert "web_port" not in (user_config_dir() / "omrg.jsonc").read_text(encoding="utf-8")


def test_put_with_a_stale_revision_is_409_and_keeps_the_hand_edit(web: Any) -> None:
    first = web.get("/v1/settings/web-port").json()["revision"]
    _save_port(9200)  # a hand edit after the page read
    response = web.put(
        "/v1/settings/web-port", json={"port": 9100, "revision": first}, headers=ORIGIN
    )
    assert response.status_code == 409
    assert response.json()["message"] == "omrg.jsonc changed on disk. Reload to see the new values."
    assert _file_port() == 9200


@pytest.mark.parametrize("body", [{"port": 1023}, {"port": 65536}, {"port": 0}, {"port": "x"}, {}])
def test_put_rejects_invalid_ports(web: Any, body: dict) -> None:
    response = web.put("/v1/settings/web-port", json=body, headers=ORIGIN)
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert (
        "1024" in response.json()["message"]
        and "65535" in response.json()["message"]
        or (body == {})
    )
    assert web.get("/v1/settings/web-port").json()["saved"] is None


def test_bearer_can_read_but_not_change_the_port(web: Any) -> None:
    web.cookies.clear()
    read = web.get("/v1/settings/web-port", headers=bearer(web.policy, "read"))
    assert read.status_code == 200
    every_scope = bearer(web.policy, "graph", "read", "run")
    refused = web.put("/v1/settings/web-port", json={"port": 9100}, headers=every_scope)
    assert refused.status_code == 403
    assert _file_port() is None


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


# ── 5.4 The login item reads the same value ──────────────────────────────


def _plan(tmp_path: Path, port: int | None = None) -> Any:
    from omrg.transports.cli import _web_login_item as core

    return core.WebLoginItemPlan(
        label="com.omrg.web.test",
        command_path="/usr/local/bin/omrg",
        plist_path=tmp_path / "test.plist",
        stdout_log=tmp_path / "out.log",
        stderr_log=tmp_path / "err.log",
        working_directory=tmp_path,
        home=tmp_path,
        port=port,
    )


def test_the_login_item_targets_the_port_in_the_config_file(tmp_path: Path) -> None:
    from omrg.transports.cli.web_login_item import _target_port

    assert _target_port(_plan(tmp_path)) == 8765
    _save_port(9100)
    assert _target_port(_plan(tmp_path)) == 9100
    assert _target_port(_plan(tmp_path, port=7000)) == 7000  # the plan option wins


def test_the_login_item_ignores_an_invalid_file_port(tmp_path: Path) -> None:
    from omrg.transports.cli.web_login_item import _target_port

    _save_port(None, raw="80")
    assert _target_port(_plan(tmp_path)) == 8765
