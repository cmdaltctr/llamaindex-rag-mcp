"""Fake external executables for plugin and launcher tests.

Each fake is a small Python script with a shebang. Nothing here installs or
runs a real notebook editor.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

FAKE_HELP = (
    "Usage: marimo edit [OPTIONS] [NAME]\n"
    "  -p, --port INTEGER\n  --host TEXT\n  --headless\n  --token / --no-token\n"
    "  --token-password-file TEXT\n  --skip-update-check\n  --no-sandbox\n"
)

_FAKE_EDITOR = r'''#!{python}
"""Fake marimo-like editor. Behaviour switches are files next to this script."""
import json, os, signal, socket, stat, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
version_file = HERE / "version.txt"
if args == ["--version"]:
    print(version_file.read_text().strip() if version_file.exists() else "0.25.1")
    sys.exit(0)
if args[:2] == ["edit", "--help"]:
    print({help!r})
    sys.exit(0)
if not args or args[0] != "edit":
    sys.exit(2)

def value(flag):
    return args[args.index(flag) + 1]

host, port, token_file = value("--host"), int(value("--port")), value("--token-password-file")
token = Path(token_file).read_text()
config = Path(".marimo.toml")
child = subprocess.Popen([sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"])
record = {{
    "argv": args,
    "env": dict(os.environ),
    "cwd": os.getcwd(),
    "token_mode": stat.S_IMODE(os.stat(token_file).st_mode),
    "token_length": len(token),
    "config": config.read_text() if config.exists() else None,
    "pid": os.getpid(),
    "pgid": os.getpgid(0),
    "child_pid": child.pid,
}}
connection_path = os.environ.get("OMRG_CONNECTION_FILE")
if connection_path:
    connection = json.loads(Path(connection_path).read_text())
    record["connection_path"] = connection_path
    record["connection_mode"] = stat.S_IMODE(os.stat(connection_path).st_mode)
    record["connection"] = connection
    record["api_token_mode"] = stat.S_IMODE(os.stat(connection["token_file"]).st_mode)
    record["api_token"] = Path(connection["token_file"]).read_text()
tmp = HERE / "record.json.tmp"
tmp.write_text(json.dumps(record))
tmp.rename(HERE / "record.json")
if (HERE / "ignore_term").exists():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if (HERE / "exit_early").exists():
    sys.exit(7)
print("URL: http://%s:%d?access_token=%s" % (host, port, token), flush=True)
if (HERE / "never_listen").exists():
    while True:
        time.sleep(0.05)
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((host, port))
server.listen()
while True:
    conn, _ = server.accept()
    conn.close()
'''


def make_fake_editor(directory: Path, name: str = "marimo") -> Path:
    """Write the fake editor executable into ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(_FAKE_EDITOR.format(python=sys.executable, help=FAKE_HELP))
    path.chmod(0o755)
    return path


def make_script(directory: Path, name: str, body: str) -> Path:
    """Write an executable Python script with ``body`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o755)
    return path


def free_port() -> int:
    """Return a loopback port that is free at the time of the call."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_record(directory: Path, timeout: float = 5.0) -> dict:
    """Wait for and return the fake editor's launch record."""
    path = directory / "record.json"
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError("fake editor wrote no record")
        time.sleep(0.02)
    return json.loads(path.read_text())


def alive(pid: int) -> bool:
    """Return whether ``pid`` exists and is not a zombie."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(  # noqa: S603
        ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def wait_gone(pid: int, timeout: float = 5.0) -> bool:
    """Wait until ``pid`` is gone; return whether it went."""
    deadline = time.monotonic() + timeout
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def unrelated_listener(port: int) -> Iterator[subprocess.Popen[bytes]]:
    """Run an unrelated loopback listener in its own session for the test."""
    code = (
        "import socket, sys, time\n"
        "s = socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen()\n"
        "print('ready', flush=True)\n"
        "while True: time.sleep(0.05)\n"
    )
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", code, str(port)], stdout=subprocess.PIPE, start_new_session=True
    )
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == b"ready"
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=5)


def write_json(path: Path, data: object) -> None:
    """Write JSON to ``path``."""
    path.write_text(json.dumps(data))
