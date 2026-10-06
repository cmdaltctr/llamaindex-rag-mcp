"""Experiment 37 OCR runs E-maths, E-scan and E-script (both engines).

Every page goes through the host path: ``build_ocr_routes`` with the
engine named as the primary route (``OCR_ENGINE_PRIMARY``) and no
fallback, then one protocol 1.1 page-listed request per page. The script
never imports an engine package.

Each engine runs E-maths, E-scan, E-script in its own process, so
dots-mocr (MPS GPU) and paddleocr-vl (CPU) can run at the same time. One
worker process per engine, so each model loads once.

    uv run python -u experiments/37-.../run_ocr.py --engine dots-mocr --resume

Use ``start_ocr.sh`` to run it detached, ``status_ocr.py`` to watch it and
``stop_ocr.sh`` to stop it. A stopped or interrupted run continues from
the last finished page with ``--resume``.

Writes (atomic, ``.tmp`` then rename):
- ``output/<engine>/<doc_id>/p<NNN>.md`` (gitignored page text);
- ``output/ocr_state_<engine>.json`` after every page (timings, errors, memory).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
#: One state file per engine, so both engines can run at once (GPU and CPU).
STATE_TEMPLATE = "ocr_state_{engine}.json"
ENGINES = ("dots-mocr", "paddleocr-vl")
RUNS = ("E-maths", "E-scan", "E-script")
MATHS_PAGES_PER_PAPER = 8
SEED = 37


def utc() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_atomic(path: Path, text: str) -> None:
    """Write *text* through a ``.tmp`` file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def page_lists() -> dict[str, list[tuple[str, int]]]:
    """Return the ``(doc_id, page)`` list of each run, from frozen inputs."""
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    labels = json.loads((EXP_DIR / "maths_labels.json").read_text(encoding="utf-8"))["documents"]
    sources = json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))["documents"]
    maths: list[tuple[str, int]] = []
    for doc in sources:
        if doc["set"] != "maths_positive":
            continue
        pages = sorted(
            int(p) for p, entry in labels[doc["doc_id"]].items() if entry["label"] == "maths"
        )
        if len(pages) > MATHS_PAGES_PER_PAPER:
            pages = sorted(random.Random(SEED).sample(pages, MATHS_PAGES_PER_PAPER))  # noqa: S311 - seeded page sample, not security
        maths += [(doc["doc_id"], p) for p in pages]
    scan = [(p["doc_id"], p["page"]) for p in plan["sets"]["scanned"]["pages"]]
    script = [(p["doc_id"], p["page"]) for p in plan["sets"]["script_handwriting"]["pages"]]
    return {"E-maths": maths, "E-scan": scan, "E-script": script}


def doc_paths() -> dict[str, Path]:
    """Return the local PDF path of every document in sources.json."""
    sources = json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))["documents"]
    return {d["doc_id"]: EXP_DIR / d["local_path"] for d in sources}


class PeakFootprint:
    """Sample the worker processes' lifetime peak memory footprint (macOS).

    ``proc_pid_rusage`` (``RUSAGE_INFO_V4``) reports
    ``ri_lifetime_max_phys_footprint``, which includes MPS allocations in
    unified memory. A thread reads it for every child process every 10 s.
    """

    _LIFETIME_MAX_INDEX = 2 + 28  # 16-byte uuid, then uint64 fields

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        try:
            self._lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        except OSError:
            self._lib = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def sample(self) -> int:
        """Read every child now; return the peak seen so far."""
        if self._lib is None:
            return self.peak
        children = subprocess.run(  # noqa: S603 - fixed argv
            ["/usr/bin/pgrep", "-P", str(os.getpid())], capture_output=True, text=True
        ).stdout.split()
        for pid in children:
            buf = (ctypes.c_uint64 * 48)()
            if self._lib.proc_pid_rusage(int(pid), 4, ctypes.byref(buf)) == 0:
                self.peak = max(self.peak, int(buf[self._LIFETIME_MAX_INDEX]))
        return self.peak

    def reset(self) -> None:
        """Start a new peak (one per engine)."""
        self.peak = 0

    def _loop(self) -> None:
        while not self._stop.wait(10):
            self.sample()

    def stop(self) -> None:
        """Stop the sampling thread."""
        self._stop.set()


def build_routes(engine: str, workers_dir: str) -> Any:
    """Build the host OCR routes with *engine* as the only (primary) route."""
    from omrg.capabilities import build_ocr_routes
    from omrg.config import Settings

    settings = Settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=workers_dir,
        ocr_engine_primary=engine,
        ocr_engine_fallback="",
        ocr_worker_command="",
        ocr_worker_env_dir="",
    )
    return settings, build_ocr_routes(settings)


def fingerprint_dict(fp: Any) -> dict[str, Any]:
    """Return the fingerprint fields as plain JSON."""
    return {
        "backend_id": fp.backend_id,
        "model": [fp.model_identity, fp.model_revision],
        "pipeline": [fp.pipeline_identity, fp.pipeline_revision],
        "protocol_version": fp.protocol_version,
        "packages": dict(fp.packages),
    }


