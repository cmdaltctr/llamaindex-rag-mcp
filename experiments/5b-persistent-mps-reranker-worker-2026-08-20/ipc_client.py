"""Parent-side worker supervisor for Experiment 5b (protocol section 11/12).

Owns the worker child process lifecycle: spawn with unrelated descriptors
closed, validate the ``hello``/``ready`` handshake evidence, drain stderr
concurrently, correlate request IDs under monotonic deadlines, reject late
responses, bound TERM-then-KILL shutdown with reaping, restart with capped
backoff and a new generation, and sample current RSS (D5) at >=1 Hz and on
demand.

The parent stays Torch-free: this module imports only stdlib, psutil and
the experiment's own ``protocol_frames``/``artefacts`` modules.
"""

from __future__ import annotations

import os
import selectors
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import artefacts
import protocol_frames as pf

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_PATH = SCRIPT_DIR / "worker.py"
DEFAULT_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"

DRAIN_DEADLINE_S = 2.0  # section 12: drain 2 s
TERM_GRACE_S = 5.0  # section 12: TERM grace 5 s
KILL_GRACE_S = 5.0  # section 12: KILL grace 5 s
STDERR_TAIL_LINES = 512
LATE_KEEP_WINDOW_S = 30.0  # how long a dead deadline stays classifiable


@dataclass
class RequestOutcome:
    """One parent-observed request result with route-admission evidence."""

    ok: bool
    frame: dict[str, Any] | None = None
    latency_ms: float | None = None
    error_code: str | None = None
    detail: str = ""
    late: bool = False

    @property
    def admitted(self) -> bool:
        """True only for timely, validated, reranked responses (design D2)."""
        return self.ok and not self.late


class RestartExhaustedError(RuntimeError):
    """Raised when ``restart()`` exceeds the registered maximum attempts."""


