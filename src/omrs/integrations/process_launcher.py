"""Generic owned-process adapter for external tools (design D10, task 8.3).

This is the only plugin module that starts processes. It never uses a shell.
Each launch gets a private directory (0o700) for its transient files (0o600),
its own process group, an allow-listed environment, and a loopback address.
The inherited environment keeps only :data:`ENV_ALLOWLIST`. A launch can add
per-launch values only for the names in :data:`LAUNCH_ENV_ALLOWLIST` (the
path of the private OMRS connection file); no secret may appear in them.
The launcher tracks only the process groups it creates. It refuses a port
that another program already uses, and it never adopts or signals that
program. Stop sends SIGTERM to the owned group, waits a bounded time, then
sends SIGKILL. Output is kept in a small in-memory buffer with secrets
redacted; nothing is written to a log file.

The module is an integration leaf: it imports nothing from ``omrs.core``.
The core plugin package depends on it only through structural protocols.
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1"})
ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR",
    "TERM", "SYSTEMROOT",
)  # fmt: skip
#: Names a single launch may set. The value is never inherited from this process.
LAUNCH_ENV_ALLOWLIST: tuple[str, ...] = ("OMRS_CONNECTION_FILE",)
REDACTED = "[redacted]"
_FILE_NAME = re.compile(r"^\.?[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_OUTPUT_LINES = 200
_LINE_LIMIT = 2000


class PortInUseError(OSError):
    """Another program listens on the requested port. It is left alone."""


class LaunchError(RuntimeError):
    """An owned process failed to start or to become ready."""


@dataclass(frozen=True)
class ProbeOutput:
    """Output of one probe command."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class StopResult:
    """Outcome of stopping one owned launch."""

    launch_id: str
    stopped: bool
    escalated: bool
    returncode: int | None


@dataclass
class _Owned:
    launch_id: str
    popen: subprocess.Popen[bytes]
    workdir: Path
    host: str
    port: int
    output: deque[str] = field(default_factory=lambda: deque(maxlen=_OUTPUT_LINES))
    reader: threading.Thread | None = None


def allowed_environment(
    source: Mapping[str, str] | None = None, allowlist: Sequence[str] = ENV_ALLOWLIST
) -> dict[str, str]:
    """Return only the allow-listed variables from ``source`` (default: this process)."""
    env = os.environ if source is None else source
    return {key: env[key] for key in allowlist if key in env}


