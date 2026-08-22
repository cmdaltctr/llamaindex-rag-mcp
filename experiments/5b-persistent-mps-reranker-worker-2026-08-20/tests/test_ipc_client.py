"""Fast tests for ipc_client (OpenSpec task 4.1) — RED until implemented.

Exercises the WorkerSupervisor lifecycle against real ``worker.py --stub``
subprocesses: handshake evidence, request round-trips, deadline fallback with
late-response rejection, worker death plus restart, restart exhaustion,
shutdown reaping, stderr draining, oversized-frame survival and the memory
sampler contract.  No model, no network, no Torch import; every test asserts
a bounded wall time with short deadlines and backoffs.
"""

from __future__ import annotations

import os
import time

import pytest
from _lazy_module import LazyModule

ic = LazyModule("ipc_client")  # RED (ModuleNotFoundError) until implemented

CANDIDATES = [{"doc_id": "a", "text": "first passage"}, {"doc_id": "b", "text": "second passage"}]


def _supervisor(**overrides):
    kwargs = {"device": "cpu", "stub": True}
    kwargs.update(overrides)
    return ic.WorkerSupervisor(**kwargs)


def _wait_until(predicate, bound_s: float = 5.0, interval: float = 0.05) -> None:
    end = time.monotonic() + bound_s
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition not met within the bound")


def _assert_bounded(started: float, bound_s: float, label: str) -> None:
    elapsed = time.monotonic() - started
    assert elapsed < bound_s, f"{label} took {elapsed:.1f}s (bound {bound_s}s)"


# ── start + handshake ─────────────────────────────────────────────────


def test_start_records_handshake_evidence() -> None:
    started = time.monotonic()
    sup = _supervisor()
    try:
        sup.start()
        assert sup.alive()
        assert sup.generation == 0
        assert isinstance(sup.worker_pid, int) and sup.worker_pid > 0
        evidence = sup.ready_evidence
        assert isinstance(evidence, dict)
        assert evidence["model_revision"] == "stub"
        assert evidence["requested_device"] == "cpu"
        assert evidence["pytorch_enable_mps_fallback"] == "0"
    finally:
        sup.shutdown()
    _assert_bounded(started, 15.0, "handshake evidence test")


# ── request round-trip ────────────────────────────────────────────────


def test_request_round_trip_admitted() -> None:
    started = time.monotonic()
    sup = _supervisor()
    try:
        sup.start()
        outcome = sup.request("probe query", CANDIDATES, top_k=2)
        assert outcome.ok is True
        assert outcome.admitted is True
        assert outcome.late is False
        assert outcome.error_code is None
        assert outcome.frame is not None
        assert outcome.frame["request_id"] == 1  # auto increment from 1
        assert outcome.frame["reranked"] is True
        assert outcome.frame["backend"] == "torch"
        assert outcome.latency_ms is not None and outcome.latency_ms >= 0

        second = sup.request("probe query", CANDIDATES, top_k=2)
        assert second.ok and second.frame["request_id"] == 2
    finally:
        sup.shutdown()
    _assert_bounded(started, 15.0, "request round-trip test")


# ── deadline fallback and late-response rejection ─────────────────────


def test_deadline_exceeded_and_late_response_never_admitted() -> None:
    started = time.monotonic()
    sup = _supervisor(stub_behaviour="slow-response", stub_slow_seconds=5.0)
    try:
        sup.start()
        outcome = sup.request("slow query", CANDIDATES, top_k=2, timeout_s=0.5)
        assert outcome.ok is False
        assert outcome.error_code == "deadline_exceeded"
        assert outcome.admitted is False

        # The worker answers ~5 s later; the late frame must be recorded
        # as evidence but never admitted as a result.
        _wait_until(lambda: len(sup.late_responses) > 0, bound_s=8.0)
        assert len(sup.late_responses) >= 1
        assert outcome.admitted is False  # unchanged by the late arrival
    finally:
        sup.shutdown()
    _assert_bounded(started, 25.0, "deadline/late-response test")


