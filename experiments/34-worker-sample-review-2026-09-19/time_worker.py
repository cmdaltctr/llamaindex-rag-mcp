#!/usr/bin/env python3
"""Time the worker on a cold and a warm page-listed parse (task 1.2 check).

Sends two page-listed requests to ONE persistent worker process and
reports wall time for each, so the Experiment 34 budget can be checked
against reality: request one carries the model load, request two shows
the steady-state per-page cost.

Usage:
    .venv/bin/python -m omrg_ocr_worker is spawned by this script.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER = REPO_ROOT / "ocr-worker" / ".venv" / "bin" / "python"
PDF = Path(
    "/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-feat-experiment-33-ocr-routing-"
    "natural-positive/experiments/33-ocr-routing-natural-positive-2026-09-17/corpus/natural/io06.pdf"
)

#: The real question: steady-state cost on the hardest class (early-modern
#: print). Request one carries the model load; request two is the warm cost.
REQUESTS = [
    {
        "id": "cold-io06-p28",
        "pages": [28],
        "protocol_version": "1.1",
        "type": "parse",
        "pdf_path": str(PDF),
    },
    {
        "id": "warm-io06-p30",
        "pages": [30],
        "protocol_version": "1.1",
        "type": "parse",
        "pdf_path": str(PDF),
    },
]


def main() -> int:
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [str(WORKER), "-m", "omrg_ocr_worker"],
        cwd=str(REPO_ROOT / "ocr-worker"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    if not (proc.stdin and proc.stdout):
        raise SystemExit("worker pipes missing")
    try:
        for req in REQUESTS:
            t0 = time.perf_counter()
            proc.stdin.write(json.dumps(req, sort_keys=True, separators=(",", ":")) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            elapsed = time.perf_counter() - t0
            if not line:
                print(f"{req['id']}: no response (worker died?)", flush=True)
                return 1
            resp = json.loads(line)
            pages = len(resp.get("pages_markdown") or [])
            head = (resp.get("pages_markdown") or [""])[0][:120].replace("\n", " ")
            # Persist what we paid for: probe markdown lands in the same
            # layout the review generator reads, so no compute is wasted.
            out_dir = Path(__file__).resolve().parent / "output" / "worker"
            for page, text in zip(req["pages"], resp.get("pages_markdown") or [], strict=False):
                doc_dir = out_dir / Path(req["pdf_path"]).stem
                doc_dir.mkdir(parents=True, exist_ok=True)
                (doc_dir / f"p{page:03d}.md").write_text(text, encoding="utf-8")
            print(
                f"{req['id']}: ok={resp['ok']} pages={pages} elapsed={elapsed:.1f}s | {head}",
                flush=True,
            )
        return 0
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)


if __name__ == "__main__":
    sys.exit(main())
