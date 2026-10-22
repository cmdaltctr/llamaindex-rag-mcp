"""Shared helpers for the experiment transport tests (tasks 8.5, 8.6).

The application has a real live Engine over in-memory fakes, the real
run service and SQLite workspace, and a real ``ExperimentEngines`` with
an explicit base ``Settings`` (no ``.env``). The context Engine builder
records the settings it receives and returns a gated Engine over its own
fake rows, so a test can tell which Engine served a run. No model, LLM or
network call happens. This module holds no tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_engine_pipelines_support import FakeEmbedder, FakeStore, chunks
from tests.unit.test_experiment_contexts_support import base_settings
from tests.unit.test_web_runs_support import BASE, ORIGIN, GatedEngine, graph, login, new_pipeline

from omrs.compose_experiments import ExperimentEngines, experiment_registry
from omrs.core.profiles.resolver import ProfileResolver
from omrs.transports.api.app import create_app
from omrs.transports.api.lifespan import WebConfig
from omrs.transports.api.runs_wiring import run_service_factory
from omrs.transports.api.security import AccessPolicy

__all__ = ["BASE", "ORIGIN", "graph", "login"]


@dataclass
class ContextEngineBuilder:
    """Builds one gated Engine per experiment context and records the settings."""

    effective_settings: Callable[..., Any]
    calls: list[Any] = field(default_factory=list)
    engines: list[GatedEngine] = field(default_factory=list)

    def __call__(self, settings: Any) -> GatedEngine:
        """Return a new gated Engine over experiment rows."""
        self.calls.append(settings)
        effective = self.effective_settings()
        # As in production, a context Engine resolves the built-in profiles by name.
        resolver = ProfileResolver(
            store=None, server_profile="documents", base=effective, env_overrides={}
        )
        engine = GatedEngine(
            effective,
            store=FakeStore(chunks("exp")),
            embed_model=FakeEmbedder(),
            profile_resolver=resolver,
        )
        self.engines.append(engine)
        return engine


@dataclass
class ExperimentApp:
    """The parts of one experiment-enabled test application."""

    app: Any
    policy: AccessPolicy
    root: Path
    base: Any
    builder: ContextEngineBuilder
    holder: dict[str, Any]

    @property
    def experiments(self) -> ExperimentEngines:
        """The launch's experiment engines (built at startup)."""
        return self.holder["experiments"]


def build_experiment_app(
    tmp_path: Path,
    live_engine: Any,
    effective_settings: Callable[..., Any],
    **config_overrides: Any,
) -> ExperimentApp:
    """Create the app with one approved experiment root below *tmp_path*."""
    root = tmp_path / "experiments"
    root.mkdir(exist_ok=True)
    base = base_settings(tmp_path / "live")
    builder = ContextEngineBuilder(effective_settings)
    holder: dict[str, Any] = {}

    def experiments_factory(config: WebConfig) -> ExperimentEngines:
        engines = ExperimentEngines(
            experiment_registry(config.experiment_roots), base, build_engine=builder
        )
        holder["experiments"] = engines
        return engines

    options: dict[str, Any] = {
        "workspace": tmp_path / "ws",
        "port": 8765,
        "static_dir": None,
        "experiment_roots": (root,),
        "experiments_factory": experiments_factory,
    }
    options.update(config_overrides)
    config = WebConfig(**options)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: live_engine,
        run_service_factory=run_service_factory,
    )
    return ExperimentApp(app, policy, root, base, builder, holder)


def register(client: TestClient, root: Path, name: str = "exp-a", **body: Any) -> dict[str, Any]:
    """Create a workspace below *root* and register it; return the response body."""
    workspace = root / name
    workspace.mkdir(exist_ok=True)
    response = client.post(
        "/v1/experiments", json={"workspace": str(workspace), "name": name, **body}, headers=ORIGIN
    )
    assert response.status_code == 201, response.text
    return response.json()


def bound_bearer(
    client: TestClient, context_id: str, scopes: tuple[str, ...] = ("graph", "read", "run")
) -> dict[str, str]:
    """Issue a bearer credential bound to *context_id*; return its header."""
    response = client.post(
        "/v1/credentials",
        json={"scopes": list(scopes), "label": "notebook", "experiment_context": context_id},
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def save_revision(client: TestClient, document: dict[str, Any] | None = None) -> str:
    """Save a read-only retrieval revision through the session; return its id."""
    pipeline = new_pipeline(client.app)
    response = client.post(
        f"/v1/pipelines/{pipeline['pipeline_id']}/revisions",
        json={"document": document or graph(top_k=2)},
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def submit(
    client: TestClient,
    revision_id: str,
    *,
    context: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Submit a run, optionally in an experiment context."""
    body: dict[str, Any] = {"revision_id": revision_id, "inputs": {"query": "text"}}
    if context is not None:
        body["experiment_context"] = context
    return client.post("/v1/runs", json=body, headers={**ORIGIN, **(headers or {})})


def wait_run(
    client: TestClient, run_id: str, headers: dict[str, str] | None = None, timeout: float = 10.0
) -> dict[str, Any]:
    """Poll a run until it is terminal; return the record."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/v1/runs/{run_id}", headers=headers or {})
        assert response.status_code == 200, response.text
        run = response.json()["run"]
        if run["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return run
        assert time.monotonic() < deadline, run
        time.sleep(0.02)