# ── worker death and restart ──────────────────────────────────────────


def test_exit_on_request_then_restart_new_generation() -> None:
    started = time.monotonic()
    sup = _supervisor(stub_behaviour="exit-on-request", restart_backoff_s=(0.05,))
    try:
        sup.start()
        first_pid = sup.worker_pid
        outcome = sup.request("doomed query", CANDIDATES, top_k=2, timeout_s=3.0)
        assert outcome.ok is False
        _wait_until(lambda: not sup.alive(), bound_s=3.0)

        sup.restart()
        assert sup.generation == 1
        assert sup.alive()
        assert sup.worker_pid != first_pid
    finally:
        sup.shutdown()
    _assert_bounded(started, 15.0, "exit/restart test")


def test_restart_exhaustion_raises() -> None:
    started = time.monotonic()
    sup = _supervisor(
        stub_behaviour="exit-on-request", max_restarts=2, restart_backoff_s=(0.05, 0.05)
    )
    try:
        sup.start()
        restarts_completed = 0
        while True:
            if sup.alive():
                sup.request("doomed", CANDIDATES, top_k=1, timeout_s=3.0)
                _wait_until(lambda: not sup.alive(), bound_s=3.0)
            try:
                sup.restart()
            except ic.RestartExhaustedError:
                break
            restarts_completed += 1
            assert restarts_completed <= 5, "restart limit never enforced"
        assert restarts_completed == 2  # exactly max_restarts succeeded
    finally:
        sup.shutdown()
    _assert_bounded(started, 20.0, "restart exhaustion test")


# ── shutdown and kill evidence ────────────────────────────────────────


def test_shutdown_reaps_worker() -> None:
    started = time.monotonic()
    sup = _supervisor()
    sup.start()
    sup.request("probe query", CANDIDATES, top_k=2)
    evidence = sup.shutdown()
    assert not sup.alive()
    assert isinstance(evidence, dict)
    assert evidence["reaped"] is True
    assert evidence["exit_status"] is not None
    assert "duration_s" in evidence
    _assert_bounded(started, 15.0, "shutdown test")


def test_kill_reaps_worker() -> None:
    started = time.monotonic()
    sup = _supervisor()
    sup.start()
    evidence = sup.kill()
    assert not sup.alive()
    assert isinstance(evidence, dict)
    assert evidence["reaped"] is True
    _assert_bounded(started, 15.0, "kill test")


# ── stderr draining ───────────────────────────────────────────────────


def test_stderr_drained_and_tail_bounded() -> None:
    started = time.monotonic()
    sup = _supervisor(stub_behaviour="slow-response", stub_slow_seconds=0.2)
    try:
        sup.start()
        assert sup.request("q", CANDIDATES, top_k=2, timeout_s=5.0).ok
        _wait_until(lambda: sup.stderr_total_bytes > 0, bound_s=3.0)
        assert sup.stderr_total_bytes > 0
        assert isinstance(sup.stderr_tail, list)
        assert all(isinstance(line, str) for line in sup.stderr_tail)
        assert len(sup.stderr_tail) < 10_000  # bounded, not unbounded
    finally:
        sup.shutdown()
    _assert_bounded(started, 15.0, "stderr drain test")


# ── oversized response survival ───────────────────────────────────────


def test_oversized_on_request_recorded_not_raised() -> None:
    started = time.monotonic()
    sup = _supervisor(stub_behaviour="oversized-on-request")
    try:
        sup.start()
        outcome = sup.request("q", CANDIDATES, top_k=2)
        assert outcome.ok is False
        assert outcome.admitted is False
        # The supervisor must survive the >8 MiB line and still shut down.
        evidence = sup.shutdown()
        assert evidence["reaped"] is True
    finally:
        sup.shutdown()
    _assert_bounded(started, 20.0, "oversized response test")


# ── memory sampler contract ───────────────────────────────────────────


