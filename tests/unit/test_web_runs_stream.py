"""Tests for the run event stream (server-sent events), task 6.6.

Replay after ``Last-Event-ID`` or ``?after=``, frames with ``id:`` lines
for deduplication, the same events as polling, a prompt end when the
server stops admitting work, and a browser disconnect that detaches
monitoring only. Live-stream tests drive the ASGI app directly, because
the test client buffers a whole streamed response.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    build_app,
    graph,
    login,
    make_engine,
    new_pipeline,
    parse_sse,
    save_revision,
    submit,
    wait_run,
)

from omrs.transports.api.lifespan import request_shutdown  # noqa: E402


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def finished(tmp_path: Path, engine: Any) -> Any:
    """A client logged in with one finished run; yields ``(client, run)``."""
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        revision = save_revision(client)
        run = wait_run(client, submit(client, revision["revision_id"]).json()["run"]["run_id"])
        yield client, run


def _stream(client: Any, run_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    response = client.get(f"/v1/runs/{run_id}/events/stream", **kwargs)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    return parse_sse(response.text)


def test_stream_replays_every_event_with_sequence_ids(finished: Any) -> None:
    client, run = finished
    frames = _stream(client, run["run_id"])
    assert frames[0] == {"retry": "3000"}
    events = [f for f in frames if "id" in f]
    assert [int(f["id"]) for f in events] == list(range(1, run["last_sequence"] + 1))
    assert all(f["event"] == f["data"]["kind"] for f in events)
    assert frames[-1]["event"] == "run.end"
    assert frames[-1]["data"] == {"status": "succeeded", "last_sequence": run["last_sequence"]}
    # Polling returns the same events.
    polled = client.get(f"/v1/runs/{run['run_id']}/events").json()["events"]
    assert [f["data"] for f in events] == polled


def test_reconnect_replays_after_last_event_id(finished: Any) -> None:
    client, run = finished
    by_header = _stream(client, run["run_id"], headers={"Last-Event-ID": "2"})
    by_query = _stream(client, run["run_id"], params={"after": 2})
    header_wins = _stream(
        client, run["run_id"], params={"after": 0}, headers={"Last-Event-ID": "3"}
    )
    ids = [int(f["id"]) for f in by_header if "id" in f]
    assert ids == list(range(3, run["last_sequence"] + 1))
    assert [f for f in by_query if "id" in f] == [f for f in by_header if "id" in f]
    assert [int(f["id"]) for f in header_wins if "id" in f][0] == 4
    at_end = _stream(client, run["run_id"], headers={"Last-Event-ID": str(run["last_sequence"])})
    assert [f for f in at_end if "id" in f] == []
    assert at_end[-1]["event"] == "run.end"


def test_bad_last_event_id_and_unknown_run(finished: Any) -> None:
    client, run = finished
    bad = client.get(f"/v1/runs/{run['run_id']}/events/stream", headers={"Last-Event-ID": "x"})
    assert bad.status_code == 400
    assert bad.json()["status"] == "error"
    negative = client.get(f"/v1/runs/{run['run_id']}/events/stream", params={"after": -1})
    assert negative.status_code == 400
    assert client.get("/v1/runs/nope/events/stream").status_code == 404


def test_stream_needs_read_credentials(finished: Any) -> None:
    client, run = finished
    client.cookies.clear()
    response = client.get(f"/v1/runs/{run['run_id']}/events/stream")
    assert response.status_code == 401
    assert response.json()["status"] == "error"
    runner = {
        "Authorization": f"Bearer {client.app.state.access_policy.issue_bearer({'run'}).token}"
    }
    assert client.get(f"/v1/runs/{run['run_id']}/events/stream", headers=runner).status_code == 403


# ── Live streams on the ASGI app ─────────────────────────────────────────


class LiveStream:
    """One ``GET .../events/stream`` request driven through raw ASGI calls."""

    def __init__(self, app: Any, run_id: str, token: str) -> None:
        self.frames: list[dict[str, Any]] = []
        self.status: int | None = None
        self.got_frame = asyncio.Event()
        self._leave = asyncio.Event()
        self._sent_request = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": f"/v1/runs/{run_id}/events/stream",
            "raw_path": f"/v1/runs/{run_id}/events/stream".encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"127.0.0.1:8765"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8765),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> dict[str, Any]:
        if not self._sent_request:
            self._sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._leave.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message.get("body"):
            self.frames += parse_sse(message["body"].decode())
            self.got_frame.set()

    def disconnect(self) -> None:
        """Simulate the browser closing the connection."""
        self._leave.set()

    async def wait_for(self, predicate: Any, timeout: float = 5.0) -> None:
        async def poll() -> None:
            while not predicate(self.frames):
                self.got_frame.clear()
                await self.got_frame.wait()

        await asyncio.wait_for(poll(), timeout)


async def _start_held_run(app: Any, engine: Any) -> tuple[str, str, Any]:
    """Start a run that waits on the engine gate; return run id, token and gate."""
    gate = engine.hold()
    token = app.state.access_policy.issue_bearer({"read", "run", "graph"}).token
    transport = httpx.ASGITransport(app=app)
    auth = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=auth) as client:
        pipeline_id = new_pipeline(app, "p")["pipeline_id"]
        revision = (
            await client.post(f"/v1/pipelines/{pipeline_id}/revisions", json={"document": graph()})
        ).json()["revision"]
        body = {"revision_id": revision["revision_id"], "inputs": {"query": "q"}}
        run = (await client.post("/v1/runs", json=body)).json()["run"]
    await asyncio.wait_for(asyncio.to_thread(engine.started.wait, 5), 6)
    return run["run_id"], token, gate


def _running(frames: list[dict[str, Any]]) -> bool:
    return any(f.get("data", {}).get("summary", {}).get("status") == "running" for f in frames)


def test_browser_disconnect_detaches_monitoring_without_cancelling(
    tmp_path: Path, engine: Any
) -> None:
    app, _ = build_app(tmp_path, engine)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            run_id, token, gate = await _start_held_run(app, engine)
            stream = LiveStream(app, run_id, token)
            await stream.wait_for(_running)
            assert stream.status == 200
            stream.disconnect()
            await asyncio.wait_for(stream.task, 5)
            repository = app.state.runtime.run_service.service.repository
            assert repository.get_run(run_id)["status"] == "running"
            gate.set()
            await asyncio.wait_for(app.state.runtime.run_service.service.wait_idle(), 10)
            run = repository.get_run(run_id)
            assert run["status"] == "succeeded"
            kinds = [e["summary"].get("status") for e in repository.list_events(run_id)]
            assert "cancelling" not in kinds

    asyncio.run(scenario())


def test_stream_ends_promptly_when_admission_closes(tmp_path: Path, engine: Any) -> None:
    app, _ = build_app(tmp_path, engine)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            run_id, token, gate = await _start_held_run(app, engine)
            stream = LiveStream(app, run_id, token)
            await stream.wait_for(_running)
            request_shutdown(app)  # what the signal handler calls
            await asyncio.wait_for(stream.task, 2)
            assert stream.frames[-1]["event"] == "server.closing"
            assert not any(f.get("event") == "run.end" for f in stream.frames)
            gate.set()

    asyncio.run(scenario())


def test_live_stream_follows_new_events_until_the_run_ends(tmp_path: Path, engine: Any) -> None:
    app, _ = build_app(tmp_path, engine)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            run_id, token, gate = await _start_held_run(app, engine)
            stream = LiveStream(app, run_id, token)
            await stream.wait_for(_running)
            gate.set()
            await asyncio.wait_for(stream.task, 10)
            ids = [int(f["id"]) for f in stream.frames if "id" in f]
            assert ids == sorted(set(ids)) and ids[0] == 1
            assert stream.frames[-1]["event"] == "run.end"
            assert stream.frames[-1]["data"]["status"] == "succeeded"

    asyncio.run(scenario())


def test_request_shutdown_before_startup_is_a_no_op(tmp_path: Path, engine: Any) -> None:
    app, _ = build_app(tmp_path, engine)
    request_shutdown(app)  # no runtime yet: nothing happens
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/v1/health").status_code == 200
