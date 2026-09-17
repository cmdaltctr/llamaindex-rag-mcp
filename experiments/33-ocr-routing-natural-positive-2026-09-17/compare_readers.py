"""Experiment 33 reader comparison (HANDOFF step 4, extraction quality).

The operator's spot check judged pypdf's text, not the text the pipeline
actually emits. This script scores all three readers of the ADR-066 chain on
exactly the pages the operator reviewed — pdf-inspector, then liteparse, then
pypdf — against the same reference transcription.

Two scores per page and reader:

- ``recall``: share of reference tokens present, the frozen token rule.
- ``order``: longest common subsequence of the reader's token stream against
  the reference token stream, divided by the reference length. Recall says
  whether the words survived; order says whether they arrived in reading
  order, which is what column and table handling changes.

Read-only. It never touches labels, and it runs no OCR.

Environment:
    PDFIUM_LIB_PATH   PDFium shared library (the LiteParse-bundled one)

    uv run python experiments/33-.../compare_readers.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

import freeze  # noqa: E402
from build_labels import TRANSCRIPTS_DIR, recall, tokens  # noqa: E402

OUT = EXP_DIR / "output" / "reader_comparison.json"
MAX_TOKENS = 1500


def order_score(text: str, reference: list[str]) -> float:
    """Return LCS(reader, reference) / len(reference), both as token streams."""
    a, b = tokens(text)[:MAX_TOKENS], reference[:MAX_TOKENS]
    if not b:
        return 0.0
    previous = [0] * (len(b) + 1)
    for token_a in a:
        current = [0] * (len(b) + 1)
        for j, token_b in enumerate(b, 1):
            current[j] = (
                previous[j - 1] + 1 if token_a == token_b else max(previous[j], current[j - 1])
            )
        previous = current
    return round(previous[-1] / len(b), 4)


def main() -> int:
    """Score pdf-inspector and pypdf on every operator-reviewed page."""
    drift = freeze.check()
    if drift:
        print("freeze check failed: " + "; ".join(drift), file=sys.stderr)
        return 1
    if not os.environ.get("PDFIUM_LIB_PATH"):
        print("PDFIUM_LIB_PATH is not set", file=sys.stderr)
        return 1

    import pdf_inspector
    from liteparse import LiteParse
    from pypdf import PdfReader

    sources = {
        d["doc_id"]: d for d in json.loads((EXP_DIR / "sources.json").read_text())["documents"]
    }
    sample = json.loads((EXP_DIR / "spot_check.json").read_text())["random_sample"]

    cache: dict[str, tuple[dict[int, str], dict[int, str], PdfReader]] = {}
    rows = []
    for entry in sample:
        doc_id, page = entry["doc_id"], entry["page"]
        if doc_id not in cache:
            path = str(EXP_DIR / sources[doc_id]["local_path"])
            result = pdf_inspector.extract_pages_markdown(path)
            # extract_pages_markdown numbers pages from 0; process_pdf_with_ocr
            # numbers them from 1, and so do the labels. Normalise to 1-based.
            inspector_pages = {p.page + 1: p.markdown for p in result.pages}
            # The same join the liteparse adapter uses (integrations/pdf/liteparse.py).
            lite = LiteParse(ocr_enabled=False, quiet=True).parse(path)
            lite_pages = {
                p.page_num: "\n".join(item.text for item in p.text_items) for p in lite.pages
            }
            cache[doc_id] = (inspector_pages, lite_pages, PdfReader(path))
        pages, lite_pages, reader = cache[doc_id]
        reference = tokens(
            json.loads((TRANSCRIPTS_DIR / doc_id / f"p{page:03d}.json").read_text("utf-8")).get(
                "transcription"
            )
            or ""
        )
        if not reference:
            continue
        inspector_text = pages.get(page, "")
        liteparse_text = lite_pages.get(page, "")
        try:
            pypdf_text = reader.pages[page - 1].extract_text() or ""
        except Exception:  # noqa: BLE001 - a failed page is an outcome
            pypdf_text = ""
        rows.append(
            {
                "doc_id": doc_id,
                "page": page,
                "stratum": sources[doc_id]["stratum"],
                "presence_label": entry["presence_label"],
                "understanding_label": entry["understanding_label"],
                "note": entry.get("note") or "",
                "reference_tokens": len(reference),
                "pdf_inspector": {
                    "chars": len(inspector_text),
                    "recall": round(recall(inspector_text, reference), 4),
                    "order": order_score(inspector_text, reference),
                },
                "liteparse": {
                    "chars": len(liteparse_text),
                    "recall": round(recall(liteparse_text, reference), 4),
                    "order": order_score(liteparse_text, reference),
                },
                "pypdf": {
                    "chars": len(pypdf_text),
                    "recall": round(recall(pypdf_text, reference), 4),
                    "order": order_score(pypdf_text, reference),
                },
            }
        )
        print(
            f"[compare] {doc_id} p{page}: "
            + " | ".join(
                f"{name} r={rows[-1][name]['recall']:.2f} o={rows[-1][name]['order']:.2f}"
                for name in ("pdf_inspector", "liteparse", "pypdf")
            ),
            flush=True,
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pages": rows}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