def run_engine(
    engine: str, args: argparse.Namespace, state: dict[str, Any], save: Any, meter: PeakFootprint
) -> bool:
    """Run every run for one engine; return False on a hard stop."""
    from omrg.integrations.ocr_worker.client import OcrWorkerError
    from omrg.integrations.ocr_worker.routes import request_timeout

    lists, paths = page_lists(), doc_paths()
    settings, routes = build_routes(engine, args.workers_dir)
    client = routes.select()
    if client is None or client is not routes.primary:
        print(
            f"[{engine}] route unavailable: check OCR_WORKERS_DIR and the engine install",
            flush=True,
        )
        routes.close()
        return False
    eng = state["engines"].setdefault(engine, {"runs": {}})
    eng["fingerprint"] = fingerprint_dict(routes.fingerprint)
    meter.reset()
    try:
        for run in RUNS:
            pages = lists[run]
            done = eng["runs"].setdefault(run, {"pages": {}})["pages"]
            eng["runs"][run]["total"] = len(pages)
            for doc_id, page in pages:
                key = f"{doc_id}:{page}"
                out = EXP_DIR / "output" / engine / doc_id / f"p{page:03d}.md"
                prior = done.get(key)
                if prior and (
                    prior["status"] == "ok"
                    and out.is_file()
                    or prior["status"] == "error"
                    and not args.retry_failed
                ):
                    continue
                if args.stop_after_h and time.monotonic() - args.started > args.stop_after_h * 3600:
                    print(
                        f"[stop] runtime cap {args.stop_after_h} h reached; resume later",
                        flush=True,
                    )
                    return False
                state["current"] = {"engine": engine, "run": run, "page": key, "since_utc": utc()}
                save()
                first = not client.is_started
                start = time.perf_counter()
                try:
                    result = client.parse(
                        str(paths[doc_id]), pages=[page], timeout=request_timeout(settings, 1)
                    )
                    text = (result.pages_markdown or (result.markdown,))[0]
                    write_atomic(out, text)
                    entry: dict[str, Any] = {"status": "ok", "chars": len(text)}
                except OcrWorkerError as exc:
                    entry = {"status": "error", "code": exc.code, "message": str(exc)[:300]}
                entry.update(
                    {
                        "seconds": round(time.perf_counter() - start, 2),
                        "includes_start": bool(first),
                        "utc": utc(),
                    }
                )
                done[key] = entry
                eng["process_generations"] = client.process_generations
                eng["peak_footprint_bytes"] = max(
                    eng.get("peak_footprint_bytes", 0), meter.sample()
                )
                save()
                tag = entry["status"] if entry["status"] == "ok" else f"ERROR {entry['code']}"
                print(
                    f"[{engine} {run}] {key} {tag} {entry['seconds']} s ({len(done)}/{len(pages)})",
                    flush=True,
                )
    finally:
        eng["peak_footprint_bytes"] = max(eng.get("peak_footprint_bytes", 0), meter.sample())
        state["current"] = None
        save()
        routes.close()
    return True


def main() -> int:
    """Run the OCR runs in order."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--resume", action="store_true", help="keep finished pages (required once output exists)"
    )
    parser.add_argument(
        "--retry-failed", action="store_true", help="retry pages that ended in an error"
    )
    parser.add_argument(
        "--engine", choices=ENGINES, help="engine to run (required unless --list-pages)"
    )
    parser.add_argument(
        "--stop-after-h", type=float, default=0.0, help="stop cleanly after this many hours"
    )
    parser.add_argument("--list-pages", action="store_true", help="print the page lists and exit")
    parser.add_argument("--workers-dir", default=os.environ.get("OCR_WORKERS_DIR", ""))
    args = parser.parse_args()
    args.started = time.monotonic()

    if args.list_pages:
        print(
            json.dumps({k: [f"{d}:{p}" for d, p in v] for k, v in page_lists().items()}, indent=1)
        )
        return 0
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    if not plan["ocr_authorisation"].get("approved"):
        print(
            "ocr_authorisation.approved is false in plan.json; no OCR runs",
            file=sys.stderr,
            flush=True,
        )
        return 1
    if not args.workers_dir:
        print("set OCR_WORKERS_DIR or pass --workers-dir", file=sys.stderr, flush=True)
        return 1
    if not args.engine:
        print("pass --engine dots-mocr or --engine paddleocr-vl", file=sys.stderr, flush=True)
        return 1
    state_path = EXP_DIR / "output" / STATE_TEMPLATE.format(engine=args.engine)
    if state_path.is_file() and not args.resume:
        print(f"{state_path.name} exists: pass --resume to continue", file=sys.stderr, flush=True)
        return 1
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    for name in ("OCR_WORKER_COMMAND", "OCR_WORKER_ENV_DIR"):
        os.environ.pop(name, None)

    state: dict[str, Any] = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file()
        else {"engines": {}}
    )
    state.update({"pid": os.getpid(), "started_utc": utc(), "finished_utc": None})
    state["page_lists"] = {k: [f"{d}:{p}" for d, p in v] for k, v in page_lists().items()}

    def save() -> None:
        state["heartbeat_utc"] = utc()
        write_atomic(state_path, json.dumps(state, indent=1, ensure_ascii=False) + "\n")

    def on_signal(signum: int, _frame: Any) -> None:
        raise SystemExit(f"stopped by signal {signum}")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    meter = PeakFootprint()
    try:
        for engine in ENGINES:
            if args.engine and engine != args.engine:
                continue
            print(f"[{engine}] start {utc()}", flush=True)
            if not run_engine(engine, args, state, save, meter):
                return 2
        state["finished_utc"] = utc()
        print(f"[done] {utc()}", flush=True)
        return 0
    finally:
        meter.stop()
        state["pid"] = None
        save()


if __name__ == "__main__":
    sys.exit(main())
