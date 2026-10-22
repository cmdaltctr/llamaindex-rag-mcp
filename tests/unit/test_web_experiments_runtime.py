"""Experiment and plugin runtime wiring of the web lifespan (tasks 8.5, 8.6).

Approved experiment roots come only from ``omrs web --experiment-root``.
The base settings come from the composition root. Shutdown order is: run
service, owned notebook editors, experiment Engines, then the live Engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_experiment_contexts_support import base_settings  # noqa: E402
from tests.unit.test_web_launch import FakeEngine, FakeRunService  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from omrs import compose_engine  # noqa: E402
from omrs.compose_experiments import ExperimentEngines  # noqa: E402
from omrs.transports.api import lifespan  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import PluginHost, WebConfig  # noqa: E402
from omrs.transports.cli import app as cli_app  # noqa: E402

BASE = "http://127.0.0.1:8765"


class Recorder:
    """Experiment engines and editor supervisor stand-ins that record calls."""

    def __init__(self, events: list[str], *, busy: bool = False) -> None:
        self.events = events
        self.busy = busy

    def close(self) -> None:
        self.events.append("experiments.close")
        if self.busy:
            raise RuntimeError("Experiment contexts still borrowed: exp_1")

    def stop_all(self) -> list[object]:
        self.events.append("editors.stop_all")
        return []


def _app(tmp_path: Path, events: list[str], *, busy: bool = False) -> Any:
    recorder = Recorder(events, busy=busy)
    config = WebConfig(
        workspace=tmp_path / "ws",
        port=8765,
        static_dir=None,
        experiments_factory=lambda _config: recorder,
        plugins_factory=lambda config: PluginHost(
            repository=None,
            registry=None,
            editors=recorder,
            manifests=(),
            manifest_dir=config.workspace / "plugins",
            executable_dirs=(),
        ),
    )
    return create_app(
        config,
        engine_factory=lambda: FakeEngine(events),
        run_service_factory=lambda runtime: FakeRunService(runtime, events),
    )


def test_shutdown_order_is_service_editors_experiments_engine(tmp_path: Path) -> None:
    events: list[str] = []
    with TestClient(_app(tmp_path, events), base_url=BASE):
        assert events == ["service.start"]
    assert events == [
        "service.start",
        "service.shutdown",
        "editors.stop_all",
        "experiments.close",
        "engine.close",
    ]


def test_engine_closes_even_when_experiments_refuse_to_close(tmp_path: Path) -> None:
    events: list[str] = []
    with TestClient(_app(tmp_path, events, busy=True), base_url=BASE):
        pass
    assert events[-2:] == ["experiments.close", "engine.close"]


def test_default_factory_without_roots_reads_no_settings(tmp_path: Path) -> None:
    with patch.object(compose_engine, "experiment_base_settings", side_effect=AssertionError):
        assert lifespan.default_experiments_factory(WebConfig(workspace=tmp_path / "ws")) is None


def test_default_factory_uses_the_composition_root_settings(tmp_path: Path) -> None:
    roots = (tmp_path / "a", tmp_path / "b")
    for root in roots:
        root.mkdir()
    base = base_settings(tmp_path / "live")
    with patch.object(compose_engine, "experiment_base_settings", return_value=base) as source:
        engines = lifespan.default_experiments_factory(
            WebConfig(workspace=tmp_path / "ws", experiment_roots=roots)
        )
    source.assert_called_once_with()
    assert isinstance(engines, ExperimentEngines)
    assert engines.registry.approved_roots == tuple(root.resolve() for root in roots)
    assert engines.registry.contexts() == []  # nothing approved, nothing built


def test_experiment_base_settings_is_the_resolved_settings() -> None:
    sentinel = object()
    with patch("omrs.config.get_settings", return_value=sentinel):
        assert compose_engine.experiment_base_settings() is sentinel


def test_cli_passes_repeatable_experiment_roots(tmp_path: Path) -> None:
    roots = [tmp_path / "one", tmp_path / "two"]
    for root in roots:
        root.mkdir()
    captured: dict[str, Any] = {}

    def fake_create_app(config: WebConfig, **_: Any) -> Any:
        captured["config"] = config
        return object()

    # --port 0: a login item on this machine can hold the default port 8765.
    args = ["web", "--port", "0", "--workspace", str(tmp_path / "ws")]
    for root in roots:
        args += ["--experiment-root", str(root)]
    with (
        patch("omrs.transports.api.app.create_app", side_effect=fake_create_app),
        patch("omrs.transports.cli.web._serve", side_effect=lambda app, sock: sock.close()),
    ):
        result = CliRunner().invoke(cli_app, args)
    assert result.exit_code == 0, result.output
    assert captured["config"].experiment_roots == tuple(roots)


def test_cli_rejects_a_missing_experiment_root(tmp_path: Path) -> None:
    with patch("omrs.transports.cli.web._serve") as serve:
        result = CliRunner().invoke(
            cli_app,
            ["web", "--workspace", str(tmp_path / "ws"), "--experiment-root", str(tmp_path / "x")],
        )
    assert result.exit_code == 2
    assert "experiment root" in result.stderr.lower()
    serve.assert_not_called()
