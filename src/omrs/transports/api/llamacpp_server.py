"""The llama.cpp server that ``omrs web`` starts and owns (design D12).

:class:`LlamacppServer` keeps the handle of the one process it launched. It
signals that process group and nothing else. It never lists processes, never
looks a process up by name or port and never touches a server the user
started: when the chat port is already taken, a start is refused with
``port-in-use``.

The module belongs to the web transport only. The CLI and the stdio MCP server
do not import it. Nothing here returns child output: the status holds a state,
one reason from a fixed set and an exit code. The child writes to a capped log
file in the workspace folder, which no route reads.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import os
import signal
import socket
import subprocess
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from ...core.providers.llm import llamacpp_rules as rules

logger = logging.getLogger(__name__)

State = Literal["stopped", "starting", "running", "failed"]

#: The log file never grows past this many bytes.
LOG_CAP_BYTES = 5 * 1024 * 1024
#: Seconds to wait for ``GET /health`` to return 200.
HEALTH_TIMEOUT = 180.0
#: Seconds between SIGTERM and SIGKILL.
STOP_GRACE = 10.0


@dataclass(frozen=True)
class LaunchConfig:
    """The saved values one launch uses.

    Attributes:
        binary: Program path.
        model: ``.gguf`` path or Hugging Face id.
        context_window: Tokens passed as ``-c``.
        chat_url: The chat address. Its port is the port of the server.
        idle_sleep: Seconds passed as ``--sleep-idle-seconds``; 0 sends no flag.
    """

    binary: str
    model: str
    context_window: int
    chat_url: str
    idle_sleep: int = 0


@dataclass(frozen=True)
class StartedWith:
    """What the running process was started with, to detect a pending restart."""

    binary: str
    model: str
    model_kind: rules.ModelKind
    context_window: int
    idle_sleep: int = 0


@dataclass(frozen=True)
class ServerStatus:
    """The state of the owned server. ``reason`` is one of ``REASONS`` or ``None``."""

    state: State
    reason: str | None = None
    exit_code: int | None = None
    pid_running: bool = False
    started_with: StartedWith | None = None


class _Readable(Protocol):
    def read(self, size: int) -> bytes: ...


def pump_capped(source: _Readable, path: Path, cap: int = LOG_CAP_BYTES) -> None:
    """Copy *source* to *path* until *cap* bytes are written, then drain the rest.

    The file is emptied first and created with mode 0600. Output past the cap
    is read and dropped, so the child never blocks on a full pipe.
    """
    written = 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        while chunk := source.read(65536):
            room = cap - written
            if room > 0:
                part = chunk[:room]
                handle.write(part)
                handle.flush()
                written += len(part)


def port_in_use(port: int) -> bool:
    """Return whether something accepts connections on 127.0.0.1:*port*."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


