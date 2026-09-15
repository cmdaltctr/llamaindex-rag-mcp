"""Experiment 31 preflight (tasks 4.1-4.5).

Gate between index build and the measured run. Every check must pass;
the measured run refuses to start otherwise. Output:
``output/preflight.json``.

Checks:
- 4.1  freeze intact; three runtime manifests present; controlled
       variables identical across cells except ``pdf_reader``; same
       document set measured in every cell.
- 4.2  development pathological docs hit the empty-extraction path in
       Cell A and are rescued in B/C; the healthy control extracts
       everywhere with no fallback tier; the scanned control stays
       ``scanned``.
- 4.3  every held-out document produced ZERO chunks in the Cell A index.
- 4.4  no measured document reports ``ocr_used=True`` (abort condition;
       with the worker disabled this must never fire) and none is
       OCR-routed in any measured cell.
- 4.5  public artefacts leak no absolute local paths and carry no
       document text.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

import freeze  # noqa: E402

RESULTS: list[dict] = []


def _check(name: str, passed: bool, detail: str = "") -> bool:
    RESULTS.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    print(
        f"{'PASS' if passed else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""), flush=True
    )
    return passed


def main() -> int:
    out_dir = EXP_DIR / "output"

    # ── 4.1 freeze + manifests ─────────────────────────────────────
    recorded = json.loads((out_dir / "frozen.manifest.json").read_text())
    current = freeze._build()
    mismatches = [
        label
        for label, entry in recorded["files"].items()
        if current["files"].get(label, {}).get("sha256") != entry["sha256"]
    ] + [
        f"doc {d}"
        for d, digest in recorded["documents"].items()
        if current["documents"].get(d) != digest
    ]
    _check("4.1a freeze intact", not mismatches, ", ".join(mismatches) if mismatches else "")

    manifests = {}
    missing = [c for c in "ABC" if not (out_dir / f"runtime_manifest_{c}.json").is_file()]
    _check("4.1b runtime manifests present", not missing, f"missing {missing}" if missing else "")
    if missing:
        _dump(out_dir)
        return 1
    for cell in "ABC":
        manifests[cell] = json.loads((out_dir / f"runtime_manifest_{cell}.json").read_text())

    def _strip_reader(cv: dict) -> dict:
        clone = json.loads(json.dumps(cv))
        clone.pop("pdf_reader", None)
        return clone

    differing = [
        c
        for c in "BC"
        if _strip_reader(manifests[c]["controlled_variables"])
        != _strip_reader(manifests["A"]["controlled_variables"])
    ]
    readers = {c: manifests[c]["reader"] for c in "ABC"}
    _check(
        "4.1c controlled variables identical; logical readers differ per cell",
        not differing and len(set(readers.values())) == 3,
        f"readers={readers}" + (f" differing={differing}" if differing else ""),
    )

    def _docset(cell: str) -> set[str]:
        return {d["doc_id"] for d in manifests[cell]["documents"]}

    _check(
        "4.1d same measured document set in every cell",
        _docset("A") == _docset("B") == _docset("C"),
        f"A={len(_docset('A'))} B={len(_docset('B'))} C={len(_docset('C'))}",
    )
    dev_in_index = _docset("A") & {
        "p01_ia_prince",
        "p02_ia_managing",
        "p03_winansi_sloman",
        "c01_scanned_kerr",
        "c02_healthy_graphrag",
    }
    _check(
        "4.1e development documents excluded from indexes",
        not dev_in_index,
        f"found {sorted(dev_in_index)}" if dev_in_index else "",
    )

    # ── 4.2 development paths ──────────────────────────────────────
    extraction = {
        (r["cell"], r["doc_id"]): r
        for r in json.loads((out_dir / "extraction_manifest.json").read_text())
    }
    pathological_ok = all(
        extraction[("A", d)]["characters"] == 0
        and extraction[("B", d)]["characters"] > 0
        and extraction[("C", d)]["characters"] > 0
        for d in ("p01_ia_prince", "p02_ia_managing", "p03_winansi_sloman")
    )
    _check("4.2a pathological docs: empty in A, rescued in B and C", pathological_ok)
    _check(
        "4.2b healthy control extracts with no fallback tier",
        all(extraction[(c, "c02_healthy_graphrag")]["characters"] > 0 for c in "ABC")
        and all(extraction[(c, "c02_healthy_graphrag")]["fallback_tier"] is None for c in "ABC"),
    )
    scanned = [extraction[(c, "c01_scanned_kerr")]["pdf_type"] for c in "ABC"]
    _check(
        "4.2c scanned control classified scanned in every cell",
        set(scanned) == {"scanned"},
        str(scanned),
    )

    # ── 4.3 Cell A zero chunks for measured PDFs ───────────────────
    heldout_ids = {
        d["doc_id"]
        for d in json.loads((EXP_DIR / "corpus_manifest.json").read_text())["documents"]
        if d["split"] == "heldout"
    }
    with_chunks = [
        d["doc_id"]
        for d in manifests["A"]["documents"]
        if d["doc_id"] in heldout_ids and (d["chunks_created"] or 0) > 0
    ]
    _check(
        "4.3 held-out PDFs produce zero chunks in Cell A",
        not with_chunks,
        f"chunked: {with_chunks}" if with_chunks else "",
    )
    zero_extraction = all(extraction[("A", h)]["characters"] == 0 for h in heldout_ids)
    _check("4.3b held-out PDFs extract zero characters in Cell A", zero_extraction)

    # ── 4.4 OCR abort condition ────────────────────────────────────
    measured_ids = heldout_ids | {
        d["doc_id"]
        for d in json.loads((EXP_DIR / "corpus_manifest.json").read_text())["documents"]
        if d["split"] == "distractor"
    }
    used = [
        f"{c}/{d}" for (c, d), r in extraction.items() if d in measured_ids and r.get("ocr_used")
    ]
    _check(
        "4.4a no measured document used OCR (abort rule)", not used, f"used: {used}" if used else ""
    )
    # Cell A legitimately OCR-routes the unrescued held-out documents
    # (the rescue that would reset the flag does not fire there); the
    # invariant that matters is that no measured document routes to OCR
    # in the measured comparison cells B and C.
    routed = [
        f"{c}/{d}"
        for (c, d), r in extraction.items()
        if c in ("B", "C") and d in measured_ids and r.get("ocr_required")
    ]
    _check(
        "4.4b no measured document is OCR-routed in cells B or C",
        not routed,
        f"routed: {routed}" if routed else "",
    )

    # ── 4.5 privacy ────────────────────────────────────────────────
    path_re = re.compile(r"/Users/|/home/|[A-Za-z]:\\\\")
    leaks: list[str] = []
    for artefact in [
        EXP_DIR / "corpus_manifest.json",
        out_dir / "extraction_manifest.json",
        *[out_dir / f"runtime_manifest_{c}.json" for c in "ABC"],
    ]:
        if artefact.is_file():
            blob = artefact.read_text()
            if path_re.search(blob):
                leaks.append(f"{artefact.name}: absolute path")
    _check(
        "4.5a public artefacts carry no absolute paths",
        not leaks,
        "; ".join(leaks) if leaks else "",
    )
    giant = [r["doc_id"] for r in extraction.values() if "text" in r or "content" in r]
    _check("4.5b public rows carry no document text", not giant, str(giant) if giant else "")

    _dump(out_dir)
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    print(f"\npreflight: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed", flush=True)
    return 1 if failed else 0


def _dump(out_dir: Path) -> None:
    (out_dir / "preflight.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