def port_in_use(host: str, port: int) -> bool:
    """Return whether something listens on, or holds, ``host:port``."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) == 0:
            return True
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        # SO_REUSEADDR ignores TIME_WAIT left by an earlier owned launch;
        # an active listener still makes the bind fail.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


class SubprocessProbeRunner:
    """Runs short probe commands (for example ``--version``) without a shell.

    Args:
        max_output: Characters kept from each output stream.
    """

    def __init__(self, *, max_output: int = 64 * 1024) -> None:
        self._max_output = max_output

    def run(self, argv: Sequence[str], *, timeout: float) -> ProbeOutput:
        """Run ``argv`` in its own process group and return its output.

        Raises:
            OSError: If the executable cannot start.
            TimeoutError: If it runs longer than ``timeout``; its group is killed.
        """
        proc = subprocess.Popen(  # noqa: S603 - operator-approved argv, no shell
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=allowed_environment(),
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _signal_group(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise TimeoutError(f"{argv[0]} did not finish within {timeout} s") from exc
        limit = self._max_output
        return ProbeOutput(
            proc.returncode,
            out.decode("utf-8", "replace")[:limit],
            err.decode("utf-8", "replace")[:limit],
        )


class OwnedProcessLauncher:
    """Starts, tracks and stops process groups that this launcher owns.

    Args:
        runtime_dir: Parent of the private launch directories.
        grace_seconds: Wait after SIGTERM before escalation.
        kill_wait_seconds: Wait after SIGKILL before giving up.
        ready_timeout: Wait for the process to listen on its port.
        environment: Source for allow-listed variables (default: this process).
    """

    def __init__(
        self,
        runtime_dir: Path,
        *,
        grace_seconds: float = 5.0,
        kill_wait_seconds: float = 5.0,
        ready_timeout: float = 30.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self._grace = grace_seconds
        self._kill_wait = kill_wait_seconds
        self._ready_timeout = ready_timeout
        self._environment = environment
        self._owned: dict[str, _Owned] = {}
        self._dirs: set[Path] = set()
        self._lock = threading.Lock()

    # --- launch directories -------------------------------------------

    def create_launch_dir(self) -> Path:
        """Create and return a private (0o700) directory for one launch."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = Path(tempfile.mkdtemp(prefix="launch-", dir=self.runtime_dir))
        with self._lock:
            self._dirs.add(path)
        return path

    def discard_launch_dir(self, workdir: Path) -> None:
        """Remove an unused launch directory that this launcher created."""
        with self._lock:
            if workdir not in self._dirs or any(o.workdir == workdir for o in self._owned.values()):
                return
            self._dirs.discard(workdir)
        shutil.rmtree(workdir, ignore_errors=True)

    def port_available(self, host: str, port: int) -> bool:
        """Return whether nothing listens on ``host:port``."""
        return not port_in_use(host, port)

    # --- start --------------------------------------------------------

    def start(
        self,
        *,
        argv: Sequence[str],
        workdir: Path,
        host: str,
        port: int,
        files: Mapping[str, str],
        secrets: Sequence[str],
        environment: Mapping[str, str] | None = None,
    ) -> str:
        """Write private files, start ``argv`` in a new process group, wait until it listens.

        Args:
            argv: Executable and arguments, run without a shell.
            workdir: A launch directory from :meth:`create_launch_dir`.
            host: Loopback address the process binds.
            port: Port the process must listen on.
            files: Private files (0o600) to write into ``workdir`` first.
            secrets: Values that must not appear in ``argv`` or ``environment``;
                they are redacted from the output buffer.
            environment: Per-launch variables, names from
                :data:`LAUNCH_ENV_ALLOWLIST` only.

        Raises:
            ValueError: If the host is not loopback, ``workdir`` is not an
                owned launch directory, a file name is unsafe, a per-launch
                variable is not allow-listed or holds a secret, or a secret
                appears in ``argv``.
            PortInUseError: If another program uses the port.
            OSError: If the executable cannot start.
            LaunchError: If the process exits or does not listen in time.
        """
        self._check_request(argv, workdir, host, secrets, files)
        extra = _launch_environment(environment or {}, secrets)
        if port_in_use(host, port):
            raise PortInUseError(
                errno.EADDRINUSE, f"port {host}:{port} is used by another program; it is left alone"
            )
        for name, content in files.items():
            _write_private(workdir / name, content)
        popen = subprocess.Popen(  # noqa: S603 - validated argv list, no shell
            list(argv),
            cwd=workdir,
            env={**allowed_environment(self._environment), **extra},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        owned = _Owned(uuid.uuid4().hex, popen, workdir, host, port)
        owned.reader = _start_reader(popen.stdout, owned.output, [s for s in secrets if s])
        with self._lock:
            self._owned[owned.launch_id] = owned
        self._wait_ready(owned)
        return owned.launch_id

    def _check_request(
        self,
        argv: Sequence[str],
        workdir: Path,
        host: str,
        secrets: Sequence[str],
        files: Mapping[str, str],
    ) -> None:
        if host not in LOOPBACK_HOSTS:
            raise ValueError(f"owned processes bind to loopback only, not {host!r}")
        with self._lock:
            if workdir not in self._dirs:
                raise ValueError(f"not a launch directory created by this launcher: {workdir}")
        if not argv:
            raise ValueError("argv must not be empty")
        if any(secret and secret in arg for secret in secrets for arg in argv):
            raise ValueError("a secret must not appear in argv; pass it in a private file")
        for name in files:
            if not _FILE_NAME.match(name) or ".." in name:
                raise ValueError(f"unsafe file name: {name!r}")

    def _wait_ready(self, owned: _Owned) -> None:
        deadline = time.monotonic() + self._ready_timeout
        while time.monotonic() < deadline:
            code = owned.popen.poll()
            if code is not None:
                self._abandon(owned)
                raise LaunchError(
                    f"process exited with code {code} before it listened on "
                    f"{owned.host}:{owned.port}. Last output: {self._tail(owned)}"
                )
            if port_in_use(owned.host, owned.port):
                return
            time.sleep(0.05)
        self._abandon(owned)
        raise LaunchError(
            f"process did not listen on {owned.host}:{owned.port} within "
            f"{self._ready_timeout} s; it was stopped. Last output: {self._tail(owned)}"
        )

    def _abandon(self, owned: _Owned) -> None:
        with self._lock:
            self._owned.pop(owned.launch_id, None)
        self._terminate(owned)

    # --- inspection ---------------------------------------------------

    def owned_ids(self) -> list[str]:
        """Return the ids of launches this launcher still owns."""
        with self._lock:
            return list(self._owned)

    def is_running(self, launch_id: str) -> bool:
        """Return whether an owned launch's leader process is still running."""
        with self._lock:
            owned = self._owned.get(launch_id)
        return owned is not None and owned.popen.poll() is None

    def recent_output(self, launch_id: str) -> list[str]:
        """Return the last output lines of an owned launch, with secrets redacted."""
        with self._lock:
            owned = self._owned.get(launch_id)
        return list(owned.output) if owned is not None else []

    def _tail(self, owned: _Owned) -> str:
        if owned.reader is not None:
            owned.reader.join(timeout=1.0)
        return " | ".join(list(owned.output)[-5:]) or "(none)"

    # --- stop ---------------------------------------------------------

    def stop(self, launch_id: str) -> StopResult:
        """Stop one owned launch and remove its launch directory.

        Raises:
            KeyError: If this launcher does not own ``launch_id``.
        """
        with self._lock:
            owned = self._owned.pop(launch_id)
        return self._terminate(owned)

    def stop_all(self) -> list[StopResult]:
        """Stop every owned launch."""
        with self._lock:
            owned = list(self._owned.values())
            self._owned.clear()
        return [self._terminate(item) for item in owned]

    def _terminate(self, owned: _Owned) -> StopResult:
        pgid = owned.popen.pid  # start_new_session makes the leader's pid the group id
        _signal_group(pgid, signal.SIGTERM)
        stopped = self._wait_group(owned, self._grace)
        escalated = False
        if not stopped:
            escalated = True
            _signal_group(pgid, signal.SIGKILL)
            stopped = self._wait_group(owned, self._kill_wait)
        if owned.reader is not None:
            owned.reader.join(timeout=1.0)
        with self._lock:
            self._dirs.discard(owned.workdir)
        shutil.rmtree(owned.workdir, ignore_errors=True)
        return StopResult(owned.launch_id, stopped, escalated, owned.popen.poll())

    @staticmethod
    def _wait_group(owned: _Owned, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            owned.popen.poll()  # reap the leader so it does not linger as a zombie
            if owned.popen.returncode is not None and not _group_exists(owned.popen.pid):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def _signal_group(pgid: int, sig: int) -> None:
    # The id is a group this launcher created. POSIX does not reuse a pid
    # while a process group with that id exists, so this reaches only
    # members of the owned group (or nothing).
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _launch_environment(environment: Mapping[str, str], secrets: Sequence[str]) -> dict[str, str]:
    """Return the checked per-launch variables.

    Raises:
        ValueError: A name is not in :data:`LAUNCH_ENV_ALLOWLIST`, or a value
            is empty, holds a NUL byte or holds a secret.
    """
    for name, value in environment.items():
        if name not in LAUNCH_ENV_ALLOWLIST:
            raise ValueError(f"per-launch environment variable not allowed: {name!r}")
        if not value or "\x00" in value:
            raise ValueError(f"per-launch environment variable {name} needs a plain value")
        if any(secret and secret in value for secret in secrets):
            raise ValueError(
                "a secret must not appear in the environment; pass it in a private file"
            )
    return dict(environment)


def _write_private(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(content)


def _start_reader(
    stream: IO[bytes] | None, sink: deque[str], secrets: Sequence[str]
) -> threading.Thread | None:
    if stream is None:
        return None

    def read() -> None:
        with stream:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\n")[:_LINE_LIMIT]
                for secret in secrets:
                    line = line.replace(secret, REDACTED)
                sink.append(line)

    thread = threading.Thread(target=read, name="owned-process-output", daemon=True)
    thread.start()
    return thread
