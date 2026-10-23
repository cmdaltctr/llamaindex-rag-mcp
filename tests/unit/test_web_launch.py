"""Tests for ``omrs web`` launch, lifespan ownership and API fallback (task 6.1).

Covers the lazy web extra, the unchanged no-argument MCP start, the
engine built once through an injectable factory, graceful drain on
shutdown, the run-service hook, ``GET /v1/health``, and the rule that the
frontend fallback never answers a ``/v1`` path with HTML.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import (  # noqa: E402
    AdmissionClosed,
    WebConfig,
    shutdown_runtime,
)
from omrs.transports.cli import app as cli_app  # noqa: E402

BASE = "http://127.0.0.1:8765"
runner = CliRunner()


class FakeEngine:
    """Engine stand-in that records its lifecycle."""

    def __init__(self, events: list[str] | None = None) -> None:
        self.closed = False
        self.events = events if events is not None else []

    def close(self) -> None:
        self.closed = True
        self.events.append("engine.close")


class FakeRunService:
    """Run-service hook stand-in that records start and shutdown."""

    def __init__(self, runtime: Any, events: list[str]) -> None:
        self.runtime = runtime
        self.events = events

    async def start(self) -> None:
        self.events.append("service.start")

    async def shutdown(self) -> None:
        # The engine must still be open while the service shuts down.
        assert not self.runtime.engine.closed
        self.events.append("service.shutdown")


def _config(tmp_path: Path, static_dir: Path | None = None) -> WebConfig:
    return WebConfig(
        workspace=tmp_path / "ws",
        host="127.0.0.1",
        port=8765,
        roots=(),
        static_dir=static_dir,
    )


def _static(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return static


# ── Lazy extra and CLI wiring ────────────────────────────────────────────


def test_cli_import_and_help_do_not_load_fastapi() -> None:
    """Importing the CLI and printing help never imports the web stack."""
    code = textwrap.dedent(
        """
        import sys
        import omrs, omrs.transports.cli
        from typer.testing import CliRunner
        result = CliRunner().invoke(omrs.transports.cli.app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "web" in result.output
        web_modules = ("fastapi", "starlette", "omrs.transports.api.app")
        loaded = [m for m in web_modules if m in sys.modules]
        assert not loaded, loaded
        """
    )
    env = {**os.environ, "PYTHONPATH": "src"}
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 0, proc.stderr[-1500:]


def test_help_works_when_fastapi_is_not_installed() -> None:
    """``omrs --help`` succeeds when fastapi cannot be imported at all."""
    code = textwrap.dedent(
        """
        import sys
        sys.modules["fastapi"] = None
        import omrs.transports.cli as cli
        from typer.testing import CliRunner
        result = CliRunner().invoke(cli.app, ["--help"])
        assert result.exit_code == 0, result.output
        """
    )
    env = {**os.environ, "PYTHONPATH": "src"}
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 0, proc.stderr[-1500:]


def test_web_without_extra_prints_install_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing extra fails only ``omrs web``, with an install instruction."""
    monkeypatch.setitem(sys.modules, "fastapi", None)
    with patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup:
        result = runner.invoke(cli_app, ["web"])
    assert result.exit_code == 1
    assert 'pip install "omrs[web]"' in result.output
    assert "uv sync --extra web" in result.output
    setup.assert_not_called()


def test_no_argument_start_still_runs_mcp_server() -> None:
    """``omrs`` with no arguments builds one Engine and starts MCP on stdio."""
    # MCP main() calls logging.basicConfig(force=True) on the captured
    # stream; keep the root logger untouched for later tests.
    server = MagicMock()
    catalogue = object()
    with (
        patch("omrs.compose_profile_setup.workspace_profile_catalogue", return_value=catalogue),
        patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup,
        patch("omrs.transports.mcp.compose.build_engine") as build_engine,
        patch("omrs.transports.mcp.create_mcp_server", return_value=server) as factory,
        patch("logging.basicConfig"),
    ):
        result = runner.invoke(cli_app, [])
    assert result.exit_code == 0, result.output
    setup.assert_not_called()
    build_engine.assert_called_once_with(catalogue=catalogue)
    factory.assert_called_once()
    server.run.assert_called_once_with(transport="stdio")


def test_web_bypasses_legacy_installer_and_prints_bootstrap_url_to_stderr(
    tmp_path: Path,
) -> None:
    """``omrs web`` skips the process-default installer and keeps stdout clean."""
    captured: dict[str, Any] = {}

    def fake_serve(app: Any, sock: Any) -> None:
        captured["app"] = app
        captured["port"] = sock.getsockname()[1]
        sock.close()

    with (
        patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup,
        patch("omrs.transports.cli.web._serve", side_effect=fake_serve),
    ):
        # --port 0: a login item on this machine can hold the default port 8765.
        result = runner.invoke(cli_app, ["web", "--port", "0", "--workspace", str(tmp_path / "ws")])

    assert result.exit_code == 0, result.output
    setup.assert_not_called()
    assert result.stdout == ""
    port = captured["port"]
    assert port > 0
    assert f"http://127.0.0.1:{port}/#bootstrap=omrs_bs_" in result.stderr
    assert "mcp" not in captured["app"].title.lower()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])  # noqa: S104