def test_memory_sampler_positive_and_not_evaluable_paths() -> None:
    started = time.monotonic()
    sup = _supervisor()
    try:
        sup.start()
        sampler = ic.MemorySampler(sup.worker_pid, interval_s=0.5, parent_pid=os.getpid())
        sampler.start()
        try:
            if not sampler.available:
                # psutil cannot sample: the NOT_EVALUABLE contract path.
                assert (
                    sampler.sample_now(
                        cell_id="torch_mps_persistent", block=1, lifetime=1, request_index=1
                    )
                    is None
                )
            else:
                row = sampler.sample_now(
                    cell_id="torch_mps_persistent", block=1, lifetime=1, request_index=1
                )
                assert row is not None
                assert row["worker_rss_bytes"] > 0
                assert row["parent_rss_bytes"] > 0
                assert row["tree_rss_bytes"] >= row["worker_rss_bytes"]
                assert len(sampler.samples) >= 1
        finally:
            sampler.stop()
    finally:
        sup.shutdown()
    _assert_bounded(started, 15.0, "memory sampler test")


def test_memory_sampler_dead_pid_not_evaluable() -> None:
    """A sampler on a non-existent PID must report unavailable, not raise."""
    sampler = ic.MemorySampler(worker_pid=999_999_999)
    sampler.start()
    try:
        assert sampler.available is False
        assert sampler.sample_now(cell_id="c", block=1, lifetime=1, request_index=1) is None
    finally:
        sampler.stop()


def test_memory_sampler_survives_contextless_background_ticks() -> None:
    """A background tick before the first on-demand sample must not retire the sampler.

    Regression for the 2026-08-22 campaign: the runner performs 24 untimed
    warm-up requests before its first ``sample_now`` call, so the >=1 Hz
    background thread fired with an empty ``_last_context`` and incorrectly
    declared the sampler unavailable, silently voiding every memory sample
    (G5/G6 NOT_EVALUABLE).  A context-less tick must be skipped, not treated
    as sampler loss.
    """
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil unavailable; sampler cannot be exercised")
    started = time.monotonic()
    sampler = ic.MemorySampler(os.getpid(), interval_s=0.2, parent_pid=os.getpid())
    sampler.start()
    try:
        assert sampler.available is True
        # Hold the sampler context-less across several background ticks.
        time.sleep(0.7)
        assert sampler.available is True, "context-less tick retired the sampler"
        row = sampler.sample_now(cell_id="c", block=1, lifetime=1, request_index=1)
        assert row is not None, "sample_now failed after context-less ticks"
        time.sleep(0.5)
        assert sampler.available is True
        assert sampler.samples, "no background samples recorded after context established"
    finally:
        sampler.stop()
    _assert_bounded(started, 15.0, "context-less tick regression test")


def test_worker_serves_many_sequential_requests() -> None:
    """Queue depth must not count history: 30 sequential requests all serve.

    Regression: the worker once rejected request 17 because its duplicate
    set was (incorrectly) compared against MAX_QUEUE_DEPTH.
    """
    started = time.monotonic()
    sup = _supervisor()
    try:
        sup.start()
        for expected_id in range(1, 31):
            outcome = sup.request("q", CANDIDATES, top_k=2)
            assert outcome.admitted, f"request {expected_id} rejected"
            assert outcome.frame["request_id"] == expected_id
    finally:
        sup.shutdown()
    _assert_bounded(started, 20.0, "sequential requests test")


def test_start_failure_kills_and_reaps_child() -> None:
    """A worker that dies before hello leaves no live process behind."""
    import shutil

    false_exe = shutil.which("false")
    assert false_exe is not None, "platform lacks a failing executable"
    started = time.monotonic()
    sup = _supervisor(python_exe=false_exe)
    try:
        try:
            sup.start()
            raise AssertionError("handshake against a dying child must fail")
        except RuntimeError:
            pass
        assert not sup.alive()
    finally:
        sup.shutdown()
    _assert_bounded(started, 10.0, "start failure cleanup test")
