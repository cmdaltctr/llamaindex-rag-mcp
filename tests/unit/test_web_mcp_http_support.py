"""Helpers for the MCP-over-HTTP tests: a live loopback server and clients.

Not a test module. The server is a real Uvicorn on a pre-bound loopback
socket (as ``omrg web`` binds it), so the SDK's streamable HTTP client
talks to it over real HTTP, including server-sent events.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from conftest import build_mcp_engine  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402


@dataclass
class Live:
    """A running web server and what the tests need to reach it."""

    port: int
    policy: AccessPolicy
    workspace: Path
    engine: Any
    app: Any
    roots: tuple[Path, ...]
    server: Any = None
    _clients: list[httpx.Client] = field(default_factory=list)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.base}/mcp"

    def browser(self) -> httpx.Client:
        """Return the client holding this server's browser session (cookie).

        The bootstrap secret works once, so every call returns the same client.
        """
        if self._clients:
            return self._clients[0]
        client = httpx.Client(base_url=self.base, headers={"Origin": self.base})
        self._clients.append(client)
        response = client.post("/v1/session", json={"bootstrap": self.policy.bootstrap_secret})
        assert response.status_code == 200, response.text
        return client

    def close(self) -> None:
        for client in self._clients:
            client.close()


def _free_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    sock.set_inheritable(True)
    return sock


@contextmanager
def live_server(
    workspace: Path,
    roots: tuple[Path, ...] = (),
    *,
    engine_factory: Callable[[], Any] | None = None,
    extra_origins: tuple[str, ...] = (),
) -> Iterator[Live]:
    """Run the web app on a real socket until the block ends.

    The same *workspace* may be reused for a second launch, which is how the
    tests prove that settings and the token survive a restart.
    """
    sock = _free_socket()
    port = sock.getsockname()[1]
    config = WebConfig(workspace=workspace, port=port, roots=roots, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, port, extra_origins=extra_origins)
    engines: list[Any] = []

    def make_engine() -> Any:
        engines.append((engine_factory or build_mcp_engine)())
        return engines[-1]

    app = create_app(
        config, policy=policy, engine_factory=make_engine, run_service_factory=run_service_factory
    )
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=None, lifespan="on", access_log=False, ws="none")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    live = Live(port, policy, workspace, engines[0], app, roots, server)
    try:
        yield live
    finally:
        live.close()
        server.should_exit = True
        thread.join(timeout=30)
        sock.close()
        assert not thread.is_alive(), "server did not stop"


def enable_mcp(live: Live, *, token: bool = True) -> str | None:
    """Turn MCP over HTTP on through the API; return a new token."""
    browser = live.browser()
    response = browser.put("/v1/mcp", json={"enabled": True})
    assert response.status_code == 200, response.text
    if not token:
        return None
    created = browser.post("/v1/mcp/token")
    assert created.status_code in (200, 201), created.text
    return created.json()["token"]


def mcp_post(live: Live, token: str | None, body: dict, **headers: str) -> httpx.Response:
    """POST a JSON-RPC message to ``/mcp`` with an optional bearer token."""
    send = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token is not None:
        send["Authorization"] = f"Bearer {token}"
    send.update(headers)
    return httpx.post(live.mcp_url, json=body, headers=send, timeout=30)


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