class LlamacppServer:
    """Starts, watches and stops one owned ``llama-server`` process.

    Args:
        log_path: File that receives the child's output (emptied at each start).
        health_timeout: Seconds to wait for ``/health`` to return 200.
        stop_grace: Seconds between SIGTERM and SIGKILL.
        poll_interval: Seconds between health checks.
        popen: Process factory; tests wrap it to record the call.
        environ: The environment the child's variables are taken from.
    """

    def __init__(
        self,
        log_path: Path,
        *,
        health_timeout: float = HEALTH_TIMEOUT,
        stop_grace: float = STOP_GRACE,
        poll_interval: float = 0.5,
        popen: Callable[..., Any] = subprocess.Popen,
        environ: Callable[[], Any] = lambda: os.environ,
    ) -> None:
        """Create a stopped manager. Nothing starts until :meth:`start`."""
        self.log_path = Path(log_path)
        self._health_timeout = health_timeout
        self._stop_grace = stop_grace
        self._poll_interval = poll_interval
        self._popen = popen
        self._environ = environ
        self._lock = asyncio.Lock()
        self._proc: Any = None
        self._watcher: asyncio.Task[None] | None = None
        self._pump: threading.Thread | None = None
        self._state: State = "stopped"
        self._reason: str | None = None
        self._exit_code: int | None = None
        self._started_with: StartedWith | None = None
        self._hooked = False

    # ── Status ───────────────────────────────────────────────────────────

    def status(self) -> ServerStatus:
        """Return the state. An owned process that has ended reads as ``failed``/``exited``."""
        self._refresh()
        return ServerStatus(
            state=self._state,
            reason=self._reason,
            exit_code=self._exit_code,
            pid_running=self._proc is not None and self._proc.poll() is None,
            started_with=self._started_with,
        )

    def _refresh(self) -> None:
        proc = self._proc
        if proc is None or self._state not in ("starting", "running"):
            return
        code = proc.poll()
        if code is not None:
            self._ended(proc, code)

    def _ended(self, proc: Any, code: int) -> None:
        if proc is not self._proc:
            return
        self._proc = None
        self._started_with = None
        self._state, self._reason, self._exit_code = "failed", "exited", code

    def _fail(self, reason: str) -> None:
        self._state, self._reason, self._exit_code = "failed", reason, None
        self._started_with = None

    # ── Start ────────────────────────────────────────────────────────────

    async def start(self, config: LaunchConfig) -> ServerStatus:
        """Check the rules, launch the process and begin watching its health.

        A server that is already ``starting`` or ``running`` is left alone.
        Every refusal is a ``failed`` status with one fixed reason and no
        process.
        """
        async with self._lock:
            self._refresh()
            if self._proc is not None and self._state in ("starting", "running"):
                return self.status()
            checked = await asyncio.to_thread(self._check, config)
            if isinstance(checked, str):
                self._fail(checked)
                return self.status()
            kind, port = checked
            self._launch(config, kind, port)
            return self.status()

    def _check(self, config: LaunchConfig) -> str | tuple[rules.ModelKind, int]:
        """Return a failure reason, or the model kind and port when every rule holds."""
        if not config.binary.strip() or not config.model.strip():
            return "not-configured"
        if not rules.check_binary(config.binary):
            return "binary-invalid"
        kind = rules.model_kind(config.model)
        if kind is None:
            return "model-invalid"
        port = rules.chat_port(config.chat_url)
        if port is None:
            return "not-loopback"
        if port_in_use(port):
            return "port-in-use"
        return kind, port

    def _launch(self, config: LaunchConfig, kind: rules.ModelKind, port: int) -> None:
        argv = rules.build_argv(
            config.binary,
            config.model,
            kind,
            port,
            config.context_window,
            idle_sleep=config.idle_sleep,
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = self._popen(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                env=rules.child_environment(self._environ(), kind),
                start_new_session=True,
            )
        except OSError:
            self._fail("binary-invalid")
            return
        self._proc = proc
        self._pump = threading.Thread(
            target=pump_capped, args=(proc.stdout, self.log_path), daemon=True
        )
        self._pump.start()
        self._started_with = StartedWith(
            config.binary, config.model, kind, config.context_window, config.idle_sleep
        )
        self._state, self._reason, self._exit_code = "starting", None, None
        self._hook_exit()
        self._watcher = asyncio.create_task(self._watch(proc, port))
        logger.info("Started the llama.cpp server (port %d).", port)

    def _hook_exit(self) -> None:
        if not self._hooked:
            self._hooked = True
            atexit.register(self.stop_now)

    async def _watch(self, proc: Any, port: int) -> None:
        """Poll ``/health`` until 200, the process exits or the time runs out."""
        deadline = time.monotonic() + self._health_timeout
        url = f"http://127.0.0.1:{port}/health"
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            while proc is self._proc:
                code = proc.poll()
                if code is not None:
                    self._ended(proc, code)
                    return
                if time.monotonic() >= deadline:
                    # Detach and report the timeout before signalling. Our own SIGTERM
                    # kills the child at once, and a status read while we still wait
                    # for it would otherwise read that death as the server exiting.
                    self._proc = None
                    self._fail("timeout")
                    await asyncio.to_thread(self._terminate, proc)
                    return
                with contextlib.suppress(httpx.HTTPError):
                    if (await client.get(url)).status_code == 200:
                        self._state, self._reason = "running", None
                        return
                await asyncio.sleep(self._poll_interval)

    # ── Stop ─────────────────────────────────────────────────────────────

    async def stop(self) -> ServerStatus:
        """Stop the owned process (SIGTERM, then SIGKILL after the grace). Do nothing if none."""
        async with self._lock:
            await self._stop_locked()
            return self.status()

    async def _stop_locked(self) -> None:
        watcher, self._watcher = self._watcher, None
        if watcher is not None and watcher is not asyncio.current_task():
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        proc, self._proc = self._proc, None
        if proc is not None:
            await asyncio.to_thread(self._terminate, proc)
        self._state, self._reason, self._exit_code, self._started_with = "stopped", None, None, None

    async def restart(self, config: LaunchConfig) -> ServerStatus:
        """Stop the owned process, then start it with *config*."""
        async with self._lock:
            await self._stop_locked()
        return await self.start(config)

    async def shutdown(self) -> None:
        """Stop the owned process when ``omrs web`` exits."""
        await self.stop()

    def stop_now(self) -> None:
        """Stop the owned process from a synchronous exit hook."""
        proc, self._proc = self._proc, None
        if proc is not None:
            self._terminate(proc)
            self._state, self._reason, self._started_with = "stopped", None, None

    def _terminate(self, proc: Any) -> None:
        """SIGTERM the process group, wait the grace, then SIGKILL it. Only this *proc*."""
        if proc.poll() is not None:
            return
        self._signal(proc, signal.SIGTERM)
        deadline = time.monotonic() + self._stop_grace
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.02)
        if proc.poll() is None:
            self._signal(proc, getattr(signal, "SIGKILL", signal.SIGTERM))
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.stdout is not None:
            with contextlib.suppress(OSError):
                proc.stdout.close()

    @staticmethod
    def _signal(proc: Any, sig: int) -> None:
        """Send *sig* to the process group that this manager created for *proc*."""
        if proc.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            if os.name == "nt":
                proc.terminate() if sig == signal.SIGTERM else proc.kill()
            elif os.getpgid(proc.pid) == proc.pid:
                os.killpg(proc.pid, sig)  # the child leads its own session, so pgid == pid
            else:
                # The child shares a group (its new session did not take). A group
                # signal would reach omrs's own group, so signal the child alone.
                os.kill(proc.pid, sig)


def owning_lifespan(inner: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Wrap an app lifespan so the owned server stops when ``omrs web`` shuts down.

    The manager is read from ``app.state.llamacpp_server`` at shutdown, so a
    test can replace it. A failure to stop is logged and never raised.
    """

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        try:
            async with inner(app):
                yield
        finally:
            manager = getattr(app.state, "llamacpp_server", None)
            if manager is not None:
                try:
                    await manager.shutdown()
                except Exception:
                    logger.exception("The llama.cpp server could not be stopped cleanly.")

    return lifespan
