"""Start, check and stop the local llama-server for Clef-flash Q8_0 (design D7).

The Experiment 38 client (jev_hosted.OPENJEV_ENDPOINT) posts to 127.0.0.1:3000,
so the server uses that port.
"""

from __future__ import annotations

import re
import subprocess
import time
import urllib.request
from pathlib import Path

from exp42_io import OUTPUT, V3_EXP38, sha256

BINARY = OUTPUT / "bin" / "llama-b11510" / "llama-server"
MODEL = V3_EXP38 / "output" / ".models" / "clef" / "gguf" / "Clef-Flash-Q8_0.gguf"
HOST, PORT = "127.0.0.1", 3000
MIN_BUILD = 11510
#: A 2,000-character head can exceed the 512-token default batch in embedding mode.
BATCH = "8192"


def build_number() -> tuple[int, str]:
    """Return the build number and the full version line."""
    out = subprocess.run(  # noqa: S603
        [str(BINARY), "--version"], capture_output=True, text=True, check=False
    )
    line = next((x for x in (out.stdout + out.stderr).splitlines() if x.startswith("version:")), "")
    match = re.search(r"build (\d+)", line)
    return (int(match.group(1)) if match else -1), line.strip()


def start(log: Path) -> subprocess.Popen:
    """Start the server bound to 127.0.0.1 and wait until /health answers."""
    handle = log.open("ab")
    process = subprocess.Popen(  # noqa: S603
        [
            str(BINARY),
            "-m",
            str(MODEL),
            "--host",
            HOST,
            "--port",
            str(PORT),
            "-b",
            BATCH,
            "-ub",
            BATCH,
        ],
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=5) as r:  # noqa: S310
                if r.status == 200:
                    return process
        except OSError:
            pass
        time.sleep(2)
    process.terminate()
    raise RuntimeError("llama-server did not become healthy in 300 s")


def listen_addresses(pid: int) -> list[str]:
    """Return the TCP listen addresses of *pid* (lsof)."""
    out = subprocess.run(  # noqa: S603
        ["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return re.findall(r"TCP (\S+) \(LISTEN\)", out)


def stop(process: subprocess.Popen) -> None:
    """Stop the server."""
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()


def static_checks(expected_sha256: str) -> dict:
    """Build and model-hash checks that need no running server."""
    build, line = build_number()
    digest = sha256(MODEL)
    return {
        "llama_cpp_build": {"value": line, "pass": build >= MIN_BUILD},
        "model_sha256": {"value": digest, "pass": digest == expected_sha256},
    }
