"""Render PDF pages to PNG for the Experiment 37 review pages.

Needs only ``pypdfium2``, which the project installs only as an optional
extra. Run it with the dots-mocr engine interpreter, which already has
it (the same renderer the engine uses), so nothing is installed:

    $OCR_WORKERS_DIR/engines/dots-mocr/.venv/bin/python \\
        experiments/37-.../render_pages.py --labelled
    $OCR_WORKERS_DIR/engines/dots-mocr/.venv/bin/python \\
        experiments/37-.../render_pages.py --pages bd03:4,6 io06:53

Writes ``output/.pages/<doc_id>/p<NNN>.png`` (gitignored). Existing
images are kept, so a rerun only renders what is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pypdfium2 as pdfium

EXP_DIR = Path(__file__).resolve().parent
PAGES_DIR = EXP_DIR / "output" / ".pages"
SCALE = 1.5


def parse_pages(specs: list[str]) -> dict[str, list[int] | None]:
    """Parse ``doc:1,2`` specs; a bare ``doc`` means every page."""
    wanted: dict[str, list[int] | None] = {}
    for spec in specs:
        doc_id, _, pages = spec.partition(":")
        wanted[doc_id] = [int(p) for p in pages.split(",")] if pages else None
    return wanted


def render(doc_path: Path, doc_id: str, pages: list[int] | None) -> int:
    """Render the listed pages (all when ``None``); return how many were new."""
    pdf = pdfium.PdfDocument(str(doc_path))
    numbers = pages or list(range(1, len(pdf) + 1))
    out_dir = PAGES_DIR / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for number in numbers:
        target = out_dir / f"p{number:03d}.png"
        if target.is_file():
            continue
        tmp = target.with_name(target.name + ".tmp")
        pdf[number - 1].render(scale=SCALE).to_pil().save(tmp, format="PNG")
        tmp.replace(target)
        made += 1
    pdf.close()
    return made


def main() -> int:
    """Render the requested pages."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--labelled", action="store_true", help='every page of documents with "label_pages": true'
    )
    parser.add_argument("--pages", nargs="*", default=[], help="doc_id or doc_id:1,2,3")
    args = parser.parse_args()

    sources = {
        d["doc_id"]: d
        for d in json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))["documents"]
    }
    wanted = parse_pages(args.pages)
    if args.labelled:
        for doc_id, doc in sources.items():
            if doc.get("label_pages"):
                wanted.setdefault(doc_id, None)
    if not wanted:
        print("nothing to render: pass --labelled or --pages", file=sys.stderr, flush=True)
        return 1
    for doc_id, pages in wanted.items():
        made = render(EXP_DIR / sources[doc_id]["local_path"], doc_id, pages)
        print(f"[render] {doc_id}: {made} new page images", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
