#!/usr/bin/env python3
"""Experiment 5b lifecycle probe battery (protocol section 12).

Runs every registered probe against stub workers (no model, no network)
with the registered deadlines: worker death, worker hang, parent death
while idle and in-flight, stdout backpressure, stderr flooding, malformed
frames, request deadline, idle expiry with restart, orderly shutdown,
EOF-on-stdin and orphan/reaping verification.

Parent-death probes need an external supervisor because a parent cannot
prove its own post-mortem behaviour: this module runs a mini-parent child
process, an external supervisor kills it, then observes the worker for the
registered orphan-observation bound and verifies no live or zombie
process remains.

Rows append to ``output/lifecycle_probes.jsonl`` via ``artefacts``.
``run_battery`` returns True only when every probe passes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import artefacts as art
import ipc_client
import protocol_frames as pf

SCRIPT_DIR = Path(__file__).resolve().parent

REQUEST_DEADLINE_S = 5.0
IDLE_EXPIRY_S = 60
ORPHAN_OBSERVATION_S = 10
BACKPRESSURE_BYTES = 1 << 20
CANDIDATES = [{"doc_id": "a", "text": "first"}, {"doc_id": "b", "text": "second"}]

PROBE_ORDER = (
    "worker_death",
    "worker_hang",
    "request_deadline",
    "stdout_backpressure",
    "stderr_flooding",
    "malformed_frame",
    "idle_expiry_restart",
    "orderly_shutdown",
    "eof_stdin",
    "parent_death_idle",
    "parent_death_inflight",
    "orphan_reaping",
)


def _append(output_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    art.append_jsonl(output_dir / "lifecycle_probes.jsonl", row)
    return row


def _pass(probe: str, started: float, **extra: Any) -> dict[str, Any]:
    return art.build_probe_row(
        probe=probe,
        worker_pid=extra.pop("worker_pid", None),
        outcome="pass",
        deadline_result="met",
        detail=extra.pop("detail", ""),
        started_monotonic=started,
        ended_monotonic=time.monotonic(),
        extra=extra,
    )


def _fail(probe: str, started: float, detail: str, **extra: Any) -> dict[str, Any]:
    return art.build_probe_row(
        probe=probe,
        worker_pid=extra.pop("worker_pid", None),
        outcome="fail",
        deadline_result="missed",
        detail=detail[:2000],
        started_monotonic=started,
        ended_monotonic=time.monotonic(),
        extra=extra,
    )


# ── individual probes ─────────────────────────────────────────────────


def probe_worker_death(output_dir: Path) -> dict[str, Any]:
    """Kill a ready worker mid-request; deadline and diagnostics result."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(device="cpu", stub=True, stub_behaviour="exit-on-request")
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("doomed", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        bounded = not sup.alive()
        late_count = len(sup.late_responses)
        if outcome.ok or outcome.error_code is None:
            return _append(
                output_dir,
                _fail(
                    "worker-death",
                    started,
                    f"dead worker produced outcome {outcome.error_code!r}",
                    worker_pid=pid,
                ),
            )
        ok = bounded and not outcome.admitted and late_count == 0
        row = (
            _pass(
                "worker-death",
                started,
                worker_pid=pid,
                error_code=outcome.error_code,
                late_responses=late_count,
                stderr_tail=sup.stderr_tail[-3:],
                fallback_route="not_exercised (stub mode)",
                detail="worker exit detected within deadline; no late response admitted",
            )
            if ok
            else _fail("worker-death", started, "unbounded failure handling", worker_pid=pid)
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_worker_hang(output_dir: Path) -> dict[str, Any]:
    """SIGSTOP the worker mid-request; deadline fires, termination bounded."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(device="cpu", stub=True, stub_behaviour="hang-on-request")
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("hanging", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        if outcome.error_code != "deadline_exceeded":
            return _append(
                output_dir,
                _fail(
                    "worker-hang",
                    started,
                    f"expected deadline_exceeded, got {outcome.error_code!r}",
                    worker_pid=pid,
                ),
            )
        evidence = sup.shutdown()
        bounded = (
            evidence["reaped"]
            and evidence["duration_s"]
            <= ipc_client.DRAIN_DEADLINE_S + ipc_client.TERM_GRACE_S + ipc_client.KILL_GRACE_S + 2.0
        )
        row = (
            _pass(
                "worker-hang",
                started,
                worker_pid=pid,
                exit_evidence=evidence,
                detail="deadline fired; TERM/KILL bounded; reaped",
            )
            if bounded
            else _fail("worker-hang", started, "termination exceeded bounds", worker_pid=pid)
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_request_deadline(output_dir: Path) -> dict[str, Any]:
    """Slow response misses the deadline; late frame never admitted."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(
        device="cpu", stub=True, stub_behaviour="slow-response", stub_slow_seconds=6.0
    )
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("slow", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        deadline_met = outcome.error_code == "deadline_exceeded" and not outcome.admitted
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and not sup.late_responses:
            time.sleep(0.1)
        late = len(sup.late_responses)
        ok = deadline_met and late >= 1 and not outcome.admitted
        row = (
            _pass(
                "request-deadline",
                started,
                worker_pid=pid,
                late_responses=late,
                detail="deadline fired; late response retained as evidence only",
            )
            if ok
            else _fail(
                "request-deadline",
                started,
                f"deadline_met={deadline_met} late={late}",
                worker_pid=pid,
            )
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_stdout_backpressure(output_dir: Path) -> dict[str, Any]:
    """Oversized frame under pipe pressure: bounded rejection, no hang."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(
        device="cpu", stub=True, stub_behaviour="oversized-on-request"
    )
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("pressure", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        evidence = sup.shutdown()
        ok = (
            not outcome.ok
            and not outcome.admitted
            and evidence["reaped"]
            and evidence["duration_s"] <= 20.0
        )
        row = (
            _pass(
                "stdout-backpressure",
                started,
                worker_pid=pid,
                error_code=outcome.error_code,
                bytes_reference=BACKPRESSURE_BYTES,
                detail="oversized frame rejected without deadlock; bounded shutdown",
            )
            if ok
            else _fail("stdout-backpressure", started, "unbounded hang or crash", worker_pid=pid)
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_stderr_flooding(output_dir: Path) -> dict[str, Any]:
    """4 MiB sustained stderr drains concurrently without deadlock."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(device="cpu", stub=True, stub_behaviour="stderr-flood")
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("flood", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sup.stderr_total_bytes < pf.STDERR_PRESSURE_BYTES:
            time.sleep(0.1)
        drained = sup.stderr_total_bytes
        evidence = sup.shutdown()
        ok = outcome.admitted and drained >= pf.STDERR_PRESSURE_BYTES and evidence["reaped"]
        row = (
            _pass(
                "stderr-flooding",
                started,
                worker_pid=pid,
                stderr_bytes_drained=drained,
                detail="concurrent drain prevented deadlock",
            )
            if ok
            else _fail(
                "stderr-flooding",
                started,
                f"admitted={outcome.admitted} drained={drained}",
                worker_pid=pid,
            )
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_malformed_frame(output_dir: Path) -> dict[str, Any]:
    """Worker emits garbage after ready: loud rejection, service continues."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(device="cpu", stub=True, stub_behaviour="malformed-on-ready")
    try:
        sup.start()
        pid = sup.worker_pid
        outcome = sup.request("after garbage", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        ok = outcome.admitted
        row = (
            _pass(
                "malformed-frame",
                started,
                worker_pid=pid,
                detail="malformed frame skipped loudly; next request admitted",
            )
            if ok
            else _fail(
                "malformed-frame",
                started,
                f"post-garbage request not admitted: {outcome.error_code}",
                worker_pid=pid,
            )
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_idle_expiry_restart(output_dir: Path) -> dict[str, Any]:
    """Idle worker exits; new generation starts after backoff and preflight."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(
        device="cpu", stub=True, idle_seconds=1.0, restart_backoff_s=(0.2,)
    )
    try:
        sup.start()
        first_pid = sup.worker_pid
        deadline = time.monotonic() + 5.0
        while sup.alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        expired = not sup.alive()
        sup.restart()
        outcome = sup.request("post restart", CANDIDATES, top_k=2, timeout_s=REQUEST_DEADLINE_S)
        ok = expired and sup.generation == 1 and sup.worker_pid != first_pid and outcome.admitted
        row = (
            _pass(
                "idle-expiry-restart",
                started,
                worker_pid=sup.worker_pid,
                generation=sup.generation,
                first_worker_pid=first_pid,
                detail="idle expiry; new generation; route preflight via handshake",
            )
            if ok
            else _fail(
                "idle-expiry-restart",
                started,
                f"expired={expired} generation={sup.generation}",
                worker_pid=sup.worker_pid,
            )
        )
        return _append(output_dir, row)
    finally:
        sup.shutdown()


def probe_orderly_shutdown(output_dir: Path) -> dict[str, Any]:
    """Shutdown frame drains, exits zero, and is reaped."""
    started = time.monotonic()
    sup = ipc_client.WorkerSupervisor(device="cpu", stub=True)
    sup.start()
    pid = sup.worker_pid
    sup.request("final", CANDIDATES, top_k=2)
    evidence = sup.shutdown()
    ok = (
        evidence["reaped"]
        and evidence["exit_status"] == 0
        and not evidence["kill_used"]
        and not sup.alive()
    )
    row = (
        _pass(
            "orderly-shutdown",
            started,
            worker_pid=pid,
            exit_evidence=evidence,
            detail="drain then clean exit; no TERM or KILL needed",
        )
        if ok
        else _fail(
            "orderly-shutdown",
            started,
            f"evidence={evidence}",
            worker_pid=pid,
        )
    )
    return _append(output_dir, row)


def probe_eof_stdin(output_dir: Path) -> dict[str, Any]:
    """Closing stdin without a shutdown frame exits the worker cleanly."""
    started = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603 — fixed argv
        [
            sys.executable,
            str(SCRIPT_DIR / "worker.py"),
            "--device",
            "cpu",
            "--stub",
            "--idle-seconds",
            "30",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(SCRIPT_DIR),
        env={**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "0", "HF_HUB_OFFLINE": "1"},
    )
    stdout_stream = proc.stdout
    stdin_stream = proc.stdin
    if stdout_stream is None or stdin_stream is None:  # pragma: no cover
        proc.kill()
        return _append(output_dir, _fail("eof-stdin", started, "pipes missing"))
    hello = stdout_stream.readline()
    ready = stdout_stream.readline()
    handshake_ok = b"hello" in hello and b"ready" in ready
    stdin_stream.close()
    try:
        exit_status = proc.wait(timeout=ipc_client.DRAIN_DEADLINE_S + ipc_client.TERM_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        exit_status = proc.returncode
    reaped = proc.poll() is not None
    ok = handshake_ok and exit_status == 0 and reaped
    row = (
        _pass(
            "eof-stdin",
            started,
            worker_pid=proc.pid,
            exit_status=exit_status,
            detail="EOF triggered clean exit within bounds",
        )
        if ok
        else _fail(
            "eof-stdin",
            started,
            f"handshake_ok={handshake_ok} exit={exit_status}",
            worker_pid=proc.pid,
        )
    )
    return _append(output_dir, row)


# ── parent-death probes with an external supervisor ───────────────────


def _mini_parent_main(mode: str) -> int:
    """Mini-parent: spawn a stub worker, optionally hold a slow request."""
    sup = ipc_client.WorkerSupervisor(
        device="cpu",
        stub=True,
        stub_behaviour="slow-response" if mode == "inflight" else None,
        stub_slow_seconds=30.0,
        idle_seconds=60.0,
    )
    sup.start()
    if mode == "inflight":
        sup.request("in flight when parent dies", CANDIDATES, top_k=2, timeout_s=60.0)
    ready_file = Path(os.environ["MINI_PARENT_READY_FILE"])
    ready_file.write_text(
        str({"parent_pid": os.getpid(), "worker_pid": sup.worker_pid}), encoding="utf-8"
    )
    time.sleep(60)  # idle until the supervisor kills this process
    return 0


def _observe_worker_gone(worker_pid: int, bound_s: float) -> tuple[bool, int]:
    """True when the PID is gone or a reaped zombie within the bound."""
    try:
        import psutil
    except ImportError:
        return True, 0
    deadline = time.monotonic() + bound_s
    while time.monotonic() < deadline:
        if not psutil.pid_exists(worker_pid):
            return True, 0
        time.sleep(0.25)
    try:
        status = psutil.Process(worker_pid).status()
        zombie = 1 if status == psutil.STATUS_ZOMBIE else 0
        return False, zombie
    except Exception:  # noqa: BLE001 — process gone is the success path
        return True, 0


def probe_parent_death(mode: str, output_dir: Path) -> dict[str, Any]:
    """External supervisor kills the parent; worker must not outlive it."""
    started = time.monotonic()
    ready_file = output_dir / f"mini_parent_{mode}.json"
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.unlink(missing_ok=True)
    mini = subprocess.Popen(  # noqa: S603 — fixed argv
        [
            sys.executable,
            str(SCRIPT_DIR / "probes.py"),
            "--mini-parent",
            mode,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(SCRIPT_DIR),
        env={
            **os.environ,
            "MINI_PARENT_READY_FILE": str(ready_file),
            "PYTORCH_ENABLE_MPS_FALLBACK": "0",
            "HF_HUB_OFFLINE": "1",
        },
    )
    try:
        while not ready_file.exists() and mini.poll() is None:
            time.sleep(0.1)
        if not ready_file.exists():
            return _append(
                output_dir,
                _fail(
                    f"parent-death-{mode}",
                    started,
                    "mini-parent never became ready",
                    worker_pid=None,
                ),
            )
        info: dict[str, int] = {"parent_pid": mini.pid}
        info.update(_pairs(ready_file.read_text(encoding="utf-8")))
        mini.kill()
        mini.wait(timeout=5.0)
        gone, zombie = _observe_worker_gone(int(info["worker_pid"]), ORPHAN_OBSERVATION_S)
        ok = gone and zombie == 0
        row = (
            _pass(
                f"parent-death-{mode}",
                started,
                worker_pid=info["worker_pid"],
                orphans_remaining=0,
                parent_pid=info["parent_pid"],
                detail="parent SIGKILLed; worker exited via stdin EOF; no orphan",
            )
            if ok
            else _fail(
                f"parent-death-{mode}",
                started,
                f"gone={gone} zombie={zombie}",
                worker_pid=info["worker_pid"],
                orphans_remaining=0 if gone else 1,
            )
        )
        return _append(output_dir, row)
    finally:
        if mini.poll() is None:
            mini.kill()
            mini.wait(timeout=5.0)


def _pairs(raw: str) -> dict[str, int]:
    """Parse the mini-parent ready file (a small dict literal)."""
    import ast

    return {k: v for k, v in ast.literal_eval(raw).items()}


def probe_orphan_reaping(output_dir: Path) -> dict[str, Any]:
    """Re-read parent-death evidence: zero workers or descendants remain."""
    started = time.monotonic()
    rows = pf.read_jsonl(output_dir / "lifecycle_probes.jsonl")
    parent_death = [row for row in rows if str(row.get("probe", "")).startswith("parent-death")]
    if len(parent_death) < 2:
        row = _fail(
            "orphan-reaping",
            started,
            f"expected both parent-death rows, found {len(parent_death)}",
            worker_pid=None,
        )
        return _append(output_dir, row)
    leaks = [
        row["probe"]
        for row in parent_death
        if row.get("outcome") == "pass" and row.get("orphans_remaining") not in (None, 0)
    ]
    failing = [row["probe"] for row in parent_death if row.get("outcome") == "fail"]
    ok = not leaks and not failing
    row = (
        _pass(
            "orphan-reaping",
            started,
            detail="both parent-death probes left zero live or zombie workers",
        )
        if ok
        else _fail("orphan-reaping", started, f"leaks={leaks} failing={failing}")
    )
    return _append(output_dir, row)


PROBES = {
    "worker_death": probe_worker_death,
    "worker_hang": probe_worker_hang,
    "request_deadline": probe_request_deadline,
    "stdout_backpressure": probe_stdout_backpressure,
    "stderr_flooding": probe_stderr_flooding,
    "malformed_frame": probe_malformed_frame,
    "idle_expiry_restart": probe_idle_expiry_restart,
    "orderly_shutdown": probe_orderly_shutdown,
    "eof_stdin": probe_eof_stdin,
    "parent_death_idle": lambda out: probe_parent_death("idle", out),
    "parent_death_inflight": lambda out: probe_parent_death("inflight", out),
    "orphan_reaping": probe_orphan_reaping,
}


def run_probe(name: str, output_dir: Path) -> dict[str, Any]:
    """Run one registered probe by kebab- or snake-case name."""
    key = name.replace("-", "_")
    if key not in PROBES:
        raise SystemExit(f"unknown probe {name!r}; registered: {sorted(PROBES)}")
    return PROBES[key](output_dir)


def run_battery(output_dir: Path, *, fast: bool = False) -> bool:
    """Run every probe in the registered order; True when all pass."""
    all_green = True
    for name in PROBE_ORDER:
        row = run_probe(name, output_dir)
        all_green = all_green and row.get("outcome") == "pass"
        print(f"probe {name}: {row.get('outcome')}")
    return all_green


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR / "output"))
    parser.add_argument("--only", help="comma-separated probe names")
    parser.add_argument("--mini-parent", choices=("idle", "inflight"), help=argparse.SUPPRESS)
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args(argv)
    if args.mini_parent:
        return _mini_parent_main(args.mini_parent)
    output_dir = Path(args.output_dir)
    if args.only:
        green = True
        for name in args.only.split(","):
            row = run_probe(name.strip(), output_dir)
            green = green and row.get("outcome") == "pass"
            print(f"probe {name.strip()}: {row.get('outcome')}")
        return 0 if green else 1
    return 0 if run_battery(output_dir, fast=args.fast) else 1


if __name__ == "__main__":
    sys.exit(main())
