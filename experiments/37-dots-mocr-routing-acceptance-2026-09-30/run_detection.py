"""Experiment 37 detection runs D-pos and D-neg (detector only, no OCR).

The flags come from the built host detector: ``detect_maths_pages`` and
``maths_condition`` from ``omrg.integrations.pdf.maths_routing``, with the
default OCR route settings (maths routing on, page fraction 0.10). A
separate font walk lists every font name per page, for the report only
(task 7.2: font names on maths pages that the list does not match).

    uv run python experiments/37-.../run_detection.py --run D-neg
    uv run python experiments/37-.../run_detection.py --run D-pos --resume

Writes ``output/detection.json`` atomically after each document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from omrg.config.ocr_routes import OcrRouteSettingsMixin
from omrg.integrations.pdf.maths_pages import (
    MATHS_DETECTOR_VERSION,
    MATHS_FONT_PATTERNS,
    MAX_FORM_DEPTH,
    is_maths_font,
    normalise_font_name,
)
from omrg.integrations.pdf.maths_routing import detect_maths_pages, maths_condition

EXP_DIR = Path(__file__).resolve().parent
OUT = EXP_DIR / "output" / "detection.json"

#: Which sources.json sets each run reads.
RUN_SETS = {"D-neg": {"negative_control"}, "D-pos": {"maths_positive"}}


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON through a ``.tmp`` file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _resolve(value: Any) -> Any:
    getter = getattr(value, "get_object", None)
    return getter() if callable(getter) else value


def page_font_names(resources: Any, depth: int, seen: set[int], names: set[str]) -> None:
    """Collect every ``/BaseFont`` on the page and its Form XObjects (detector walk depth)."""
    if resources is None or depth > MAX_FORM_DEPTH or id(resources) in seen:
        return
    seen.add(id(resources))
    fonts = _resolve(resources.get("/Font"))
    if fonts is not None:
        for font_ref in fonts.values():
            base_font = _resolve(font_ref).get("/BaseFont")
            if base_font is not None:
                names.add(normalise_font_name(str(base_font)))
    xobjects = _resolve(resources.get("/XObject"))
    for xobject_ref in (xobjects or {}).values():
        xobject = _resolve(xobject_ref)
        if xobject.get("/Subtype") == "/Form":
            page_font_names(_resolve(xobject.get("/Resources")), depth + 1, seen, names)


def detect_document(pdf: Path, settings: OcrRouteSettingsMixin) -> dict[str, Any]:
    """Run the host detector on one PDF and list fonts per page."""
    start = time.perf_counter()
    flagged = detect_maths_pages(pdf, settings)
    seconds = time.perf_counter() - start
    reader = PdfReader(str(pdf))
    page_count = len(reader.pages)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        names: set[str] = set()
        try:
            page_font_names(_resolve(page.get("/Resources")), 0, set(), names)
            error = None
        except Exception as exc:  # noqa: BLE001 - report only
            error = f"{type(exc).__name__}: {exc}"
        maths = sorted(n for n in names if is_maths_font(n))
        pages.append(
            {
                "page": number,
                "flagged": number in (flagged or ()),
                "maths_fonts": maths,
                "other_fonts": sorted(names - set(maths)),
                "walk_error": error,
            }
        )
    flagged_sorted = sorted(flagged or ())
    return {
        "page_count": page_count,
        "flagged_pages": flagged_sorted,
        "flagged_count": len(flagged_sorted),
        "flagged_share": round(len(flagged_sorted) / page_count, 4) if page_count else 0.0,
        "maths_condition": maths_condition(flagged, page_count, settings),
        "walk_agrees_with_detector": all(bool(p["maths_fonts"]) == p["flagged"] for p in pages),
        "detector_seconds": round(seconds, 3),
        "pages": pages,
    }


def main() -> int:
    """Run one detection run over its sources.json set."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, choices=sorted(RUN_SETS))
    parser.add_argument("--resume", action="store_true", help="skip documents already in the run")
    args = parser.parse_args()

    sources = json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))
    docs = [d for d in sources["documents"] if d["set"] in RUN_SETS[args.run]]
    if not docs:
        print(
            f"{args.run}: no documents in sets {sorted(RUN_SETS[args.run])}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    settings = OcrRouteSettingsMixin()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 - git from PATH (Homebrew or Xcode)
        cwd=EXP_DIR,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    state: dict[str, Any] = (
        json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {"runs": {}}
    )
    state.update(
        {
            "maths_detector_version": MATHS_DETECTOR_VERSION,
            "maths_font_patterns": list(MATHS_FONT_PATTERNS),
            "settings": {
                "ocr_maths_routing_enabled": settings.ocr_maths_routing_enabled,
                "ocr_maths_page_fraction": settings.ocr_maths_page_fraction,
            },
        }
    )
    run = state["runs"].setdefault(args.run, {"documents": {}})
    if not args.resume:
        run["documents"] = {}
    run.update(
        {"omrg_commit": commit, "started_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    )

    for doc in docs:
        doc_id = doc["doc_id"]
        if args.resume and doc_id in run["documents"]:
            print(f"{args.run} {doc_id}: done, skipped", flush=True)
            continue
        pdf = EXP_DIR / doc["local_path"]
        digest = sha256_file(pdf)
        if digest != doc["sha256"]:
            print(f"{args.run} {doc_id}: SHA-256 mismatch, stop", file=sys.stderr, flush=True)
            return 1
        result = detect_document(pdf, settings)
        run["documents"][doc_id] = {"sha256": digest, **result}
        run["updated_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_atomic(OUT, state)
        print(
            f"{args.run} {doc_id}: {result['flagged_count']}/{result['page_count']} pages flagged "
            f"{result['flagged_pages']} condition={result['maths_condition']} "
            f"walk_agrees={result['walk_agrees_with_detector']} {result['detector_seconds']} s",
            flush=True,
        )

    flagged_total = sum(d["flagged_count"] for d in run["documents"].values())
    pages_total = sum(d["page_count"] for d in run["documents"].values())
    print(
        f"{args.run}: {flagged_total} flagged of {pages_total} pages "
        f"in {len(run['documents'])} documents",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
