"""Server log: ring buffer, ``GET /v1/logs`` and ``GET /v1/logs/stream`` (task 7.3).

The buffer holds the last 1,000 records in memory. A redacting filter sits
on the handler, so provider keys and bearer tokens never enter the buffer.
Both routes need the browser session (``manage``). The stream replays
after a sequence, follows new records, and ends with ``server.closing``
when the server stops admitting requests. Live-stream tests drive the
ASGI app directly, because the test client buffers a whole streamed
response.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import SECRET  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
    parse_sse,
)
from typer.testing import CliRunner  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig, request_shutdown  # noqa: E402
from omrg.transports.api.log_buffer import LogBuffer  # noqa: E402
from omrg.transports.api.security import RedactingFilter  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402

LOGGER = "omrg.test.logs"


@pytest.fixture
def buffer() -> Iterator[LogBuffer]:
    log_buffer = LogBuffer([SECRET])
    logger = logging.getLogger(LOGGER)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_buffer)
    # Keep records away from handlers outside this logger. The CLI tests install a
    # RichHandler on the root logger and never remove it, and RichHandler raises on a
    # bad format string, so which tests share a worker decided whether this file passed.
    propagate, logger.propagate = logger.propagate, False
    yield log_buffer
    logger.propagate = propagate
    logger.removeHandler(log_buffer)


def emit(level: int, message: str, *args: Any) -> None:
    logging.getLogger(LOGGER).log(level, message, *args)


# ── Buffer ───────────────────────────────────────────────────────────────


def test_record_shape(buffer: LogBuffer) -> None:
    emit(logging.WARNING, "disk %s", "low")
    [record] = buffer.records()
    assert set(record) == {"seq", "time", "level", "logger", "message"}
    assert record["seq"] == 1
    assert record["level"] == "warning"
    assert record["logger"] == LOGGER
    assert record["message"] == "disk low"
    assert record["time"].endswith("+00:00")


def test_the_openrouter_key_never_enters_the_buffer(buffer: LogBuffer) -> None:
    emit(logging.ERROR, "call failed with key %s", SECRET)
    emit(logging.ERROR, f"call failed with key {SECRET}")
    emit(logging.ERROR, "token omrg_bt_abc123.secretpart and Bearer abcdef123456")
    try:
        raise RuntimeError(f"upstream said {SECRET}")
    except RuntimeError:
        logging.getLogger(LOGGER).exception("failure")
    text = json.dumps(buffer.records())
    assert SECRET not in text
    assert "secretpart" not in text and "abcdef123456" not in text
    assert "***" in text
    assert "RuntimeError" in text


def test_the_filter_is_on_the_handler_itself(buffer: LogBuffer) -> None:
    assert any(isinstance(item, RedactingFilter) for item in buffer.filters)


def test_the_buffer_keeps_the_last_1000_records(buffer: LogBuffer) -> None:
    for index in range(1005):
        emit(logging.INFO, "line %d", index)
    records = buffer.records()
    assert len(records) == 1000
    assert records[0]["seq"] == 6 and records[-1]["seq"] == 1005
    assert records[0]["message"] == "line 5"
    assert buffer.last_seq == 1005


def test_records_after_a_sequence(buffer: LogBuffer) -> None:
    for index in range(5):
        emit(logging.INFO, "line %d", index)
    assert [r["seq"] for r in buffer.records(after=3)] == [4, 5]
    assert buffer.records(after=5) == []
    assert buffer.records(after=99) == []
    assert [r["seq"] for r in buffer.records(after=0)] == [1, 2, 3, 4, 5]


def test_one_message_is_capped(buffer: LogBuffer) -> None:
    emit(logging.INFO, "x" * 50_000)
    assert len(buffer.records()[0]["message"]) <= 10_001


def test_a_bad_format_does_not_break_logging(buffer: LogBuffer) -> None:
    with patch.object(logging, "raiseExceptions", False):
        emit(logging.INFO, "needs %s and %s", "one")
    emit(logging.INFO, "fine")
    assert [r["message"] for r in buffer.records()][-1] == "fine"


# ── Routes ───────────────────────────────────────────────────────────────


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, buffer: LogBuffer):
    engine = make_engine(lance_store(tmp_path), effective_settings())
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    from omrg.transports.api.security import AccessPolicy

    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: engine, log_buffer=buffer)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy, buffer


def test_logs_returns_records_and_replays_after_a_sequence(setup: Any) -> None:
    client, _, _ = setup
    for index in range(4):
        emit(logging.INFO, "line %d", index)
    body = client.get("/v1/logs").json()
    assert body["status"] == "ok" and body["last_seq"] == 4
    assert [r["message"] for r in body["records"]] == [f"line {i}" for i in range(4)]
    later = client.get("/v1/logs", params={"after": 2}).json()
    assert [r["seq"] for r in later["records"]] == [3, 4]
    empty = client.get("/v1/logs", params={"after": 4}).json()
    assert empty["records"] == [] and empty["last_seq"] == 4


def test_logs_response_never_holds_the_key(setup: Any) -> None:
    client, _, _ = setup
    emit(logging.ERROR, "bad key %s", SECRET)
    response = client.get("/v1/logs")
    assert SECRET not in response.text


def test_negative_after_is_a_validation_error(setup: Any) -> None:
    client, _, _ = setup
    assert client.get("/v1/logs", params={"after": -1}).status_code == 400
    assert client.get("/v1/logs/stream", params={"after": -1}).status_code == 400


def test_bearer_credentials_are_refused_on_both_endpoints(setup: Any) -> None:
    client, policy, _ = setup
    client.cookies.clear()
    header = bearer(policy, "read", "graph", "run")
    for path in ("/v1/logs", "/v1/logs/stream"):
        refused = client.get(path, headers=header)
        assert refused.status_code == 403, path
        assert refused.json()["status"] == "error"
        assert client.get(path).status_code == 401


def test_stream_replays_after_a_sequence_then_follows_the_server_closing(
    tmp_path: Path, effective_settings: Any, buffer: LogBuffer
) -> None:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, buffer)
    for index in range(5):
        emit(logging.INFO, "line %d", index)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            stream = LiveStream(app, policy, "/v1/logs/stream", query=b"after=2")
            await stream.wait_for(lambda frames: sum("id" in f for f in frames) >= 3)
            assert stream.status == 200
            assert stream.frames[0] == {"retry": "3000"}
            logged = [f for f in stream.frames if "id" in f]
            assert [int(f["id"]) for f in logged] == [3, 4, 5]
            assert all(f["event"] == "log" for f in logged)
            assert logged[0]["data"]["message"] == "line 2"
            emit(logging.WARNING, "a live warning")
            await stream.wait_for(lambda frames: any("live warning" in str(f) for f in frames))
            assert [int(f["id"]) for f in stream.frames if "id" in f][-1] == 6
            request_shutdown(app)
            await asyncio.wait_for(stream.task, 2)
            assert stream.frames[-1]["event"] == "server.closing"

    asyncio.run(scenario())


def test_stream_last_event_id_wins_over_after(
    tmp_path: Path, effective_settings: Any, buffer: LogBuffer
) -> None:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, buffer)
    for index in range(5):
        emit(logging.INFO, "line %d", index)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            stream = LiveStream(app, policy, "/v1/logs/stream", query=b"after=0", last_event_id="4")
            await stream.wait_for(lambda frames: any(f.get("id") == "5" for f in frames))
            assert [int(f["id"]) for f in stream.frames if "id" in f] == [5]
            request_shutdown(app)
            await asyncio.wait_for(stream.task, 2)

    asyncio.run(scenario())


def test_stream_with_a_bad_last_event_id_is_400(setup: Any) -> None:
    client, _, _ = setup
    bad = client.get("/v1/logs/stream", headers={"Last-Event-ID": "x"})
    assert bad.status_code == 400 and bad.json()["status"] == "error"


def test_stream_secret_never_appears_in_a_frame(
    tmp_path: Path, effective_settings: Any, buffer: LogBuffer
) -> None:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, buffer)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            stream = LiveStream(app, policy, "/v1/logs/stream")
            await stream.wait_for(lambda frames: bool(frames))
            emit(logging.ERROR, "leak %s", SECRET)
            await stream.wait_for(lambda frames: any(f.get("id") for f in frames))
            request_shutdown(app)
            await asyncio.wait_for(stream.task, 2)
            assert SECRET not in json.dumps(stream.frames)

    asyncio.run(scenario())


def test_without_a_buffer_the_routes_return_an_empty_log(
    tmp_path: Path, effective_settings: Any
) -> None:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        body = client.get("/v1/logs").json()
        assert body["records"] == [] and body["last_seq"] == 0


def test_log_responses_conform(setup: Any) -> None:
    client, policy, _ = setup
    emit(logging.INFO, "one")
    emit(logging.ERROR, "two")
    check = ContractChecker()
    body = check.check(client.get("/v1/logs"), 200)
    assert len(body["records"]) == 2
    check.check(client.get("/v1/logs", params={"after": 1}), 200)
    check.check(client.get("/v1/logs", params={"after": -1}), 400)
    check.check(client.get("/v1/logs/stream", params={"after": -1}), 400)
    client.cookies.clear()
    read = bearer(policy, "read")
    check.check(client.get("/v1/logs", headers=read), 403)
    check.check(client.get("/v1/logs"), 401)
    check.check(client.get("/v1/logs/stream", headers=read), 403)
    check.check(client.get("/v1/logs/stream"), 401)
    assert {"getLogs"} <= check.operations


def test_stream_frames_conform(tmp_path: Path, effective_settings: Any, buffer: LogBuffer) -> None:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, buffer)
    emit(logging.INFO, "one")
    emit(logging.ERROR, "two")
    check = ContractChecker()

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            stream = LiveStream(app, policy, "/v1/logs/stream")
            await stream.wait_for(lambda frames: sum("id" in f for f in frames) >= 2)
            request_shutdown(app)
            await asyncio.wait_for(stream.task, 2)
            check.check(stream.response(), 200)
            assert stream.frames[-1]["event"] == "server.closing"

    asyncio.run(scenario())
    assert check.operations >= FAMILIES["logs"] - {"getLogs"}


# ── omrg web installs the handler ────────────────────────────────────────


def test_omrg_web_installs_the_buffer_on_the_root_logger_and_removes_it_on_exit(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_serve(app: Any, sock: Any) -> None:
        captured["buffer"] = app.state.log_buffer
        captured["attached"] = app.state.log_buffer in logging.getLogger().handlers
        sock.close()

    with patch("omrg.transports.cli.web._serve", side_effect=fake_serve):
        # --port 0: a login item on this machine can hold the default port 8765.
        result = CliRunner().invoke(
            cli_app, ["web", "--port", "0", "--workspace", str(tmp_path / "ws")]
        )
    assert result.exit_code == 0, result.output
    buffer = captured["buffer"]
    assert captured["attached"] is True
    assert buffer.capacity == 1000
    assert any(isinstance(item, RedactingFilter) for item in buffer.filters)
    assert buffer not in logging.getLogger().handlers


# ── Helpers ──────────────────────────────────────────────────────────────


def build_app_with_buffer(tmp_path: Path, engine: Any, log_buffer: LogBuffer) -> tuple[Any, Any]:
    from omrg.transports.api.security import AccessPolicy

    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: engine, log_buffer=log_buffer)
    return app, policy


class LiveStream:
    """One streamed ``GET`` driven through raw ASGI calls with the session cookie."""

    def __init__(
        self,
        app: Any,
        policy: Any,
        path: str,
        *,
        query: bytes = b"",
        last_event_id: str | None = None,
    ) -> None:
        self.frames: list[dict[str, Any]] = []
        self.status: int | None = None
        self.got_frame = asyncio.Event()
        self._leave = asyncio.Event()
        self._sent_request = False
        session = policy.exchange_bootstrap(policy.bootstrap_secret)
        assert session is not None
        self.path = path
        self.raw = ""
        self.headers: dict[str, str] = {}
        headers = [(b"host", b"127.0.0.1:8765")]
        headers.append((b"cookie", f"{policy.cookie_name}={session}".encode()))
        if last_event_id is not None:
            headers.append((b"last-event-id", last_event_id.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "root_path": "",
            "headers": headers,
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
            self.headers = {k.decode(): v.decode() for k, v in message["headers"]}
        elif message.get("body"):
            self.raw += message["body"].decode()
            self.frames += parse_sse(message["body"].decode())
            self.got_frame.set()

    def response(self) -> httpx.Response:
        """Return the finished stream as a response the contract checker accepts."""
        request = httpx.Request("GET", BASE + self.path)
        return httpx.Response(
            self.status or 0, headers=self.headers, text=self.raw, request=request
        )

    async def wait_for(self, predicate: Any, timeout: float = 5.0) -> None:
        async def poll() -> None:
            while not predicate(self.frames):
                self.got_frame.clear()
                await self.got_frame.wait()

        await asyncio.wait_for(poll(), timeout)


# ── Keys saved while the server runs (design D7; task 6.1) ───────────────

SAVED = "sk-or-v1-saved-key-0123456789abcdef"
REPLACED = "sk-or-v1-replaced-key-fedcba9876543210"


@pytest.fixture
def live_secrets() -> Iterator[tuple[LogBuffer, Any]]:
    """A buffer that starts with no keys, sharing a ``SecretSet`` with the app."""
    from omrg.transports.api.security import SecretSet

    secrets = SecretSet()
    log_buffer = LogBuffer(secrets)
    logger = logging.getLogger(LOGGER)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_buffer)
    propagate, logger.propagate = logger.propagate, False
    yield log_buffer, secrets
    logger.propagate = propagate
    logger.removeHandler(log_buffer)


def test_a_key_added_after_launch_is_removed_from_the_buffer(
    live_secrets: tuple[LogBuffer, Any],
) -> None:
    log_buffer, secrets = live_secrets
    secrets.add(SAVED)
    emit(logging.ERROR, "after the save %s", SAVED)
    try:
        raise RuntimeError(f"upstream echoed {SAVED}")
    except RuntimeError:
        logging.getLogger(LOGGER).exception("failure")
    text = json.dumps(log_buffer.records())
    assert SAVED not in text
    assert "after the save ***" in text


def test_a_replaced_key_stays_redacted(live_secrets: tuple[LogBuffer, Any]) -> None:
    log_buffer, secrets = live_secrets
    secrets.add(SAVED)
    secrets.add(REPLACED)
    emit(logging.ERROR, "old %s new %s", SAVED, REPLACED)
    text = json.dumps(log_buffer.records())
    assert SAVED not in text and REPLACED not in text


def _leak_two_keys(app: Any) -> None:
    # The key route adds a key to the app's set before it calls the keychain.
    app.state.secrets.add(SAVED)
    emit(logging.ERROR, "leak %s", SAVED)
    app.state.secrets.add(REPLACED)
    emit(logging.ERROR, "leak %s", REPLACED)


def test_the_logs_route_never_shows_a_saved_key(
    tmp_path: Path, effective_settings: Any, live_secrets: tuple[LogBuffer, Any]
) -> None:
    log_buffer, _ = live_secrets
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, log_buffer)
    _leak_two_keys(app)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/logs")
    assert SAVED not in response.text and REPLACED not in response.text
    assert "***" in response.text


def test_the_log_stream_never_shows_a_saved_key(
    tmp_path: Path, effective_settings: Any, live_secrets: tuple[LogBuffer, Any]
) -> None:
    log_buffer, _ = live_secrets
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app_with_buffer(tmp_path, engine, log_buffer)
    _leak_two_keys(app)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            stream = LiveStream(app, policy, "/v1/logs/stream")
            await stream.wait_for(lambda frames: sum("id" in f for f in frames) >= 2)
            emit(logging.ERROR, "live %s", REPLACED)
            await stream.wait_for(lambda frames: any("live" in str(f) for f in frames))
            request_shutdown(app)
            await asyncio.wait_for(stream.task, 2)
            dumped = json.dumps(stream.frames)
            assert SAVED not in dumped and REPLACED not in dumped

    asyncio.run(scenario())
