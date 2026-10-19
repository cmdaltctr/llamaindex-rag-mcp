"""The fake ``llama-server`` must not depend on the runner's DNS.

``HTTPServer`` looks up the host name of its address when it binds. That
reverse lookup can stall on a CI runner, so the fake would not answer
``/health`` in time and every lifecycle test would fail.
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from tests.unit.llamacpp_fake import free_port, install_fake, wait_until

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shebang program")

_NO_REVERSE_DNS = (
    "import socket\n"
    "def _refuse(*args, **kwargs):\n"
    "    raise OSError('reverse DNS is not allowed in this test')\n"
    "socket.getfqdn = _refuse\n"
)


def _health(port: int) -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as reply:
            return int(reply.status)
    except (urllib.error.URLError, OSError):
        return 0


def test_the_fake_answers_health_without_a_reverse_dns_lookup(tmp_path: Path) -> None:
    program = install_fake(tmp_path / "bin")
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(_NO_REVERSE_DNS, encoding="utf-8")
    port = free_port()
    proc = subprocess.Popen(
        [str(program.path), "--port", str(port)],
        env={**os.environ, "PYTHONPATH": str(hook)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until(lambda: _health(port) == 200, timeout=10.0)
    finally:
        proc.kill()
        proc.wait()
