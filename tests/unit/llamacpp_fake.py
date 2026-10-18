"""A fake ``llama-server`` for tests. Not a test module.

``install_fake`` writes a small Python program named exactly ``llama-server``
into a folder (mode 755). The program records its argument list and its
environment next to itself, then serves ``GET /health`` and ``GET /v1/models``
on the port it was given. A ``mode`` file next to it tells it how to behave, so
a test can make it exit, hang, ignore SIGTERM, flood its output or answer
``503`` for a while. It never loads a model and never touches Ollama or the
user's own llama.cpp server.
"""

from __future__ import annotations

import asyncio
import json
import socket
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT = """#!{python}
import json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

here = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(here, "argv.json"), "w") as handle:
    json.dump(sys.argv, handle)
with open(os.path.join(here, "env.json"), "w") as handle:
    json.dump(dict(os.environ), handle)
with open(os.path.join(here, "starts.log"), "a") as handle:
    handle.write(str(os.getpid()) + "\\n")
with open(os.path.join(here, "mode")) as handle:
    mode = handle.read().strip()

if mode.startswith("exit:"):
    print("fatal: fake failure SECRET-CHILD-TEXT", flush=True)
    sys.exit(int(mode.split(":")[1]))
if mode == "ignore-term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == "hang":
    while True:
        time.sleep(1)
if mode == "flood":
    chunk = "x" * 1023 + "\\n"
    for _ in range(6 * 1024 + 512):
        sys.stdout.write(chunk)
    sys.stdout.flush()

port = int(sys.argv[sys.argv.index("--port") + 1])
began = time.time()
slow = float(mode.split(":")[1]) if mode.startswith("slow:") else 0.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        ready = time.time() - began >= slow
        if self.path == "/health" and ready:
            body, code = b'{{"status":"ok"}}', 200
        elif self.path == "/health":
            body, code = b'{{"error":"loading"}}', 503
        elif self.path.endswith("/models"):
            body, code = b'{{"data":[]}}', 200
        else:
            body, code = b"{{}}", 404
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if mode.startswith("die-after:"):
    deadline = time.time() + float(mode.split(":")[1])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 0.05
    while time.time() < deadline:
        server.handle_request()
    sys.exit(7)
HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


@dataclass
class FakeServerProgram:
    """The fake program on disk and the files it writes."""

    path: Path

    def set_mode(self, mode: str) -> None:
        (self.path.parent / "mode").write_text(mode, encoding="utf-8")

    def argv(self) -> list[str]:
        return json.loads((self.path.parent / "argv.json").read_text(encoding="utf-8"))

    def env(self) -> dict[str, str]:
        return json.loads((self.path.parent / "env.json").read_text(encoding="utf-8"))

    def pids(self) -> list[int]:
        log = self.path.parent / "starts.log"
        return [int(x) for x in log.read_text().split()] if log.exists() else []


def install_fake(folder: Path, mode: str = "ok") -> FakeServerProgram:
    """Write the fake ``llama-server`` into *folder* and return its handle."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "llama-server"
    path.write_text(SCRIPT.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    program = FakeServerProgram(path)
    program.set_mode(mode)
    return program


def free_port() -> int:
    """Return a TCP port on 127.0.0.1 that nothing listens on right now."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until(probe: Any, timeout: float = 15.0) -> Any:
    """Poll *probe* until it returns a truthy value or *timeout* seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


async def await_until(probe: Any, timeout: float = 15.0) -> Any:
    """Like :func:`wait_until`, but yields to the event loop between polls."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        await asyncio.sleep(0.05)
    raise AssertionError("condition not reached in time")
