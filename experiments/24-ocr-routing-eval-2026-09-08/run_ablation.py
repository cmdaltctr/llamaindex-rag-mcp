"""Experiment 24 ablation runner: fast path vs routed OCR worker.

Cells (declared in plan.json):
- fast_path_baseline: pdf-inspector reader, OCR fallback disabled.
- routed_worker_candidate: same reader wrapped by OcrRoutedPdfInspector,
  gate 0.5/0.5, managed worker client (absolute command, preserved cache).

Fixtures: the five held-out evaluation PDFs only.

Writes output/ablation.json atomically; --resume skips completed cells.
No retrieval, no embedding calls, no index writes.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

EXP_DIR = Path(__file__).resolve().parent
REPO = EXP_DIR.parents[1]
OUT = EXP_DIR / "output/ablation.json"
FIXTURES = sorted((REPO / "tests/fixtures/pdf_baseline/evaluation").glob("*.pdf"))

HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)
LIST_RE = re.compile(r"^\s*(?:[-*+] |\d+\. )", re.MULTILINE)
TABLE_RE = re.compile(r"<table|\|.*\|", re.MULTILINE)

WORKER_PY = REPO / "ocr-worker/.venv/bin/python"


def _settings(cell: str) -> SimpleNamespace:
    """Injected settings per cell, mirroring the frozen plan."""
    base = {
        "ocr_fallback_enabled": False,
        "ocr_fallback_min_confidence": 0.5,
        "ocr_fallback_page_fraction": 0.5,
        "ocr_worker_command": f"{WORKER_PY} -m omrg_ocr_worker",
        "ocr_worker_env_dir": str(REPO / "ocr-worker"),
        "ocr_worker_request_timeout": 600.0,
    }
    if cell == "routed_worker_candidate":
        base["ocr_fallback_enabled"] = True
    return SimpleNamespace(**base)


def _markers(markdown: str) -> dict[str, int]:
    """Count structure markers in emitted Markdown."""
    return {
        "headings": len(HEADING_RE.findall(markdown)),
        "list_items": len(LIST_RE.findall(markdown)),
        "tables": len(TABLE_RE.findall(markdown)),
    }


def _run_cell(cell: str) -> dict:
    """Run one cell over every evaluation fixture."""
    from omrg.integrations.pdf.factory import build_pdf_reader

    settings = _settings(cell)
    ocr_client = None
    if cell == "routed_worker_candidate":
        from omrg.capabilities import build_managed_ocr_client

        ocr_client = build_managed_ocr_client(settings)

    rows: list[dict] = []
    for fixture in FIXTURES:
        reader = build_pdf_reader("pdf_inspector", settings, ocr_client=ocr_client)
        row: dict = {"fixture": fixture.name}
        t0 = time.perf_counter()
        try:
            docs = reader.load_data(fixture)
            row["latency_s"] = round(time.perf_counter() - t0, 3)
            text = "\n".join(d.text for d in docs)
            meta = dict(docs[0].metadata) if docs else {}
            row.update(
                {
                    "documents": len(docs),
                    "markdown_chars": len(text),
                    "markdown": text,
                    "markdown_sha256": __import__("hashlib")
                    .sha256(text.encode("utf-8"))
                    .hexdigest(),
                    "markers": _markers(text),
                    "pdf_type": meta.get("pdf_type"),
                    "pdf_confidence": meta.get("pdf_confidence"),
                    "pages_needing_ocr": meta.get("pages_needing_ocr"),
                    "page_count": meta.get("page_count"),
                    "ocr_required": meta.get("ocr_required"),
                    "ocr_used": meta.get("ocr_used"),
                    "ocr_backend": meta.get("ocr_backend"),
                    "error": None,
                }
            )
        except Exception as exc:  # structured per-file failure record
            row["latency_s"] = round(time.perf_counter() - t0, 3)
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(
            f"[{cell}] {fixture.name}: "
            f"{'ERROR ' + row['error'] if row.get('error') else row.get('markdown_chars')} "
            f"({row['latency_s']}s)",
            flush=True,
        )

    if ocr_client is not None:
        ocr_client.close()
    return {"done": True, "rows": rows}


def main() -> None:
    """Run declared cells with checkpoint/resume."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cell", choices=["fast_path_baseline", "routed_worker_candidate"])
    args = parser.parse_args()

    state: dict = {"cells": {}}
    if OUT.exists() and args.resume:
        state = json.loads(OUT.read_text(encoding="utf-8"))
    cells = [args.cell] if args.cell else ["fast_path_baseline", "routed_worker_candidate"]

    for cell in cells:
        if args.resume and state["cells"].get(cell, {}).get("done"):
            print(f"[skip] {cell} already complete", flush=True)
            continue
        state["cells"][cell] = _run_cell(cell)
        tmp = OUT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(OUT)
        print(f"[checkpoint] {cell} written", flush=True)


if __name__ == "__main__":
    main()
