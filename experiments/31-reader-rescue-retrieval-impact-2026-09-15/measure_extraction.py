"""Experiment 31 extraction measurement (tasks 3.2-3.4 evidence, 3.6 partial).

Runs every corpus document through each cell's reader path — outside
ingestion, with wall-clock timing (median of 3 runs; first run's text is
kept) — and records per document per cell:

- ``classify_seconds``: one bare ``pdf_inspector.process_pdf`` run (the
  shared first tier, identical in every cell; reference timing).
- ``reader_seconds_median3``: full ``load_data`` wall time, median of 3.
- ``characters``, ``fallback_tier`` (from reader metadata), ``pdf_type``,
  ``pages_needing_ocr`` (post-correction evidence).
- ``ocr_required``: the production routing gate evaluated on the emitted
  evidence (packaged thresholds 0.5 / 0.10, as Experiment 30 used).
- ``ocr_used``: False — the OCR worker is disabled in every cell; this
  field is recorded so the abort check (task 4.4) has an auditable input.

Full extracted texts are saved to gitignored ``output/.extractions/<cell>/``
for the evidence-recoverability measurement; the public manifest
``output/extraction_manifest.json`` carries doc_id-level rows only — no
paths, no text (task 4.5).

Usage:
    uv run python measure_extraction.py [--cell A|B|C ...] [--splits heldout,distractor,development]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR))

import harness_readers  # noqa: E402

harness_readers.register_mirrors()

from omrg.integrations.pdf import registry as pdf_registry  # noqa: E402
from omrg.integrations.pdf.ocr_routing import ocr_required_by_gate  # noqa: E402

CELL_READERS = {
    "A": "exp31_inspector_only",
    "B": "pdf_inspector",
    "C": "exp31_pypdf_guard",
}


class _Gate:
    """Packaged OCR gate thresholds (0.5 / 0.10), as Experiment 30 used."""

    ocr_fallback_min_confidence: float = 0.5
    ocr_fallback_page_fraction: float = 0.10


GATE = _Gate()


def _route(evidence: dict) -> bool:
    return ocr_required_by_gate(
        pdf_type=str(evidence.get("pdf_type", "")),
        pdf_confidence=float(evidence.get("pdf_confidence", 1.0)),
        pages_needing_ocr=int(evidence.get("pages_needing_ocr", 0)),
        page_count=int(evidence.get("page_count", 0)),
        settings=GATE,
    )


def _measure(reader_cls: object, path: Path, repeats: int = 3) -> dict:
    """Run *reader_cls*().load_data(path) *repeats* times; keep run-1 output."""
    first = None
    times: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        docs = reader_cls().load_data(path)  # type: ignore[attr-defined]
        times.append(time.perf_counter() - started)
        if first is None:
            first = docs
    return {"docs": first, "seconds_median": statistics.median(times)}


def _positive_int(value: str) -> int:
    """Argparse type: reject --repeats below 1 (median of an empty list raises)."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", choices=sorted(CELL_READERS), action="append")
    parser.add_argument("--splits", default="heldout,distractor,development")
    parser.add_argument("--repeats", type=_positive_int, default=3)
    args = parser.parse_args()
    cells = args.cell or sorted(CELL_READERS)
    splits = set(args.splits.split(","))

    private = json.loads((EXP_DIR / "output" / ".collection.private.json").read_text())
    targets = [d for d in private["documents"] if d["split"] in splits]

    extraction_dir = EXP_DIR / "output" / ".extractions"
    rows: list[dict] = []
    for cell in cells:
        reader_name = CELL_READERS[cell]
        reader_cls = pdf_registry.get(reader_name)
        cell_dir = extraction_dir / cell
        cell_dir.mkdir(parents=True, exist_ok=True)
        for entry in targets:
            path = Path(entry["path"])
            # Shared first-tier reference timing (identical in every cell).
            import pdf_inspector

            t0 = time.perf_counter()
            raw = pdf_inspector.process_pdf(str(path))
            classify_s = time.perf_counter() - t0

            measured = _measure(reader_cls, path, repeats=args.repeats)
            docs = measured["docs"]
            text = "\n\n".join(doc.text for doc in docs if doc.text)
            meta = docs[0].metadata if docs else {}
            (cell_dir / f"{entry['doc_id']}.txt").write_text(text, encoding="utf-8")

            evidence = {
                "pdf_type": meta.get("pdf_type", raw.pdf_type),
                "pdf_confidence": meta.get("pdf_confidence", raw.confidence),
                "pages_needing_ocr": meta.get("pages_needing_ocr", 0),
                "page_count": meta.get("page_count", raw.page_count),
            }
            row = {
                "cell": cell,
                "reader": reader_name,
                "doc_id": entry["doc_id"],
                "split": entry["split"],
                "classify_seconds": round(classify_s, 3),
                "reader_seconds_median3": round(measured["seconds_median"], 3),
                "characters": len(text),
                "fallback_tier": meta.get("extraction_fallback_backend"),
                "pdf_type": evidence["pdf_type"],
                "page_count": evidence["page_count"],
                "pages_needing_ocr": evidence["pages_needing_ocr"],
                "ocr_required": _route(evidence),
                "ocr_used": False,  # OCR worker disabled in every cell
            }
            rows.append(row)
            print(
                f"[{cell}] {entry['doc_id']}: {row['characters']} chars, "
                f"tier={row['fallback_tier']}, reader={row['reader_seconds_median3']}s, "
                f"ocr_required={row['ocr_required']}",
                flush=True,
            )

    out_path = EXP_DIR / "output" / "extraction_manifest.json"
    existing: list[dict] = []
    if out_path.is_file():
        existing = json.loads(out_path.read_text())
        by_key = {(r["cell"], r["doc_id"]): r for r in existing}
        for row in rows:
            by_key[(row["cell"], row["doc_id"])] = row
        existing = sorted(by_key.values(), key=lambda r: (r["cell"], r["doc_id"]))
    else:
        existing = sorted(rows, key=lambda r: (r["cell"], r["doc_id"]))
    out_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"wrote {out_path.name}: {len(existing)} rows", flush=True)


if __name__ == "__main__":
    main()
