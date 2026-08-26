"""Fast lifecycle tests for the worker.py stub CLI (OpenSpec task 4.1).

Spawns ``worker.py --stub`` subprocesses and exercises the protocol surface
end-to-end over real pipes: handshake evidence, deterministic stub results,
orderly shutdown, EOF, idle expiry, malformed/oversized/wrong-generation/
duplicate frame rejection, stderr flooding under concurrent drain and the
malformed-on-ready probe.  Every test asserts a bounded wall time and never
imports the Torch stack.  No network, no model.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import threading
import time
from pathlib import Path

import protocol_frames as pf

EXP_DIR = Path(__file__).resolve().parents[1]
WORKER_PATH = EXP_DIR / "worker.py"
DEFAULT_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class WorkerSession:
    """Bounded pipe I/O around one stub worker subprocess."""

    def __init__(self, *args: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(WORKER_PATH), "--device", "cpu", "--stub", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(EXP_DIR),
        )
        self._buffer = b""
        self._stderr_chunks: list[bytes] = []
        self._stderr_thread: threading.Thread | None = None

    def read_line(self, deadline_s: float = 5.0) -> bytes:
        """Read one newline-terminated stdout line, failing by deadline."""
        assert self.proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(self.proc.stdout, selectors.EVENT_READ)
        try:
            end = time.monotonic() + deadline_s
            while b"\n" not in self._buffer:
                remaining = end - time.monotonic()
                assert remaining > 0, "timed out waiting for a worker stdout line"
                events = selector.select(timeout=remaining)
                assert events, "timed out waiting for a worker stdout line"
                chunk = os.read(self.proc.stdout.fileno(), 1 << 16)
                assert chunk, "worker stdout closed before a complete line arrived"
                self._buffer += chunk
            line, self._buffer = self._buffer.split(b"\n", 1)
            return line + b"\n"
        finally:
            selector.close()

    def read_frame(self, deadline_s: float = 5.0) -> dict:
        return pf.decode_frame(self.read_line(deadline_s))

    def send_frame(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(pf.encode_frame(payload))
        self.proc.stdin.flush()

    def send_raw(self, raw: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(raw + b"\n")
        self.proc.stdin.flush()

    def start_stderr_drain(self) -> None:
        """Drain stderr concurrently so worker writes never block."""
        assert self.proc.stderr is not None

        def _drain() -> None:
            while True:
                chunk = self.proc.stderr.read(1 << 16)  # type: ignore[union-attr]
                if not chunk:
                    return
                self._stderr_chunks.append(chunk)

        self._stderr_thread = threading.Thread(target=_drain, daemon=True)
        self._stderr_thread.start()

    @property
    def stderr_bytes(self) -> int:
        return sum(len(chunk) for chunk in self._stderr_chunks)

    def handshake(self) -> tuple[dict, dict]:
        hello = self.read_frame()
        ready = self.read_frame()
        return hello, ready

    def request(
        self,
        request_id: int,
        *,
        query: str = "alpha probe query",
        candidates: list[dict] | None = None,
        top_k: int = 2,
        generation: int = 0,
    ) -> None:
        self.send_frame(
            {
                "type": "rerank",
                "request_id": request_id,
                "generation": generation,
                "query": query,
                "candidates": candidates
                or [
                    {"doc_id": "a", "text": "first passage"},
                    {"doc_id": "b", "text": "second passage"},
                ],
                "top_k": top_k,
            }
        )

    def shutdown_and_wait(self, deadline_s: float = 5.0) -> int:
        self.send_frame({"type": "shutdown"})
        return self.wait_exit(deadline_s)

    def wait_exit(self, deadline_s: float = 5.0) -> int:
        try:
            return self.proc.wait(timeout=deadline_s)
        except subprocess.TimeoutExpired as exc:
            self.proc.kill()
            self.proc.wait(timeout=5.0)
            raise AssertionError("worker did not exit within the deadline") from exc

    def close_stdin_and_wait(self, deadline_s: float = 5.0) -> int:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        return self.wait_exit(deadline_s)

    def cleanup(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5.0)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def _assert_bounded(started: float, bound_s: float, label: str) -> None:
    elapsed = time.monotonic() - started
    assert elapsed < bound_s, f"{label} took {elapsed:.1f}s (bound {bound_s}s)"


# ── handshake evidence ────────────────────────────────────────────────


def test_hello_and_ready_evidence_fields() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        hello, ready = worker.handshake()
        assert pf.validate_hello(hello) == []
        assert hello["pid"] == worker.proc.pid

        assert pf.validate_ready(ready) == []
        assert ready["model_id"] == DEFAULT_MODEL_ID
        assert ready["model_revision"] == "stub"
        assert all(len(v) == 64 for v in ready["model_file_sha256"].values())
        assert ready["requested_device"] == "cpu"
        assert ready["effective_device"] == "cpu"
        assert ready["mps_available"] is False
        assert ready["pytorch_enable_mps_fallback"] == "0"
        assert "stub" in ready["stack_versions"]
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "handshake evidence test")


# ── deterministic stub results ────────────────────────────────────────


def test_stub_result_deterministic_same_input() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        worker.request(1)
        first = worker.read_frame()
        worker.request(2)  # identical payload, different request id
        second = worker.read_frame()

        assert pf.validate_result(first) == []
        assert pf.validate_result(second) == []
        assert first["ranking"] == second["ranking"]
        assert first["scores"] == second["scores"]
        assert first["reranked"] is True
        assert first["backend"] == "torch"
        assert first["device"] == "cpu"
        assert first["request_id"] == 1 and second["request_id"] == 2
        assert first["generation"] == 0
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "determinism test")


# ── orderly shutdown / EOF / idle expiry ──────────────────────────────


def test_shutdown_frame_exits_zero() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "shutdown test")


def test_stdin_eof_exits_zero() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        assert worker.close_stdin_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "EOF test")


def test_idle_expiry_exits_zero_within_bound() -> None:
    started = time.monotonic()
    worker = WorkerSession("--idle-seconds", "1")
    try:
        worker.handshake()
        # No further input: the worker must exit cleanly by idle expiry.
        assert worker.wait_exit(deadline_s=4.0) == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 12.0, "idle expiry test")


# ── malformed and bound-violating frames ──────────────────────────────


def test_malformed_input_gets_error_frame_then_recovery() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        worker.send_raw(b"this-is-not-json{")
        error = worker.read_frame()
        assert error["type"] == "error"
        assert error["code"] == "malformed_frame"

        worker.request(1)  # worker must keep serving after the rejection
        result = worker.read_frame()
        assert pf.validate_result(result) == []
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "malformed frame test")


def test_candidate_count_over_bound_rejected() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        candidates = [{"doc_id": f"c{i}", "text": "short passage"} for i in range(201)]
        worker.request(1, candidates=candidates)
        error = worker.read_frame()
        assert error["type"] == "error"
        assert error["code"] == "bound_violation"
        assert "exceeds" in error["detail"]
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "candidate bound test")


def test_token_budget_over_bound_rejected() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        # 16 x 50_000 ascii chars = 800_016 bytes -> ~200_004 estimated
        # tokens, above the 65_536 budget, while the frame stays below 8 MiB.
        candidates = [{"doc_id": f"c{i}", "text": "z" * 50_000} for i in range(16)]
        worker.request(1, candidates=candidates)
        error = worker.read_frame()
        assert error["code"] == "bound_violation"
        assert "token budget" in error["detail"]
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "token budget test")


def test_wrong_generation_rejected() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        worker.request(1, generation=7)  # worker runs generation 0
        error = worker.read_frame()
        assert error["code"] == "wrong_generation"
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "wrong generation test")


def test_duplicate_request_id_rejected() -> None:
    started = time.monotonic()
    worker = WorkerSession()
    try:
        worker.handshake()
        worker.request(5)
        assert pf.validate_result(worker.read_frame()) == []
        worker.request(5)  # same request id again
        error = worker.read_frame()
        assert error["code"] == "duplicate_request"
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "duplicate request test")


# ── stderr pressure and ready-frame corruption probes ─────────────────


def test_stderr_flood_completes_without_deadlock() -> None:
    started = time.monotonic()
    worker = WorkerSession("--stub-behaviour", "stderr-flood", "--stub-stderr-bytes", "131072")
    try:
        worker.handshake()
        worker.start_stderr_drain()  # 128 KiB exceeds the pipe buffer
        worker.request(1)
        result = worker.read_frame(deadline_s=10.0)
        assert pf.validate_result(result) == []
        assert worker.shutdown_and_wait() == 0
        assert worker._stderr_thread is not None
        worker._stderr_thread.join(timeout=5.0)
        assert worker.stderr_bytes >= 131_072
    finally:
        worker.cleanup()
    _assert_bounded(started, 20.0, "stderr flood test")


def test_malformed_on_ready_emits_garbage_then_serves() -> None:
    started = time.monotonic()
    worker = WorkerSession("--stub-behaviour", "malformed-on-ready")
    try:
        worker.handshake()
        garbage = worker.read_line()
        try:
            json.loads(garbage.decode("utf-8"))
            raise AssertionError("third line after ready must be garbage")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        worker.request(1)
        result = worker.read_frame()
        assert pf.validate_result(result) == []
        assert worker.shutdown_and_wait() == 0
    finally:
        worker.cleanup()
    _assert_bounded(started, 15.0, "malformed-on-ready test")
