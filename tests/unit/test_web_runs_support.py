"""Shared helpers for the graph and run route tests (task 6.6).

The app uses a real Engine over in-memory fakes (real catalogue and real
graph validation, no model calls), the real SQLite workspace repository
on ``tmp_path`` and the real ``RunService``. :class:`GatedEngine` can
hold a run open until a test releases it. This module holds no tests.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_engine_pipelines_support import (
    FakeEmbedder,
    FakeStore,
    chunks,
    retrieval_graph,
)

from omrs.engine import Engine
from omrs.transports.api.app import create_app
from omrs.transports.api.lifespan import WebConfig
from omrs.transports.api.runs_wiring import run_service_factory
from omrs.transports.api.security import AccessPolicy

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


class GatedEngine(Engine):
    """A real Engine whose graph runs are counted and can wait on a gate.

    The gate is a thread event, so a test thread can open it while the app
    runs on the TestClient's event loop.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.runs: list[Any] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def hold(self) -> threading.Event:
        """Make the following runs wait until the returned gate is set."""
        self.gate = threading.Event()
        return self.gate

    async def run_pipeline(self, definition: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        self.runs.append(definition)
        self.started.set()
        if self.gate is not None:
            assert await asyncio.to_thread(self.gate.wait, 10), "test gate was never opened"
        return await super().run_pipeline(definition, **kwargs)


def make_engine(effective_settings: Callable[..., Any], **kwargs: Any) -> GatedEngine:
    """Return a gated Engine over a fake store and embedder."""
    store = FakeStore(chunks())
    return GatedEngine(effective_settings(), store=store, embed_model=FakeEmbedder(), **kwargs)


def build_app(
    tmp_path: Path,
    engine: Any,
    *,
    with_runs: bool = True,
    workspace: Path | None = None,
    roots: tuple[Path, ...] = (),
) -> tuple[Any, AccessPolicy]:
    """Create the app around *engine* with the workspace run service."""
    config = WebConfig(
        workspace=workspace or tmp_path / "ws", port=8765, roots=roots, static_dir=None
    )
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory if with_runs else None,
    )
    return app, policy


def login(client: TestClient, policy: AccessPolicy) -> None:
    """Exchange the bootstrap secret for a session cookie."""
    response = client.post(
        "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text


def bearer(policy: AccessPolicy, *scopes: str) -> dict[str, str]:
    """Return an Authorization header for a new bearer credential."""
    return {"Authorization": f"Bearer {policy.issue_bearer(set(scopes)).token}"}


def graph(**params: Any) -> dict[str, Any]:
    """Return a valid retrieval graph document."""
    return retrieval_graph(**params)


def new_pipeline(
    app: Any, title: str = "Search", layout: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a loose pipeline in the workspace of *app* and return its record.

    ``POST /v1/pipelines`` is withdrawn, so tests write the record directly.
    The app must be running (inside the ``TestClient`` block).
    """
    repository = app.state.runtime.run_service.service.repository
    return dict(repository.create_pipeline(title, layout=layout))


def save_revision(client: TestClient, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a loose pipeline and save one revision; return the revision."""
    pipeline_id = new_pipeline(client.app)["pipeline_id"]
    response = client.post(
        f"/v1/pipelines/{pipeline_id}/revisions",
        json={"document": document or graph(top_k=2)},
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]


def submit(client: TestClient, revision_id: str, **inputs: Any) -> Any:
    """Submit a run of *revision_id*."""
    return client.post(
        "/v1/runs",
        json={"revision_id": revision_id, "inputs": inputs or {"query": "text"}},
        headers=ORIGIN,
    )


def wait_run(client: TestClient, run_id: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Poll a run until it is terminal; return the record."""
    deadline = time.monotonic() + timeout
    while True:
        run = client.get(f"/v1/runs/{run_id}").json()["run"]
        if run["status"] in TERMINAL:
            return run
        if time.monotonic() > deadline:
            raise AssertionError(f"run did not finish: {run}")
        time.sleep(0.02)


def parse_sse(text: str) -> list[dict[str, Any]]:
    """Split an event-stream body into frames of ``id``, ``event`` and ``data``."""
    import json

    frames = []
    for block in text.split("\n\n"):
        frame: dict[str, Any] = {}
        for line in block.splitlines():
            field, _, value = line.partition(": ")
            if field == "data":
                frame["data"] = json.loads(value)
            elif field in {"id", "event", "retry"}:
                frame[field] = value
        if frame:
            frames.append(frame)
    return frames
