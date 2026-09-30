"""Experiment 33 page-fraction boundary probe (task 5.4, exploratory).

Builds synthetic mixed PDFs with a known share of degraded image-only pages,
so the shipped gate's 0.10 page-fraction switch can be observed on documents
whose true answer is known. Results are exploratory and never held-out
evidence; the thresholds are never changed.

Base: the clean CC BY arXiv source 2308.13049 (also a synthetic-set source).
Replaced pages are chosen with a seeded generator from page 2 onwards (the
title page stays clean), and degraded with the synthetic-set recipe.

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/make_probe.py
    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/route.py --probe
    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/make_probe.py --report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

from make_synthetic import _fetch, _page_params, _run  # noqa: E402

SOURCE_ARXIV = "2308.13049"
CLEAN = EXP_DIR / "corpus" / "synthetic" / "clean" / f"{SOURCE_ARXIV}.pdf"
OUT_DIR = EXP_DIR / "corpus" / "probe"
MANIFEST = EXP_DIR / "probe.json"
ROUTING = EXP_DIR / "output" / "probe" / "routing.json"
SUMMARY = EXP_DIR / "output" / "probe" / "summary.json"
PAGE_FRACTION = 0.10
SEED = 3354

#: (doc_id, base pages, image pages): shares 0%, 5%, 9.5%, 10%, 15%, 20%.
CELLS = [
    ("pb00", 20, 0),
    ("pb01", 20, 1),
    ("pb05", 21, 2),
    ("pb02", 20, 2),
    ("pb03", 20, 3),
    ("pb04", 20, 4),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _image_page(page: int, params: dict, seed: int, work: Path) -> Path:
    png = work / f"src{page:03d}"
    _run("pdftoppm", "-r", "200", "-f", str(page), "-l", str(page), "-png",
         "-singlefile", str(CLEAN), str(png))  # fmt: skip
    pdf = work / f"img{page:03d}.pdf"
    _run(
        "magick", f"{png}.png",
        "-colorspace", "Gray", "-background", "white",
        "-rotate", str(params["skew_degrees"]),
        "-seed", str(seed),
        "-attenuate", str(params["noise_attenuate"]), "+noise", "Gaussian",
        "-blur", f"0x{params['blur_sigma']}",
        "-quality", str(params["jpeg_quality"]),
        "-compress", "JPEG", "-density", "200", "-units", "PixelsPerInch",
        str(pdf),
    )  # fmt: skip
    return pdf


def build() -> None:
    """Assemble every probe cell and write probe.json."""
    from pypdf import PdfReader, PdfWriter

    _fetch(SOURCE_ARXIV, CLEAN)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)  # noqa: S311 - reproducible positions, not security
    clean = PdfReader(str(CLEAN))
    documents = []
    for doc_id, base_pages, image_pages in CELLS:
        positions = sorted(rng.sample(range(2, base_pages + 1), image_pages))
        replaced = []
        writer = PdfWriter()
        with tempfile.TemporaryDirectory() as tmp:
            for page in range(1, base_pages + 1):
                if page in positions:
                    params = _page_params(rng)
                    image = _image_page(page, params, SEED * 1000 + page, Path(tmp))
                    writer.add_page(PdfReader(str(image)).pages[0])
                    replaced.append({"page": page, **params})
                else:
                    writer.add_page(clean.pages[page - 1])
            out = OUT_DIR / f"{doc_id}.pdf"
            with out.open("wb") as handle:
                writer.write(handle)
        share = image_pages / base_pages
        documents.append(
            {
                "doc_id": doc_id,
                "stratum": "synthetic_probe",
                "local_path": f"corpus/probe/{doc_id}.pdf",
                "sha256": _sha256(out),
                "pages": base_pages,
                "image_pages": image_pages,
                "image_share": round(share, 4),
                "expected_route_if_only_image_pages_flagged": share >= PAGE_FRACTION,
                "replaced_pages": replaced,
            }
        )
        print(f"[probe] {doc_id}: {image_pages}/{base_pages} image pages ({share:.1%})")
    MANIFEST.write_text(
        json.dumps(
            {
                "description": (
                    "Exploratory page-fraction boundary probe. Synthetic; never held-out "
                    "evidence; thresholds unchanged."
                ),
                "source": {
                    "arxiv_id": SOURCE_ARXIV,
                    "licence": "http://creativecommons.org/licenses/by/4.0/",
                    "sha256": _sha256(CLEAN),
                },
                "seed": SEED,
                "page_fraction_threshold": PAGE_FRACTION,
                "documents": documents,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def report() -> None:
    """Compare the observed routes with the expected switch."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = {r["doc_id"]: r for r in json.loads(ROUTING.read_text(encoding="utf-8"))["rows"]}
    cells = []
    for doc in manifest["documents"]:
        row = rows[doc["doc_id"]]
        flagged = row.get("pages_needing_ocr")
        cells.append(
            {
                "doc_id": doc["doc_id"],
                "image_share": doc["image_share"],
                "image_pages": doc["image_pages"],
                "pdf_type": row.get("pdf_type"),
                "pdf_confidence": row.get("pdf_confidence"),
                "pages_needing_ocr": flagged,
                "flagged_matches_image_pages": flagged == doc["image_pages"],
                "expected_route": doc["expected_route_if_only_image_pages_flagged"],
                "ocr_required": row.get("ocr_required"),
                "matches_expectation": row.get("ocr_required")
                == doc["expected_route_if_only_image_pages_flagged"],
                "error_class": row.get("error_class"),
            }
        )
    summary = {
        "label": "EXPLORATORY — synthetic boundary probe, not held-out evidence",
        "all_match": all(c["matches_expectation"] for c in cells),
        "cells": cells,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for c in cells:
        print(
            f"[probe] {c['doc_id']} share={c['image_share']:.1%} type={c['pdf_type']} "
            f"flagged={c['pages_needing_ocr']}/{c['image_pages']} "
            f"routed={c['ocr_required']} expected={c['expected_route']}"
        )
    print(f"[probe] all match: {summary['all_match']}")


def main() -> int:
    """Build the probe, or report on its routing run with --report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report()
    else:
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