class _ReaderState:
    """Shared state between the request path and the stdout reader thread."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.completed: dict[int, dict[str, Any]] = {}
        self.deadline_by_rid: dict[int, float] = {}
        self.late_responses: list[dict[str, Any]] = []
        self.error_events: deque[dict[str, Any]] = deque(maxlen=64)
        self.violation: str | None = None  # oversized-frame / protocol breach
        self.eof = False


class WorkerSupervisor:
    """Supervise one persistent worker child over the versioned protocol."""

    def __init__(
        self,
        *,
        device: str,
        model_id: str = DEFAULT_MODEL_ID,
        generation: int = 0,
        stub: bool = False,
        stub_behaviour: str | None = None,
        stub_slow_seconds: float = 5.0,
        stub_stderr_bytes: int = pf.STDERR_PRESSURE_BYTES,
        request_deadline_s: float = 5.0,
        idle_seconds: float = 60.0,
        handshake_timeout_s: float = 300.0,
        restart_backoff_s: tuple[float, ...] = (1.0, 2.0, 4.0),
        max_restarts: int = 3,
        env_extra: dict[str, str] | None = None,
        python_exe: str | None = None,
    ) -> None:
        if device not in ("cpu", "mps"):
            raise ValueError(f"device must be cpu|mps, got {device!r}")
        self.device = device
        self.model_id = model_id
        self.generation = generation
        self.stub = stub
        self.stub_behaviour = stub_behaviour
        self.stub_slow_seconds = stub_slow_seconds
        self.stub_stderr_bytes = stub_stderr_bytes
        self.request_deadline_s = request_deadline_s
        self.idle_seconds = idle_seconds
        self.handshake_timeout_s = handshake_timeout_s
        self.restart_backoff_s = tuple(restart_backoff_s)
        self.max_restarts = max_restarts
        self.env_extra = dict(env_extra or {})
        self.python_exe = python_exe
        self.ready_evidence: dict[str, Any] = {}
        self.late_responses: list[dict[str, Any]] = []
        self._proc: subprocess.Popen[bytes] | None = None
        self._reader: _ReaderState | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._stderr_total = 0
        self._request_counter = 0
        self._restarts_done = 0

    # ── process plumbing ───────────────────────────────────────────────

    def _argv(self) -> list[str]:
        argv = [
            self.python_exe or sys.executable,
            str(WORKER_PATH),
            "--device",
            self.device,
            "--generation",
            str(self.generation),
            "--idle-seconds",
            str(self.idle_seconds),
        ]
        if self.stub:
            argv.append("--stub")
        if self.stub_behaviour:
            argv.extend(
                [
                    "--stub-behaviour",
                    self.stub_behaviour,
                    "--stub-slow-seconds",
                    str(self.stub_slow_seconds),
                    "--stub-stderr-bytes",
                    str(self.stub_stderr_bytes),
                ]
            )
        return argv

    def _spawn(self) -> None:
        env = {
            **os.environ,
            "PYTORCH_ENABLE_MPS_FALLBACK": "0",
            "HF_HUB_OFFLINE": "1",
            **self.env_extra,
        }
        self._proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            self._argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(SCRIPT_DIR),
            close_fds=True,
        )

    def _drain_stderr_forever(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        fd = self._proc.stderr.fileno()
        while True:
            try:
                chunk = os.read(fd, 1 << 16)
            except OSError:
                return
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr_total += len(chunk)
                self._stderr_tail.extend(
                    line.decode("utf-8", errors="replace") for line in chunk.splitlines()[-8:]
                )

    _stderr_lock = threading.Lock()

    @property
    def stderr_tail(self) -> list[str]:
        """Bounded recent stderr lines (diagnostics evidence)."""
        with self._stderr_lock:
            return list(self._stderr_tail)

    @property
    def stderr_total_bytes(self) -> int:
        """Total stderr bytes drained (flooding evidence)."""
        with self._stderr_lock:
            return self._stderr_total

    # ── frame reading ──────────────────────────────────────────────────

    def _read_line(
        self,
        stdout: Any,
        timeout_s: float,
    ) -> tuple[bytes | None, bool]:
        """Read one line; return ``(line, oversized)``.

        ``line`` is ``None`` on EOF or timeout.  Oversized lines are consumed
        up to their newline and reported without their payload.
        """
        selector = selectors.DefaultSelector()
        selector.register(stdout, selectors.EVENT_READ)
        buffer = b""
        oversized = False
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, oversized
                events = selector.select(timeout=remaining)
                if not events:
                    return None, oversized
                chunk = os.read(stdout.fileno(), 1 << 16)
                if not chunk:
                    return None, oversized
                buffer += chunk
                if len(buffer) > pf.MAX_FRAME_BYTES:
                    oversized = True
                    keep = buffer[-1:]
                    buffer = keep
                if b"\n" in buffer:
                    line, _, rest = buffer.partition(b"\n")
                    # Preserve unread bytes?  Pipe reads are line-atomic enough
                    # for this protocol; extra bytes belong to the next read.
                    if rest:
                        self._readahead = rest
                    return line, oversized
        finally:
            selector.close()

    _readahead: bytes = b""

    def _read_frame_blocking(self, timeout_s: float) -> dict[str, Any] | None:
        """Handshake-phase frame read (before the reader thread starts)."""
        stdout = self._proc.stdout if self._proc else None
        if stdout is None:
            return None
        if self._readahead:
            line, _, self._readahead = self._readahead.partition(b"\n")
            if line:
                return self._decode(line)
        raw, _oversized = self._read_line(stdout, timeout_s)
        if raw is None:
            return None
        return self._decode(raw)

    @staticmethod
    def _decode(line: bytes) -> dict[str, Any]:
        frame = pf.decode_frame(line)
        return frame

    # ── handshake ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the worker and validate the hello/ready evidence."""
        self._readahead = b""
        self._spawn()
        if self._proc is None:  # pragma: no cover — Popen raises on failure
            raise RuntimeError("worker spawn failed")
        self._stderr_thread = threading.Thread(target=self._drain_stderr_forever, daemon=True)
        self._stderr_thread.start()

        hello = self._read_frame_blocking(self.handshake_timeout_s)
        if hello is None:
            raise RuntimeError("worker handshake timed out before hello")
        hello_errors = pf.validate_hello(hello)
        if hello_errors:
            raise RuntimeError(f"invalid hello frame: {'; '.join(hello_errors)}")
        ready = self._read_frame_blocking(self.handshake_timeout_s)
        if ready is None:
            raise RuntimeError("worker handshake timed out before ready")
        ready_errors = pf.validate_ready(ready)
        if ready_errors:
            raise RuntimeError(f"invalid ready frame: {'; '.join(ready_errors)}")
        self.ready_evidence = ready

        self._reader = _ReaderState()
        self.late_responses = self._reader.late_responses
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    @property
    def worker_pid(self) -> int:
        """PID of the supervised worker (raises before start)."""
        if self._proc is None:
            raise RuntimeError("worker not started")
        return self._proc.pid

    def alive(self) -> bool:
        """True while the worker process has not exited."""
        return self._proc is not None and self._proc.poll() is None

    # ── reader thread ──────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        state = self._reader
        if state is None or self._proc is None or self._proc.stdout is None:
            return
        stdout = self._proc.stdout
        selector = selectors.DefaultSelector()
        selector.register(stdout, selectors.EVENT_READ)
        buffer = self._readahead  # bytes left over from the handshake reads
        self._readahead = b""
        try:
            while True:
                events = selector.select(timeout=0.25)
                if events:
                    chunk = os.read(stdout.fileno(), 1 << 16)
                    if not chunk:
                        with state.changed:
                            state.eof = True
                            state.changed.notify_all()
                        return
                    buffer += chunk
                    if len(buffer) > pf.MAX_FRAME_BYTES:
                        buffer = b""
                        with state.changed:
                            state.violation = "oversized_frame"
                            state.changed.notify_all()
                        continue
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    try:
                        frame = pf.decode_frame(line)
                    except pf.FrameError:
                        continue  # malformed child output: evidence in stderr
                    self._route_frame(frame)
        finally:
            selector.close()

    def _route_frame(self, frame: dict[str, Any]) -> None:
        state = self._reader
        if state is None:
            return
        if frame.get("type") == "error":
            with state.changed:
                state.error_events.append(frame)
                state.changed.notify_all()
            return
        if frame.get("type") != "result":
            return
        rid = frame.get("request_id")
        if not isinstance(rid, int):
            return
        with state.changed:
            deadline = state.deadline_by_rid.get(rid)
            if deadline is not None and time.monotonic() > deadline:
                state.late_responses.append(frame)
                state.deadline_by_rid.pop(rid, None)
            else:
                state.completed[rid] = frame
            state.changed.notify_all()

    # ── requests ───────────────────────────────────────────────────────

    def request(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
        timeout_s: float | None = None,
    ) -> RequestOutcome:
        """Send one rerank frame and observe the validated response."""
        state = self._reader
        if state is None or self._proc is None or self._proc.stdin is None:
            return RequestOutcome(False, error_code="not_started", detail="worker not started")
        deadline_s = timeout_s if timeout_s is not None else self.request_deadline_s
        self._request_counter += 1
        rid = self._request_counter
        frame = {
            "type": "rerank",
            "request_id": rid,
            "generation": self.generation,
            "query": query,
            "candidates": candidates,
            "top_k": top_k,
        }
        errors = pf.validate_rerank(frame)
        if errors:
            return RequestOutcome(False, error_code="invalid_request", detail="; ".join(errors))
        now = time.monotonic()
        with state.changed:
            # Prune deadlines that can no longer produce a classifiable late
            # frame; enforce the queue-depth bound on live entries only.
            stale = [
                key
                for key, expiry in state.deadline_by_rid.items()
                if expiry < now - LATE_KEEP_WINDOW_S
            ]
            for key in stale:
                state.deadline_by_rid.pop(key, None)
            live = sum(1 for expiry in state.deadline_by_rid.values() if expiry >= now)
            if live >= pf.MAX_QUEUE_DEPTH:
                return RequestOutcome(False, error_code="queue_depth", detail="bound exceeded")
            state.deadline_by_rid[rid] = now + deadline_s
        started = time.perf_counter()
        try:
            self._proc.stdin.write(pf.encode_frame(frame))
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            with state.changed:
                state.deadline_by_rid.pop(rid, None)
            return RequestOutcome(False, error_code="worker_exit", detail=str(exc))
        deadline = time.monotonic() + deadline_s
        with state.changed:
            while True:
                if rid in state.completed:
                    response = state.completed.pop(rid)
                    state.deadline_by_rid.pop(rid, None)
                    return self._validate_response(response, started, deadline)
                if state.violation is not None:
                    violation = state.violation
                    state.deadline_by_rid.pop(rid, None)
                    return RequestOutcome(
                        False, error_code=violation, detail="protocol violation from worker"
                    )
                for index, error_frame in enumerate(state.error_events):
                    if error_frame.get("request_id") in (rid, None):
                        del state.error_events[index]
                        state.deadline_by_rid.pop(rid, None)
                        return RequestOutcome(
                            False,
                            error_code=str(error_frame.get("code", "worker_error")),
                            detail=str(error_frame.get("detail", "")),
                        )
                if state.eof:
                    state.deadline_by_rid.pop(rid, None)
                    return RequestOutcome(
                        False, error_code="worker_exit", detail="stdout closed before response"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # Keep the deadline registered so the eventual frame is
                    # classified as late evidence and never admitted.
                    return RequestOutcome(
                        False,
                        error_code="deadline_exceeded",
                        detail=f"no response within {deadline_s}s",
                    )
                state.changed.wait(timeout=remaining)

    def _validate_response(
        self,
        frame: dict[str, Any],
        started: float,
        deadline: float,
    ) -> RequestOutcome:
        errors = pf.validate_result(frame)
        if errors:
            return RequestOutcome(False, error_code="invalid_result", detail="; ".join(errors))
        checks = self._route_checks(frame)
        late = time.monotonic() > deadline
        outcome_ok = not checks and not late
        latency_ms = (time.perf_counter() - started) * 1000.0
        return RequestOutcome(
            ok=outcome_ok,
            frame=frame,
            latency_ms=latency_ms if outcome_ok else latency_ms,
            error_code=checks or None,
            detail="route admission failed" if checks else "",
            late=late,
        )

    def _route_checks(self, frame: dict[str, Any]) -> str | None:
        """Per-response route admission (design D2); None means admitted."""
        if frame.get("backend") != "torch":
            return f"wrong_backend:{frame.get('backend')!r}"
        device = str(frame.get("device", ""))
        if not device.startswith(self.device):
            return f"wrong_device:{device!r}"
        if frame.get("reranked") is not True:
            return "not_reranked"
        expected = frame.get("expected_cardinality")
        if isinstance(expected, int) and frame.get("cardinality") != expected:
            return "wrong_cardinality"
        if frame.get("model_id") != self.model_id:
            return "wrong_model"
        return None

    # ── lifecycle ──────────────────────────────────────────────────────

    def _stop_threads(self) -> None:
        state = self._reader
        if state is not None:
            with state.changed:
                state.eof = True
                state.changed.notify_all()

    def shutdown(self) -> dict[str, Any]:
        """Orderly bounded shutdown: frame, drain, close, TERM-then-KILL."""
        started = time.monotonic()
        term_used = False
        kill_used = False
        if self._proc is None:
            return {
                "exit_status": None,
                "term_used": False,
                "kill_used": False,
                "reaped": False,
                "duration_s": 0.0,
            }
        if self.alive() and self._proc.stdin is not None:
            try:
                self._proc.stdin.write(pf.encode_frame({"type": "shutdown"}))
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        try:
            self._proc.wait(timeout=DRAIN_DEADLINE_S)
        except subprocess.TimeoutExpired:
            pass
        if self._proc.stdin is not None:
            try:
                self._proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        if self.alive():
            self._proc.terminate()
            term_used = True
            try:
                self._proc.wait(timeout=TERM_GRACE_S)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                kill_used = True
                try:
                    self._proc.wait(timeout=KILL_GRACE_S)
                except subprocess.TimeoutExpired:
                    pass
        reaped = self._proc.poll() is not None
        self._stop_threads()
        return {
            "exit_status": self._proc.returncode,
            "term_used": term_used,
            "kill_used": kill_used,
            "reaped": reaped,
            "duration_s": time.monotonic() - started,
        }

    def kill(self) -> dict[str, Any]:
        """Immediate SIGKILL with bounded wait and reaping."""
        started = time.monotonic()
        if self._proc is None:
            return {
                "exit_status": None,
                "term_used": False,
                "kill_used": False,
                "reaped": False,
                "duration_s": 0.0,
            }
        self._proc.kill()
        try:
            self._proc.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            pass
        reaped = self._proc.poll() is not None
        self._stop_threads()
        return {
            "exit_status": self._proc.returncode,
            "term_used": False,
            "kill_used": True,
            "reaped": reaped,
            "duration_s": time.monotonic() - started,
        }

    def restart(self) -> None:
        """Restart the worker: new generation, registered backoff, capped."""
        if self._restarts_done >= self.max_restarts:
            raise RestartExhaustedError(f"exceeded maximum restart attempts ({self.max_restarts})")
        if self.alive():
            self.kill()
        backoff = self.restart_backoff_s[min(self._restarts_done, len(self.restart_backoff_s) - 1)]
        time.sleep(backoff)
        self._restarts_done += 1
        self.generation += 1
        self.start()


class MemorySampler:
    """Current-RSS sampler (design D5): >=1 Hz background plus on-demand.

    Tree RSS covers the fallback-ready parent, the worker and every worker
    descendant.  When sampling is unavailable the sampler reports
    ``available=False`` and ``sample_now`` returns None so gates become
    NOT_EVALUABLE instead of substituting peak RSS.
    """

    def __init__(
        self,
        worker_pid: int,
        *,
        interval_s: float = 1.0,
        parent_pid: int | None = None,
    ) -> None:
        self.worker_pid = worker_pid
        self.parent_pid = parent_pid if parent_pid is not None else os.getpid()
        self.interval_s = interval_s
        self.available = False
        self.samples: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._psutil: Any = None
        self._last_request_index = 0
        self._last_context: dict[str, Any] = {}

    def _resolve_processes(self) -> bool:
        try:
            import psutil
        except ImportError:
            return False
        self._psutil = psutil
        try:
            self._worker = psutil.Process(self.worker_pid)
            self._parent = psutil.Process(self.parent_pid)
            self._worker.memory_info()
            self._parent.memory_info()
        except Exception:  # noqa: BLE001 — psutil.Error family
            return False
        return True

    def start(self) -> None:
        """Probe capability, then run the >=1 Hz background cadence."""
        self.available = self._resolve_processes()
        if not self.available:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            row = self._sample(**self._last_context) if self._last_context else None
            if row is not None:
                with self._lock:
                    self.samples.append(row)
            else:
                self.available = False
                return

    def _tree_rss(self) -> int:
        if self._psutil is None:
            return 0
        total = 0
        processes = [self._parent, self._worker]
        try:
            processes.extend(self._worker.children(recursive=True))
        except Exception:  # noqa: BLE001, S110 — raced worker exit is expected
            pass
        for process in processes:
            try:
                total += int(process.memory_info().rss)
            except Exception:  # noqa: BLE001, S112 — raced exit skips one process
                continue
        return total

    def _sample(
        self,
        *,
        cell_id: str,
        block: int,
        lifetime: int,
        request_index: int,
        mps_current_allocated_bytes: int | None = None,
        mps_driver_allocated_bytes: int | None = None,
    ) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            return artefacts.build_memory_sample(
                cell_id=cell_id,
                block=block,
                lifetime=lifetime,
                request_index=request_index,
                worker_rss_bytes=self._worker.memory_info().rss,
                parent_rss_bytes=self._parent.memory_info().rss,
                tree_rss_bytes=self._tree_rss(),
                mps_current_allocated_bytes=mps_current_allocated_bytes,
                mps_driver_allocated_bytes=mps_driver_allocated_bytes,
            )
        except Exception:  # noqa: BLE001 — sampler loss means NOT_EVALUABLE
            self.available = False
            return None

    def sample_now(
        self,
        *,
        cell_id: str,
        block: int,
        lifetime: int,
        request_index: int,
        mps_current_allocated_bytes: int | None = None,
        mps_driver_allocated_bytes: int | None = None,
    ) -> dict[str, Any] | None:
        """Take one on-demand sample at a known request boundary."""
        context = {
            "cell_id": cell_id,
            "block": block,
            "lifetime": lifetime,
            "request_index": request_index,
        }
        self._last_context = context
        self._last_request_index = request_index
        row = self._sample(
            mps_current_allocated_bytes=mps_current_allocated_bytes,
            mps_driver_allocated_bytes=mps_driver_allocated_bytes,
            **context,
        )
        if row is not None:
            with self._lock:
                self.samples.append(row)
        return row

    def stop(self) -> None:
        """Stop the background cadence."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s + 1.0)
            self._thread = None
