"""The single install job that adds an allowed extra to this server (design D1, D3).

One :class:`InstallJob` lives on ``WebRuntime``, so one install runs per
server at a time. The job runs
``uv pip install --python <this Python> <requirements>`` as an argument
list with no shell and no stdin. The requirements come from the installed
package metadata; no request text reaches the argument list.

The process gets the server environment without any ``*_API_KEY``
variable. Its output (stderr merged into stdout) is redacted line by line
and only the last :data:`MAX_OUTPUT_LINES` lines are kept. The job stops
the process after :data:`INSTALL_TIMEOUT_SECONDS`.

After exit code 0 the job runs ``uv pip check --python <this Python>``
with the same limits, because an install can move a package another one
needs (ADR-094). A conflict fails the install with ``check-failed``.

After a successful check the extra goes into ``restart_needed``: the
running process cannot use the new modules safely until it restarts. The
state is kept in memory, so a restart shows ``idle`` again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .install_environment import InstallEnvironment, detect_environment, extra_requirements
from .security import redact

logger = logging.getLogger(__name__)

#: Seconds one install may take before the job stops it (10 minutes).
INSTALL_TIMEOUT_SECONDS = 600.0
#: Output lines kept for the status route.
MAX_OUTPUT_LINES = 40

IDLE = "idle"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"


class InstallRunning(RuntimeError):
    """Raised when an install starts while another one runs."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _child_environment() -> tuple[dict[str, str], list[str]]:
    """Return the server environment without ``*_API_KEY`` variables, and their values."""
    env: dict[str, str] = {}
    removed: list[str] = []
    for name, value in os.environ.items():
        if name.upper().endswith("_API_KEY"):
            removed.append(value)
        else:
            env[name] = value
    return env, removed


def _stop(process: asyncio.subprocess.Process) -> None:
    """Kill the process group, so a child of ``uv`` stops too."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()


@dataclass
class InstallJob:
    """State and runner of the one install this server may run.

    Attributes:
        timeout: Seconds before the job stops the process.
        python: The Python whose environment receives the packages.
        detect: Returns the install type and ``uv`` path (tests replace it).
        requirements: Returns an extra's requirements (tests replace it).
        restart_needed: Extras installed in this launch.
    """

    timeout: float = INSTALL_TIMEOUT_SECONDS
    python: str = field(default_factory=lambda: sys.executable)
    detect: Callable[[], InstallEnvironment] = detect_environment
    requirements: Callable[[str], list[str]] = extra_requirements
    restart_needed: set[str] = field(default_factory=set)
    _state: str = IDLE
    _extra: str | None = None
    _started_at: str | None = None
    _finished_at: str | None = None
    _reason: str | None = None
    _exit_code: int | None = None
    _output: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_OUTPUT_LINES))
    _task: asyncio.Task[None] | None = None
    _process: asyncio.subprocess.Process | None = None

    @property
    def running(self) -> bool:
        """Whether an install runs now."""
        return self._state == RUNNING

    def snapshot(self) -> dict[str, Any]:
        """Return the state in the ``IntegrationInstall`` shape."""
        return {
            "state": self._state,
            "extra": self._extra,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "reason": self._reason,
            "exit_code": self._exit_code,
            "output": list(self._output),
        }

    def start(
        self,
        extra: str,
        uv: str,
        packages: list[str],
        *,
        redactor: Callable[[str], str] | None = None,
    ) -> None:
        """Start installing *packages* for *extra*. Call it on the event loop.

        Args:
            extra: The allowed extra, already checked by the caller.
            uv: Path of the ``uv`` program.
            packages: The extra's requirements from the package metadata.
            redactor: ``Engine.redact``; removes provider credential values.

        Raises:
            InstallRunning: Another install runs.
        """
        if self.running:
            raise InstallRunning(f"The {self._extra} install is running.")
        self._state, self._extra = RUNNING, extra
        self._started_at, self._finished_at = _now(), None
        self._reason, self._exit_code = None, None
        self._output.clear()
        argv = [uv, "pip", "install", "--python", self.python, *packages]
        self._task = asyncio.get_running_loop().create_task(self._run(argv, redactor))

    async def wait(self) -> None:
        """Wait until the current install ends. Returns at once when idle."""
        if self._task is not None:
            await asyncio.shield(self._task)

    def _finish(self, state: str, reason: str | None, exit_code: int | None) -> None:
        self._state, self._reason, self._exit_code = state, reason, exit_code
        self._finished_at = _now()
        if state == SUCCEEDED and self._extra is not None:
            self.restart_needed.add(self._extra)
        logger.info("Install of %s ended: %s %s", self._extra, state, reason or "")

    async def _run(self, argv: list[str], redactor: Callable[[str], str] | None) -> None:
        env, secrets = _child_environment()

        def clean(text: str) -> str:
            return redact(redactor(text) if redactor else text, secrets)

        check = [argv[0], "pip", "check", "--python", self.python]
        try:
            reason, code = await asyncio.wait_for(
                self._steps(argv, check, env, clean), self.timeout
            )
        except TimeoutError:
            # Before OSError: TimeoutError is one of its subclasses.
            await self._stop_current()
            self._finish(FAILED, "timed-out", None)
            return
        except OSError:
            logger.warning("Could not start the install of %s.", self._extra)
            self._finish(FAILED, "start-failed", None)
            return
        except asyncio.CancelledError:
            # The server is shutting down: stop the process and keep no result.
            if self._process is not None:
                _stop(self._process)
            raise
        self._finish(SUCCEEDED if reason is None else FAILED, reason, code)

    async def _steps(
        self, install: list[str], check: list[str], env: dict[str, str], clean: Callable[[str], str]
    ) -> tuple[str | None, int]:
        """Run the install, then the check; return the failure reason (or ``None``) and the code."""
        code = await self._exec(install, env, clean)
        if code != 0:
            return "exit-code", code
        code = await self._exec(check, env, clean)
        return (None if code == 0 else "check-failed"), code

    async def _exec(self, argv: list[str], env: dict[str, str], clean: Callable[[str], str]) -> int:
        """Run one argument list, keep its redacted output lines and return the exit code."""
        self._process = process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        if process.stdout is not None:
            async for raw in process.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._output.append(clean(line))
        return await process.wait()

    async def _stop_current(self) -> None:
        """Stop the running process after a timeout and wait for it to end."""
        if self._process is not None:
            _stop(self._process)
            await self._process.wait()
