#!/usr/bin/env python3
"""Write per-page reader text for the review columns (task: operator request).

Two columns, every sampled page, both from this worktree's code (the
LiteParse column carries the fixed multi-column join from PR #96):

- ``output/pdf_inspector/<doc>/pNNN.md`` — pdf-inspector's native
  per-page Markdown (extract_pages_markdown, milliseconds);
- ``output/liteparse/<doc>/pNNN.md`` — the LiteParse adapter in the
  rescue path's configuration (extraction-only, OCR forced off),
  per-page text with the reading-order join applied.

Usage (from the repository root):
    uv run python experiments/34-worker-sample-review-2026-09-19/extract_readers.py
    uv run python .../extract_readers.py --only eq01:11   # a page outside the sample (A4)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from extra_pages import EXTRA_PAGES, parse_only, source_pdf

EXP_DIR = Path(__file__).resolve().parent


def main() -> int:
    from omrg.integrations.pdf.registry import get as get_reader

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only", help="restrict to doc:page pairs; may name pages outside the sample"
    )
    args = parser.parse_args()

    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    sources = {
        d["doc_id"]: d for d in json.loads((exp33 / "sources.json").read_text())["documents"]
    }

    import pdf_inspector

    liteparse = get_reader("liteparse")(ocr_enabled=False, num_workers=None)

    rows = sample["pages"]
    if args.only:
        only = parse_only(args.only)
        rows = [r for r in rows + EXTRA_PAGES if (r["doc_id"], r["page"]) in only]
    for doc_id in sorted({row["doc_id"] for row in rows}):
        pages = sorted(r["page"] for r in rows if r["doc_id"] == doc_id)
        pdf = source_pdf(doc_id, exp33, sources)

        pdir = EXP_DIR / "output" / "pdf_inspector" / doc_id
        pdir.mkdir(parents=True, exist_ok=True)
        scan = pdf_inspector.extract_pages_markdown(str(pdf))
        native = {page.page + 1: page.markdown or "" for page in scan.pages}
        for page in pages:
            (pdir / f"p{page:03d}.md").write_text(native.get(page, ""), encoding="utf-8")

        ldir = EXP_DIR / "output" / "liteparse" / doc_id
        ldir.mkdir(parents=True, exist_ok=True)
        by_page: dict[int, str] = {}
        for document in liteparse.load_data(pdf):
            number = document.metadata.get("page")
            if isinstance(number, int) and document.text:
                by_page[number] = document.text
        for page in pages:
            (ldir / f"p{page:03d}.md").write_text(by_page.get(page, ""), encoding="utf-8")

        filled = sum(1 for page in pages if by_page.get(page))
        print(f"[readers] {doc_id}: {len(pages)} pages, {filled} with liteparse text")
    print("wrote output/pdf_inspector/ and output/liteparse/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
