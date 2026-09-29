#!/usr/bin/env python3
"""Write the local OCR tier text per page (review column, protocol A5).

The local OCR tier is pdf-inspector's selective OCR (PP-OCRv6 Small on ONNX
Runtime, CPU): what the pipeline falls back to today on scanned pages. The
call matches Experiment 33 task 6.7 (``local_ocr.py``): ``force`` mode, so
pdf-inspector's own routing is never consulted.

Output: ``output/local_ocr/<doc>/pNNN.md`` and ``output/local_ocr_state.json``
(per-document seconds, per-page OCR confidence, source, hosted recommendation).

Environment (paths, not secrets):
    PDFIUM_LIB_PATH       PDFium shared library (the LiteParse-bundled one)
    ORT_DYLIB_PATH        ONNX Runtime shared library
    PDF_INSPECTOR_MODEL_CACHE  model cache (Experiment 33 reuses output/.pdfi_models)

Usage (from the repository root):
    uv run python experiments/34-worker-sample-review-2026-09-19/local_ocr_pages.py \
        --only bd03:1,bd03:2,io06:28,io06:53,eq01:11
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path

from extra_pages import EXTRA_PAGES, parse_only, source_pdf

EXP_DIR = Path(__file__).resolve().parent
OUT_DIR = EXP_DIR / "output" / "local_ocr"
STATE = EXP_DIR / "output" / "local_ocr_state.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only", help="restrict to doc:page pairs; may name pages outside the sample"
    )
    args = parser.parse_args()
    for var in ("PDFIUM_LIB_PATH", "ORT_DYLIB_PATH"):
        if not os.environ.get(var):
            print(f"{var} is not set", file=sys.stderr)
            return 1

    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    os.environ.setdefault("PDF_INSPECTOR_MODEL_CACHE", str(exp33 / "output" / ".pdfi_models"))
    sources = {
        d["doc_id"]: d for d in json.loads((exp33 / "sources.json").read_text())["documents"]
    }

    import pdf_inspector

    rows = sample["pages"]
    if args.only:
        only = parse_only(args.only)
        rows = [r for r in rows + EXTRA_PAGES if (r["doc_id"], r["page"]) in only]

    state = json.loads(STATE.read_text()) if STATE.exists() else {"pages": {}, "docs": {}}
    state["identity"] = {
        "pdf_inspector": importlib.metadata.version("pdf-inspector"),
        "onnxruntime": importlib.metadata.version("onnxruntime"),
        "mode": "force",
    }
    for doc_id in sorted({row["doc_id"] for row in rows}):
        pages = sorted(r["page"] for r in rows if r["doc_id"] == doc_id)
        t0 = time.perf_counter()
        try:
            result = pdf_inspector.process_pdf_with_ocr(
                str(source_pdf(doc_id, exp33, sources)), mode="force", page_numbers=pages
            )
            error = None
        except Exception as exc:  # noqa: BLE001 - a failed document is an outcome
            result, error = None, type(exc).__name__
        elapsed = time.perf_counter() - t0
        outputs = {pg.page_number: pg for pg in (result.pages if result else [])}
        hosted = set(result.pages_recommending_hosted) if result else set()
        (OUT_DIR / doc_id).mkdir(parents=True, exist_ok=True)
        for page in pages:
            out = outputs.get(page)
            text = (out.markdown or "") if out else ""
            (OUT_DIR / doc_id / f"p{page:03d}.md").write_text(text, encoding="utf-8")
            provenance = out.provenance if out else None
            state["pages"][f"{doc_id}/{page}"] = {
                "source": provenance.source if provenance else None,
                "confidence": provenance.ocr_confidence if provenance else None,
                "hosted_recommended": page in hosted,
                "chars": len(text),
            }
        state["docs"][doc_id] = {"pages": pages, "seconds": round(elapsed, 1), "error": error}
        print(f"[local_ocr] {doc_id}: {len(pages)} pages in {elapsed:.1f}s error={error}")

    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    tmp.replace(STATE)
    print(f"wrote {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
