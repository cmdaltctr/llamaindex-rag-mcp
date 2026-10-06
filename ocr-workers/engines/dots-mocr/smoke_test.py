#!/usr/bin/env python3
"""Offline smoke test for the provisioned dots-mocr engine (tasks 3.4, 3.5).

SEPARATE from the main OMRG pytest suite: it needs the provisioned engine
environment and the downloaded model. Provision first, with operator
approval and licence acceptance::

    python3 ocr-workers/provision.py dots-mocr --accept-model-licence

The test runs the capability command, then ONE worker process that
receives one page-listed request per ``--case``, over the real JSON Lines
protocol. The worker runs under ``sandbox-exec`` with network access
denied, so a parse that tries to download fails. ``/usr/bin/time -l``
reports the process's peak memory footprint; on Apple Silicon this
includes the MPS allocations, which live in unified memory.

Without ``--run`` the script prints its plan and runs nothing.

Usage::

    python3 ocr-workers/engines/dots-mocr/smoke_test.py \\
        --case eq01=/path/eq01.pdf:11 --case io06=/path/io06.pdf:28 --run

Evidence (capability JSON, per-page Markdown, timings) is written to
``smoke_evidence/``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = ENGINE_DIR / ".venv" / "bin" / "python"
EVIDENCE_DIR = ENGINE_DIR / "smoke_evidence"
PROTOCOL_VERSION = "1.1"

#: Deny every network connection; local files and Metal stay available.
SANDBOX_PROFILE = "(version 1)(allow default)(deny network-outbound)(deny network-inbound)"

_PEAK_RE = re.compile(r"^\s*(\d+)\s+peak memory footprint", re.MULTILINE)


def parse_case(text: str) -> tuple[str, Path, int]:
    """Parse ``name=path.pdf:page`` into its three parts."""
    name, _, rest = text.partition("=")
    path, _, page = rest.rpartition(":")
    if not name or not path or not page.isdigit():
        raise argparse.ArgumentTypeError(f"case {text!r} is not name=path.pdf:page")
    return name, Path(path).expanduser().resolve(), int(page)


def worker_command() -> list[str]:
    """Return the sandboxed, timed worker command."""
    return [
        "/usr/bin/sandbox-exec",
        "-p",
        SANDBOX_PROFILE,
        "/usr/bin/time",
        "-l",
        str(VENV_PYTHON),
        "-m",
        "omrg_ocr_worker_core",
    ]


def run(cases: list[tuple[str, Path, int]]) -> int:
    """Probe, parse every case in one sandboxed worker, and save evidence."""
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(VENV_PYTHON), "-m", "omrg_ocr_worker_core", "--capabilities"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=ENGINE_DIR,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        print(f"error: capability probe failed: {probe.stderr[-2000:]}", file=sys.stderr)
        return 1
    capabilities = json.loads(probe.stdout.splitlines()[0])
    if capabilities.get("backend_id") != "dots_mocr":
        print(f"error: probe backend_id {capabilities.get('backend_id')!r}", file=sys.stderr)
        return 1
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "capabilities.json").write_text(
        json.dumps(capabilities, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"capabilities: {json.dumps(capabilities, sort_keys=True)}")

    # Standard error goes to a file: a full pipe would block the worker.
    stderr_path = EVIDENCE_DIR / "worker-stderr.log"
    stderr_file = stderr_path.open("w", encoding="utf-8")
    worker = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        worker_command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        encoding="utf-8",
        cwd=ENGINE_DIR,
    )
    assert worker.stdin is not None and worker.stdout is not None  # noqa: S101
    results: list[dict[str, Any]] = []
    failed = False
    for name, pdf, page in cases:
        request = {
            "id": f"smoke-{name}-p{page}",
            "pages": [page],
            "pdf_path": str(pdf),
            "protocol_version": PROTOCOL_VERSION,
            "type": "parse",
        }
        started = time.perf_counter()
        worker.stdin.write(json.dumps(request, sort_keys=True) + "\n")
        worker.stdin.flush()
        line = worker.stdout.readline()
        seconds = time.perf_counter() - started
        response = json.loads(line) if line.strip() else {}
        pages = response.get("pages_markdown") or []
        text = pages[0] if len(pages) == 1 else ""
        ok = response.get("ok") is True and response.get("id") == request["id"]
        (EVIDENCE_DIR / f"{name}-p{page:03d}.md").write_text(text, encoding="utf-8")
        results.append(
            {"case": name, "page": page, "ok": ok, "seconds": round(seconds, 1), "chars": len(text)}
        )
        print(f"{name} p{page}: ok={ok} seconds={seconds:.1f} chars={len(text)}")
        if not ok:
            failed = True
            print(f"error: response {line[:600]!r}", file=sys.stderr)
    worker.stdin.close()
    worker.wait(timeout=120)
    stderr_file.close()
    stderr = stderr_path.read_text(encoding="utf-8")
    peak = _PEAK_RE.search(stderr)
    summary = {
        "cases": results,
        "network": "denied by sandbox-exec",
        "peak_memory_footprint_bytes": int(peak.group(1)) if peak else None,
        "note": "the first case's seconds include model load",
    }
    (EVIDENCE_DIR / "run.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"peak memory footprint bytes: {summary['peak_memory_footprint_bytes']}")
    if failed:
        print("worker stderr tail:", stderr[-3000:], file=sys.stderr)
        return 1
    print("OCR PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Offline smoke test for dots-mocr.")
    parser.add_argument(
        "--case", action="append", type=parse_case, required=True, help="name=path.pdf:page"
    )
    parser.add_argument("--run", action="store_true", help="run the worker (default: plan only)")
    args = parser.parse_args(argv)
    missing = [str(pdf) for _, pdf, _ in args.case if not pdf.is_file()]
    if missing:
        print(f"error: missing PDF {missing}", file=sys.stderr)
        return 2
    print("plan:")
    print(f"  worker : {' '.join(worker_command())}")
    for name, pdf, page in args.case:
        print(f"  case   : {name} {pdf} page {page}")
    if not args.run:
        print("plan only: nothing ran.")
        return 0
    if not VENV_PYTHON.is_file():
        print("error: engine not provisioned (see the module docstring)", file=sys.stderr)
        return 1
    return run(args.case)


if __name__ == "__main__":
    raise SystemExit(main())
