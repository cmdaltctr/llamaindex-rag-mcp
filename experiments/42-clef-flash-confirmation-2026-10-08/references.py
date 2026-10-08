"""Task 3.2: local dots.mocr reference transcription of every page (OD2).

Uses the shipped host path (``omrg.capabilities.build_ocr_routes``) with
dots-mocr as the only route, one page per request, as in Experiment 37.
The engine runs offline (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1).

Writes (gitignored) ``output/.references/<doc_id>/pNNN.md`` and the state file
``output/reference_state.json`` after every page. Interrupted runs continue
with ``--resume``.

    uv run --no-sync python -u references.py --resume
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exp42_io import EXP_DIR, OUTPUT, atomic_json, plan, read_json, sha256

STATE = OUTPUT / "reference_state.json"
TEXT_DIR = OUTPUT / ".references"
WORKERS_DIR = EXP_DIR.parent.parent / "ocr-workers"


def utc() -> str:
    """Return the current UTC time."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_text(path: Path, text: str) -> None:
    """Write text through a .tmp file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_routes() -> tuple[Any, Any]:
    """Host OCR routes with dots-mocr as the only (primary) route."""
    from omrg.capabilities import build_ocr_routes
    from omrg.config import Settings

    settings = Settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(WORKERS_DIR),
        ocr_engine_primary="dots-mocr",
        ocr_engine_fallback="",
        ocr_worker_command="",
        ocr_worker_env_dir="",
    )
    return settings, build_ocr_routes(settings)


def main() -> int:
    """Transcribe every page in sources.json order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    plan()
    if STATE.is_file() and not args.resume:
        print("reference_state.json exists: pass --resume", file=sys.stderr)
        return 1
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    for name in ("OCR_WORKER_COMMAND", "OCR_WORKER_ENV_DIR"):
        os.environ.pop(name, None)
    from omrg.integrations.ocr_worker.client import OcrWorkerError
    from omrg.integrations.ocr_worker.routes import request_timeout

    documents = read_json(EXP_DIR / "sources.json")["documents"]
    state: dict[str, Any] = read_json(STATE) if STATE.is_file() else {"pages": {}}
    state.update(
        {
            "pid": os.getpid(),
            "started_utc": utc(),
            "finished_utc": None,
            "offline_env": {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            "sources_sha256": sha256(EXP_DIR / "sources.json"),
            "total_pages": sum(d["page_count"] for d in documents),
        }
    )

    def save() -> None:
        state["heartbeat_utc"] = utc()
        atomic_json(STATE, state)

    def on_signal(signum: int, _frame: Any) -> None:
        raise SystemExit(f"stopped by signal {signum}")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    settings, routes = build_routes()
    client = routes.select()
    if client is None or client is not routes.primary:
        print("dots-mocr route unavailable: check ocr-workers provisioning", flush=True)
        routes.close()
        return 2
    fp = routes.fingerprint
    state["engine"] = {
        "backend_id": fp.backend_id,
        "model": [fp.model_identity, fp.model_revision],
        "pipeline": [fp.pipeline_identity, fp.pipeline_revision],
        "protocol_version": fp.protocol_version,
        "packages": dict(fp.packages),
    }
    done = state["pages"]
    try:
        for doc in documents:
            for page in range(1, doc["page_count"] + 1):
                key = f"{doc['doc_id']}:{page}"
                out = TEXT_DIR / doc["doc_id"] / f"p{page:03d}.md"
                prior = done.get(key)
                if prior and (
                    (prior["status"] == "ok" and out.is_file())
                    or (prior["status"] == "error" and not args.retry_failed)
                ):
                    continue
                first = not client.is_started
                start = time.perf_counter()
                try:
                    result = client.parse(
                        str(EXP_DIR / doc["local_path"]),
                        pages=[page],
                        timeout=request_timeout(settings, 1),
                    )
                    text = (result.pages_markdown or (result.markdown,))[0]
                    write_text(out, text)
                    entry: dict[str, Any] = {"status": "ok", "chars": len(text)}
                except OcrWorkerError as exc:
                    entry = {"status": "error", "code": exc.code, "message": str(exc)[:300]}
                entry.update(
                    {
                        "seconds": round(time.perf_counter() - start, 2),
                        "includes_start": first,
                        "utc": utc(),
                    }
                )
                done[key] = entry
                save()
                print(
                    f"[ref] {key} {entry['status']} {entry['seconds']} s "
                    f"({len(done)}/{state['total_pages']})",
                    flush=True,
                )
        state["finished_utc"] = utc()
        return 0
    finally:
        state["pid"] = None
        save()
        routes.close()


if __name__ == "__main__":
    sys.exit(main())
