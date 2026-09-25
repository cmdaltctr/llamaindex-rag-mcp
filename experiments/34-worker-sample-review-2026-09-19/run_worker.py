#!/usr/bin/env python3
"""Run the OCR worker over the frozen Experiment 34 sample (task 2.2).

One page-listed protocol 1.1 request per document, through OMRG's own
client, against the worker environment provisioned in ``ocr-worker/``.
Checkpoint per document: pages land as ``output/worker/<doc>/pNNN.md``,
state in ``output/worker_state.json`` (atomic rename), so an
interruption resumes without re-running completed documents.

Budget rules (proposal, operator decision 2026-09-19):
- 900-second request timeout per document;
- 2-hour wall-clock cap; the run stops cleanly at the cap and resumes.

Usage (from the repository root, provisioned venv):
    uv run python experiments/34-worker-sample-review-2026-09-19/run_worker.py
    uv run python .../run_worker.py --only eq01:11   # a page outside the sample (A4)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from extra_pages import EXTRA_PAGES, source_pdf

from omrg.integrations.ocr_worker.client import OcrWorkerClient, OcrWorkerError

EXP_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXP_DIR.parents[1]
WORKER_DIR = REPO_ROOT / "ocr-worker"
OUT_DIR = EXP_DIR / "output" / "worker"
STATE = EXP_DIR / "output" / "worker_state.json"

REQUEST_TIMEOUT_S = 900.0
WALL_CAP_S = 2 * 60 * 60
#: Measured 2026-09-19: one dense io06 page took 69 min cold on this
#: machine. A page-listed request gets this many seconds per page (floor
#: REQUEST_TIMEOUT_S) so multi-page requests are not aborted mid-flight.
SECONDS_PER_PAGE_S = 65 * 60


def _write_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    tmp.replace(STATE)


def _worker_command() -> list[str]:
    venv_python = WORKER_DIR / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        raise SystemExit(f"worker venv missing: {venv_python}; run ocr-worker/provision.py first")
    return [str(venv_python), "-m", "omrg_ocr_worker"]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="restrict the run, e.g. 'io06:28,io06:53' (doc:page pairs)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-run completed documents; the old record moves to state['superseded'] (A9)",
    )
    args = parser.parse_args()

    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    sources = {
        d["doc_id"]: d for d in json.loads((exp33 / "sources.json").read_text())["documents"]
    }

    by_doc: dict[str, list[int]] = {}
    # Extra pages join only through --only, which intersects them away otherwise.
    for row in sample["pages"] + (EXTRA_PAGES if args.only else []):
        by_doc.setdefault(row["doc_id"], []).append(row["page"])
    if args.only:
        only: dict[str, list[int]] = {}
        for item in args.only.split(","):
            doc, _, page = item.partition(":")
            only.setdefault(doc.strip(), []).append(int(page))
        by_doc = {doc: sorted(set(by_doc.get(doc, [])) & set(pages)) for doc, pages in only.items()}
        by_doc = {doc: pages for doc, pages in by_doc.items() if pages}
    for pages in by_doc.values():
        pages.sort()

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": {}}
    started = time.perf_counter()

    with OcrWorkerClient(
        _worker_command(), cwd=str(WORKER_DIR), request_timeout=REQUEST_TIMEOUT_S
    ) as client:
        for doc_id in sorted(by_doc):
            pages = by_doc[doc_id]
            # A later run over other pages of a document already in the state
            # gets its own key, so the earlier run's timing and merged text stay.
            key = doc_id
            if doc_id in state["done"] and state["done"][doc_id].get("pages") != pages:
                key = f"{doc_id}@{','.join(str(p) for p in pages)}"
            if key in state["done"] and state["done"][key].get("pages") == pages:
                if not args.force:
                    print(f"[exp34] {key}: already done, skipping", flush=True)
                    continue
                state.setdefault("superseded", {})[key] = state["done"].pop(key)
            if time.perf_counter() - started > WALL_CAP_S:
                print("[exp34] wall-clock cap reached; stopping (resume later)", flush=True)
                break
            t0 = time.perf_counter()
            pdf = source_pdf(doc_id, exp33, sources)
            record: dict = {"pages": pages, "seconds": None, "error": None}
            try:
                result = client.parse(
                    str(pdf),
                    pages=pages,
                    timeout=max(REQUEST_TIMEOUT_S, SECONDS_PER_PAGE_S * len(pages)),
                )
                if result.metadata.get("page_count") != len(pages):
                    # TDR-027 tripwire: a whole-document run masquerading as a
                    # page-listed response must be recorded, never trusted.
                    raise RuntimeError(
                        f"page_count {result.metadata.get('page_count')} != {len(pages)} requested"
                    )
                texts = list(result.pages_markdown or [])
                if len(texts) != len(pages):
                    raise RuntimeError(
                        f"pages_markdown has {len(texts)} entries for {len(pages)} pages"
                    )
                doc_dir = OUT_DIR / doc_id
                doc_dir.mkdir(parents=True, exist_ok=True)
                for page, text in zip(pages, texts, strict=True):
                    (doc_dir / f"p{page:03d}.md").write_text(text, encoding="utf-8")
                merged = "merged.md"
                if key != doc_id:
                    merged = f"merged_p{pages[0]:03d}-p{pages[-1]:03d}.md"
                (doc_dir / merged).write_text("\n\n".join(texts), encoding="utf-8")
            except (OcrWorkerError, RuntimeError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                print(f"[exp34] {doc_id}: ERROR {record['error']}", flush=True)
            record["seconds"] = round(time.perf_counter() - t0, 1)
            state["done"][key] = record
            _write_state(state)
            print(f"[exp34] {key}: {len(pages)} pages in {record['seconds']}s", flush=True)

    print(json.dumps({k: v["seconds"] for k, v in state["done"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