def test_web_rejects_non_loopback_bind(host: str, tmp_path: Path) -> None:
    """A remote bind address fails with a local-use explanation."""
    with patch("omrs.transports.cli.web._serve") as serve:
        result = runner.invoke(
            cli_app, ["web", "--host", host, "--workspace", str(tmp_path / "ws")]
        )
    assert result.exit_code == 2
    assert "loopback" in result.stderr
    serve.assert_not_called()


def test_web_rejects_missing_root(tmp_path: Path) -> None:
    """An approved root that does not exist stops the launch."""
    with patch("omrs.transports.cli.web._serve") as serve:
        result = runner.invoke(
            cli_app,
            ["web", "--workspace", str(tmp_path / "ws"), "--root", str(tmp_path / "absent")],
        )
    assert result.exit_code == 2
    serve.assert_not_called()


@pytest.mark.parametrize(
    ("value", "rule"),
    [("http://example.com", "loopback"), ("http://*.localhost:3000", "wildcard")],
)
def test_web_rejects_bad_allow_origin_before_binding(value: str, rule: str, tmp_path: Path) -> None:
    """A bad ``--allow-origin`` exits 2 and names the value, before any socket opens."""
    with (
        patch("omrs.transports.cli.web._bind_socket") as bind,
        patch("omrs.transports.cli.web._serve") as serve,
    ):
        result = runner.invoke(
            cli_app, ["web", "--workspace", str(tmp_path / "ws"), "--allow-origin", value]
        )
    assert result.exit_code == 2
    assert rule in result.stderr
    assert value in result.stderr.replace("\n", "")
    bind.assert_not_called()
    serve.assert_not_called()


def test_web_passes_allowed_origins_to_the_policy_and_prints_them_first(tmp_path: Path) -> None:
    """Each approved origin reaches the policy and is printed before the launch link."""
    captured: dict[str, Any] = {}

    def fake_serve(app: Any, sock: Any) -> None:
        captured["policy"] = app.state.access_policy
        sock.close()

    with patch("omrs.transports.cli.web._serve", side_effect=fake_serve):
        result = runner.invoke(
            cli_app,
            [
                "web",
                "--port",
                "0",
                "--workspace",
                str(tmp_path / "ws"),
                "--allow-origin",
                "http://a.orca.localhost:57977",
                "--allow-origin",
                "HTTP://localhost:3000/",
            ],
        )

    assert result.exit_code == 0, result.output
    origins = captured["policy"].allowed_origins
    assert {"http://a.orca.localhost:57977", "http://localhost:3000"} <= origins
    text = result.stderr
    link = text.index("#bootstrap=")
    assert text.index("http://a.orca.localhost:57977") < link
    assert text.index("http://localhost:3000") < link


# ── Lifespan ownership ───────────────────────────────────────────────────


def test_lifespan_builds_one_engine_and_closes_it(tmp_path: Path) -> None:
    """The factory runs once at startup; the engine closes at shutdown."""
    engines: list[FakeEngine] = []

    def factory() -> FakeEngine:
        engines.append(FakeEngine())
        return engines[-1]

    app = create_app(_config(tmp_path), engine_factory=factory)
    assert engines == []  # nothing is built before startup
    with TestClient(app, base_url=BASE) as client:
        assert len(engines) == 1
        assert client.get("/v1/health").status_code == 200
        assert not engines[0].closed
    assert len(engines) == 1
    assert engines[0].closed


