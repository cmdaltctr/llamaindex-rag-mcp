"""Show Experiment 37 OCR progress from output/ocr_state.json.

    uv run python experiments/37-.../status_ocr.py          # once
    uv run python experiments/37-.../status_ocr.py --watch  # refresh every 30 s

Read only: it never changes the run.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
OUT = EXP_DIR / "output"
ENGINES = ("dots-mocr", "paddleocr-vl")
RUNS = ("E-maths", "E-scan", "E-script")
#: Planning rates (s per page) for engines with no finished page yet.
DEFAULT_RATE = {"dots-mocr": 38.2, "paddleocr-vl": 73.0}


def running(engine: str) -> bool:
    """Return True when the engine's runner process is alive."""
    pidfile = OUT / f"run_ocr_{engine}.pid"
    if not pidfile.is_file():
        return False
    try:
        os.kill(int(pidfile.read_text().strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def report() -> str:
    """Build the status text. Engines run in parallel, so time left is the longer one."""
    lines: list[str] = []
    left: list[float] = []
    for engine in ENGINES:
        path = OUT / f"ocr_state_{engine}.json"
        if not path.is_file():
            lines.append(f"\n{engine}: {'RUNNING (loading)' if running(engine) else 'not started'}")
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        totals = {run: len(pages) for run, pages in state.get("page_lists", {}).items()}
        eng = state.get("engines", {}).get(engine, {})
        secs = [
            p["seconds"]
            for r in eng.get("runs", {}).values()
            for p in r["pages"].values()
            if p["status"] == "ok" and not p.get("includes_start")
        ]
        rate = statistics.median(secs) if secs else DEFAULT_RATE[engine]
        peak = eng.get("peak_footprint_bytes")
        status = (
            "FINISHED"
            if state.get("finished_utc")
            else ("RUNNING" if running(engine) else "NOT RUNNING")
        )
        lines.append(
            f"\n{engine}: {status} · median {rate:.1f} s/page{'' if secs else ' (planning rate)'}"
            + (f" · peak memory {peak / 2**30:.1f} GiB" if peak else "")
            + f" · last update {state.get('heartbeat_utc')} UTC"
        )
        remaining = 0.0
        for run in RUNS:
            pages = eng.get("runs", {}).get(run, {}).get("pages", {})
            ok = sum(p["status"] == "ok" for p in pages.values())
            err = sum(p["status"] == "error" for p in pages.values())
            total = totals.get(run, 0)
            remaining += max(total - ok - err, 0) * rate
            bar = "#" * int(20 * (ok + err) / total) if total else ""
            lines.append(f"  {run:9s} [{bar:20s}] {ok + err:3d}/{total:<3d} ok {ok}  errors {err}")
        current = state.get("current")
        if current:
            lines.append(
                f"  now: {current['run']} {current['page']} (since {current['since_utc']} UTC)"
            )
        if not state.get("finished_utc"):
            left.append(remaining)
            lines.append(f"  time left: {remaining / 3600:.1f} h")
        log = OUT / f"run_ocr_{engine}.log"
        if log.is_file():
            tail = subprocess.run(  # noqa: S603 - fixed argv
                ["/usr/bin/tail", "-n", "1", str(log)], capture_output=True, text=True
            ).stdout.rstrip()
            lines.append(f"  log: {tail}")
    finish = (
        f"estimated time left (engines in parallel): {max(left) / 3600:.1f} h"
        if left
        else "ALL FINISHED"
    )
    return finish + "\n" + "\n".join(lines)


def main() -> int:
    """Print the status once, or every 30 s with --watch."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    while True:
        text = report()
        if args.watch:
            print("\033[2J\033[H" + text, flush=True)
            time.sleep(30)
        else:
            print(text)
            return 0


if __name__ == "__main__":
    sys.exit(main())
