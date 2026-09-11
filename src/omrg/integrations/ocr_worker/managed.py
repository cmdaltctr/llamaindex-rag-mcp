"""Owner-scoped lifecycle wrapper for the OCR worker subprocess (task 2.6a).

The wave-1 :class:`OcrWorkerClient` owns the subprocess mechanics —
lazy start, single-flight dispatch, discard-on-failure. This wrapper
adds the OWNER side of design D2.2: a resolved capability fingerprint
that gates dispatch, a spawn-generation counter that makes reuse and
restart observable, and a close state that stops new requests when the
owning engine (or ingest operation) shuts down.

``core/`` receives this collaborator by injection and never imports
subprocess code itself; the composition boundary constructs it via
``omrg.capabilities.build_managed_ocr_client``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from .client import OcrWorkerClient, OcrWorkerError
from .fingerprint import OcrWorkerFingerprint
from .protocol import ParseSuccess

logger = logging.getLogger(__name__)

#: Failure codes that make the subprocess unusable; a structured
#: worker-reported error is deliberately absent — that exchange leaves
#: a healthy process that later requests reuse (design D2.2).
_FATAL_OCR_WORKER_CODES = frozenset(
    {
        "timeout",
        "worker_crashed",
        "worker_closed_output",
        "worker_closed_input",
        "protocol_violation",
        "spawn_failed",
    }
)


class ManagedOcrClient:
    """Owner-scoped OCR worker client: lazy, long-lived, invalidated on failure.

    Construction is cheap and starts nothing. The first :meth:`parse`
    starts one subprocess; healthy subprocesses are reused; a fatal
    failure discards the handle so the NEXT request lazily starts a
    fresh process (the failed request is never replayed — dispatch is
    caller-driven).
    """

    def __init__(
        self,
        *,
        fingerprint: OcrWorkerFingerprint,
        command: list[str],
        request_timeout: float = 300.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_stderr_line: Any = None,
    ) -> None:
        """Hold the resolved fingerprint and worker command; start nothing.

        Args:
            fingerprint: Resolved capability fingerprint (the probe
                result). An unavailable fingerprint makes every
                :meth:`parse` fail before dispatch.
            command: Worker launch command, argv-style.
            request_timeout: Seconds to wait for each terminal response.
            cwd: Working directory for the subprocess, if any.
            env: Extra environment mappings merged over the current
                environment, if any.
            on_stderr_line: Optional callback for drained worker
                diagnostics, forwarded through OMRG logging.
        """
        self.fingerprint = fingerprint
        self._command = list(command)
        self._request_timeout = request_timeout
        self._cwd = cwd
        self._env = env
        self._on_stderr_line = on_stderr_line
        self._client: OcrWorkerClient | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._process_generations = 0

    # ── Observability ───────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Whether the resolved fingerprint reports a compatible worker."""
        return self.fingerprint.available

    @property
    def is_started(self) -> bool:
        """Whether a worker subprocess is currently held."""
        client = self._client
        return client is not None and client.is_started

    @property
    def process_generations(self) -> int:
        """How many distinct subprocesses have been constructed.

        Reuse keeps this at 1; each fatal failure followed by a new
        request increments it. Test observability for the lazy/reuse/
        restart contract — deliberately absent from the fingerprint,
        which carries no transient process detail.
        """
        return self._process_generations

    # ── Dispatch ────────────────────────────────────────────────────

    def parse(self, pdf_path: str) -> ParseSuccess:
        """Dispatch one whole-PDF parse request to the worker.

        Args:
            pdf_path: Path of the PDF the worker must parse.

        Returns:
            The terminal success envelope with structured Markdown.

        Raises:
            RuntimeError: When the owner has closed this client.
            OcrWorkerError: ``worker_unavailable`` before dispatch when
                the fingerprint is unavailable (no process is started);
                otherwise the structured failure from the subprocess
                exchange (timeout, crash, protocol violation, or a
                worker-reported error code).
        """
        if self._closed:
            raise RuntimeError("ManagedOcrClient is closed; construct a new client.")
        if not self.fingerprint.available:
            raise OcrWorkerError(
                "worker_unavailable",
                "the OCR worker fingerprint is unavailable; dispatch refused",
            )
        client = self._ensure_client()
        try:
            return client.parse(pdf_path)
        except OcrWorkerError as exc:
            if exc.code in _FATAL_OCR_WORKER_CODES:
                self._drop_client(client)
            raise

    # ── Owner lifecycle ─────────────────────────────────────────────

    def close(self) -> None:
        """Stop accepting requests and close the subprocess, bounded.

        Mirrors the engine's resource release: stdin closes first so a
        well-behaved worker exits on its own, then a bounded graceful
        wait, then termination (delegated to the underlying client's
        close). Idempotent.
        """
        with self._lock:
            self._closed = True
            client = self._client
            self._client = None
        if client is not None:
            client.close()
            logger.debug("closed managed OCR worker client")

    def __enter__(self) -> ManagedOcrClient:
        """Return self for ``with``-scoped ownership."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the subprocess on scope exit."""
        self.close()

    # ── Internals ───────────────────────────────────────────────────

    def _ensure_client(self) -> OcrWorkerClient:
        """Return the shared underlying client, constructing it lazily."""
        with self._lock:
            if self._closed:
                raise RuntimeError("ManagedOcrClient is closed; construct a new client.")
            if self._client is None:
                self._client = OcrWorkerClient(
                    self._command,
                    cwd=self._cwd,
                    env=self._env,
                    request_timeout=self._request_timeout,
                    on_stderr_line=self._on_stderr_line,
                )
                self._process_generations += 1
            return self._client

    def _drop_client(self, client: OcrWorkerClient) -> None:
        """Discard a fatally failed client; the next parse builds a fresh one."""
        with self._lock:
            if self._client is client:
                self._client = None
        client.close()
