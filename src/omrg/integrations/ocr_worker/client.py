"""Subprocess client for the isolated OCR worker.

Wave-1 scope (task 2.2): spawn a worker subprocess from an explicit
command, write one JSON Lines request, read the correlated terminal
response with a caller-supplied timeout, drain standard error
independently, and surface every failure as one structured
:class:`OcrWorkerError`. Lifecycle ownership (worker reuse,
invalidation, owner-scoped shutdown policy) lands with task 2.6a; the
class is shaped so an owner can wrap ``start``/``close`` around it.

Standard output is reserved for protocol messages. Standard error is
read on its own thread so a chatty worker can never fill its log pipe
and block, and the captured lines are handed to an optional callback
for forwarding through OMRG logging.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import uuid
from collections import deque
from collections.abc import Callable
from queue import Empty, Queue

from .protocol import (
    ParseFailure,
    ParseSuccess,
    ProtocolError,
    decode_response_line,
    encode_line,
    make_request,
)

logger = logging.getLogger(__name__)

_STDERR_BUFFER_LINES = 1000
_GRACEFUL_EXIT_SECONDS = 5.0
_EXIT_REAP_SECONDS = 2.0


class OcrWorkerError(Exception):
    """Structured client failure with a stable machine-readable code.

    Attributes:
        code: Stable failure code, for example ``timeout``,
            ``worker_crashed``, ``protocol_violation``, or a
            worker-reported error code.
        message: Human-readable description of the failure.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class OcrWorkerClient:
    """Client for one OCR worker subprocess speaking the JSON Lines protocol.

    The constructor takes the worker command explicitly; no settings
    are read and no path is hardcoded. The subprocess starts lazily on
    the first :meth:`parse` call, matching the lazy-worker decision
    (design D2.2). One request may be in flight at a time.
    """

    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        request_timeout: float = 120.0,
        on_stderr_line: Callable[[str], None] | None = None,
    ) -> None:
        """Initialise the client around an explicit worker command.

        Args:
            command: Worker launch command, argv-style. The first
                element must be an executable.
            cwd: Working directory for the subprocess, if any.
            env: Extra environment mappings merged over the current
                environment, if any.
            request_timeout: Default terminal-response timeout.
            on_stderr_line: Optional callback invoked with every
                drained standard-error line, for forwarding through
                OMRG logging. Callback errors are logged and
                swallowed so logging can never break drainage.
        """
        self._command = list(command)
        self._cwd = cwd
        self._env = env
        self.request_timeout = request_timeout
        self._on_stderr_line = on_stderr_line
        self._process: subprocess.Popen[str] | None = None
        self._responses: Queue[tuple[str, str | None]] = Queue()
        self._stderr_lines: deque[str] = deque(maxlen=_STDERR_BUFFER_LINES)
        self._dispatch_lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────

    @property
    def is_started(self) -> bool:
        """Whether a worker subprocess is currently held."""
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start the worker subprocess if it is not already running.

        Raises:
            OcrWorkerError: If the process cannot be spawned.
        """
        if self.is_started:
            return
        try:
            process = subprocess.Popen(  # noqa: S603 - caller-supplied argv, no shell
                self._command,
                cwd=self._cwd,
                env=self._merged_env(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:
            raise OcrWorkerError(
                "spawn_failed", f"could not start worker {self._command[0]!r}: {exc}"
            ) from exc
        self._responses = Queue()
        stdout_reader = threading.Thread(
            target=self._drain_stdout,
            args=(process,),
            name="ocr-worker-stdout",
            daemon=True,
        )
        stderr_reader = threading.Thread(
            target=self._drain_stderr,
            args=(process,),
            name="ocr-worker-stderr",
            daemon=True,
        )
        self._process = process
        stdout_reader.start()
        stderr_reader.start()
        logger.debug("started OCR worker pid=%s", process.pid)

    def close(self) -> None:
        """Close the subprocess: stdin first, then bounded graceful exit.

        Closing standard input lets a well-behaved worker exit on its
        own; a worker that does not exit within the grace period is
        terminated, then killed. The call is idempotent.
        """
        process = self._process
        if process is None:
            return
        self._process = None
        self._close_quietly(process.stdin)
        try:
            process.wait(timeout=_GRACEFUL_EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=_GRACEFUL_EXIT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=_GRACEFUL_EXIT_SECONDS)
        self._close_quietly(process.stdout)
        self._close_quietly(process.stderr)
        logger.debug("closed OCR worker pid=%s", process.pid)

    def __enter__(self) -> OcrWorkerClient:
        """Return self for ``with``-scoped ownership."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the subprocess on scope exit."""
        self.close()

    # ── Requests ───────────────────────────────────────────────────────

    def parse(self, pdf_path: str, *, timeout: float | None = None) -> ParseSuccess:
        """Send one parse request and await its terminal response.

        Starts the worker subprocess lazily on first use. Exactly one
        request may be in flight at a time.

        Args:
            pdf_path: Path of the PDF the worker must parse.
            timeout: Seconds to wait for the terminal response;
                defaults to :attr:`request_timeout`.

        Returns:
            The terminal success envelope.

        Raises:
            OcrWorkerError: On timeout, worker crash, unexpected
                output closure, protocol violation, spawn failure, or
                a worker-reported structured error. A structured
                worker error leaves the subprocess healthy.
        """
        with self._dispatch_lock:
            self.start()
            process = self._process
            if process is None or process.stdin is None:
                raise OcrWorkerError("spawn_failed", "worker process was not started")
            request = make_request(uuid.uuid4().hex, pdf_path)
            try:
                process.stdin.write(encode_line(request) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._discard()
                raise OcrWorkerError(
                    "worker_closed_input", f"worker closed its input: {exc}"
                ) from exc

            effective_timeout = self.request_timeout if timeout is None else timeout
            try:
                kind, payload = self._responses.get(timeout=effective_timeout)
            except Empty:
                self._discard()
                raise OcrWorkerError(
                    "timeout",
                    f"no terminal response within {effective_timeout} seconds",
                ) from None

            if kind == "eof":
                returncode = self._reap_exit_code(process)
                self._discard()
                if returncode not in (0, None):
                    raise OcrWorkerError(
                        "worker_crashed",
                        f"worker exited with code {returncode} before responding",
                    )
                raise OcrWorkerError(
                    "worker_closed_output",
                    "worker closed standard output before responding",
                )

            if payload is None:
                self._discard()
                raise OcrWorkerError("protocol_violation", "empty response payload")
            try:
                response = decode_response_line(payload, expected_id=request.id)
            except ProtocolError as exc:
                self._discard()
                raise OcrWorkerError("protocol_violation", f"{exc.code}: {exc.message}") from exc
            if isinstance(response, ParseFailure):
                # A structured worker error is a healthy protocol
                # exchange; the subprocess stays usable (design D2.2).
                raise OcrWorkerError(response.error.code, response.error.message)
            return response

    def drained_stderr(self) -> list[str]:
        """Return the drained standard-error lines, oldest first.

        The buffer is bounded; only the most recent lines are kept.
        """
        return list(self._stderr_lines)

    # ── Internals ──────────────────────────────────────────────────────

    def _drain_stdout(self, process: subprocess.Popen[str]) -> None:
        """Forward standard-output lines to the response queue."""
        stdout = process.stdout
        if stdout is None:
            self._responses.put(("eof", None))
            return
        for line in stdout:
            self._responses.put(("line", line))
        self._responses.put(("eof", None))

    def _drain_stderr(self, process: subprocess.Popen[str]) -> None:
        """Drain standard error on its own thread, independent of stdout."""
        stderr = process.stderr
        if stderr is None:
            return
        for line in stderr:
            text = line.rstrip("\n")
            self._stderr_lines.append(text)
            callback = self._on_stderr_line
            if callback is not None:
                try:
                    callback(text)
                except Exception:  # noqa: BLE001 - logging must never break drainage
                    logger.debug("stderr callback raised; ignoring", exc_info=True)

    def _discard(self) -> None:
        """Tear the worker down after a failure; a later wave owns restart policy."""
        process = self._process
        if process is None:
            return
        self._process = None
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=_GRACEFUL_EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning("OCR worker pid=%s did not exit after kill", process.pid)
        self._close_quietly(process.stdin)
        self._close_quietly(process.stdout)
        self._close_quietly(process.stderr)

    def _reap_exit_code(self, process: subprocess.Popen[str]) -> int | None:
        """Return the exit code, waiting briefly; ``None`` if still running.

        Standard output can close just before the process finishes, so
        a single ``poll`` races the exit. A bounded wait makes the
        crash classification deterministic.
        """
        try:
            return process.wait(timeout=_EXIT_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            return None

    def _merged_env(self) -> dict[str, str] | None:
        """Merge the extra environment over a copy of the current one."""
        if self._env is None:
            return None
        merged = dict(os.environ)
        merged.update(self._env)
        return merged

    @staticmethod
    def _close_quietly(stream: object) -> None:
        """Close a pipe stream, ignoring closed-stream errors."""
        if stream is None:
            return
        try:
            stream.close()  # type: ignore[attr-defined]
        except OSError:
            pass