def test_run_service_hook_starts_and_shuts_down_before_engine_close(tmp_path: Path) -> None:
    """The run-service hook shuts down while the engine is still open."""
    events: list[str] = []
    app = create_app(
        _config(tmp_path),
        engine_factory=lambda: FakeEngine(events),
        run_service_factory=lambda runtime: FakeRunService(runtime, events),
    )
    with TestClient(app, base_url=BASE):
        assert events == ["service.start"]
    assert events == ["service.start", "service.shutdown", "engine.close"]


def test_shutdown_waits_for_active_work_and_rejects_new_admission(tmp_path: Path) -> None:
    """Shutdown stops admission and closes the engine only after active work ends."""
    app = create_app(_config(tmp_path), engine_factory=FakeEngine)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            engine = runtime.engine
            release = asyncio.Event()

            async def active_work() -> None:
                async with runtime.admission.enter():
                    await release.wait()

            worker = asyncio.create_task(active_work())
            await asyncio.sleep(0)
            shutdown = asyncio.create_task(shutdown_runtime(runtime))
            await asyncio.sleep(0.01)
            assert not engine.closed  # still owned while work is active
            with pytest.raises(AdmissionClosed):
                async with runtime.admission.enter():
                    pass
            release.set()
            await worker
            await shutdown
            assert engine.closed

    asyncio.run(scenario())


def test_engine_closes_when_run_service_start_fails(tmp_path: Path) -> None:
    """A failing run-service start still releases the engine."""
    engine = FakeEngine()

    class Broken:
        async def start(self) -> None:
            raise RuntimeError("boom")

        async def shutdown(self) -> None:
            return None

    app = create_app(
        _config(tmp_path), engine_factory=lambda: engine, run_service_factory=lambda rt: Broken()
    )
    with pytest.raises(RuntimeError, match="boom"), TestClient(app, base_url=BASE):
        pass
    assert engine.closed


# ── Health and fallback ──────────────────────────────────────────────────


def test_health_is_public_json(tmp_path: Path) -> None:
    """``GET /v1/health`` answers without credentials."""
    app = create_app(_config(tmp_path), engine_factory=FakeEngine)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/v1/does-not-exist", "/v1/collections/x/nothing", "/v1"])
def test_unknown_api_path_returns_json_envelope_not_html(tmp_path: Path, path: str) -> None:
    """Unknown ``/v1`` paths never fall through to the SPA."""
    app = create_app(_config(tmp_path, _static(tmp_path)), engine_factory=FakeEngine)
    with TestClient(app, base_url=BASE) as client:
        client.cookies.clear()
        response = client.get(path)
    assert response.status_code in {401, 404}
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["status"] == "error"
    assert isinstance(body["message"], str)
    assert "<html" not in response.text.lower()


def test_spa_fallback_serves_index_and_assets(tmp_path: Path) -> None:
    """Frontend routes return index.html; assets are served; missing assets 404."""
    app = create_app(_config(tmp_path, _static(tmp_path)), engine_factory=FakeEngine)
    with TestClient(app, base_url=BASE) as client:
        root = client.get("/")
        route = client.get("/library")
        asset = client.get("/assets/app.js")
        missing = client.get("/assets/missing.js")
    assert root.status_code == 200 and "id=root" in root.text
    assert route.status_code == 200 and "id=root" in route.text
    assert asset.status_code == 200 and "console.log" in asset.text
    assert missing.status_code == 404
    assert "id=root" not in missing.text


def test_missing_static_build_gives_actionable_message(tmp_path: Path) -> None:
    """Without built assets the root page names the build command."""
    app = create_app(_config(tmp_path, tmp_path / "no-static"), engine_factory=FakeEngine)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/")
        api = client.get("/v1/health")
    assert response.status_code == 404
    assert "npm run build" in response.text
    assert api.status_code == 200


def test_api_errors_use_envelope_for_method_not_allowed(tmp_path: Path) -> None:
    """Framework errors on API routes keep the status/message envelope."""
    app = create_app(_config(tmp_path), engine_factory=FakeEngine)
    with TestClient(app, base_url=BASE) as client:
        response = client.delete("/v1/health")
    assert response.status_code == 405
    assert response.json()["status"] == "error"


def test_bind_socket_picks_a_free_loopback_port() -> None:
    """Port 0 binds a real free port on loopback before the app starts."""
    from omrs.transports.cli.web import _bind_socket

    sock = _bind_socket("127.0.0.1", 0)
    try:
        host, port = sock.getsockname()[:2]
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        sock.close()
