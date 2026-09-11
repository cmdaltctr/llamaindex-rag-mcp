"""OCR routing gate calibration sweep (task 1.7, design D7.2).

Reads the pinned pdf-inspector observations for the CALIBRATION fixture
set from tests/fixtures/pdf_baseline/manifest.json (never the evaluation
set) and sweeps the two threshold knobs defined in task 1.8:

    OCR_FALLBACK_MIN_CONFIDENCE   route when confidence < threshold
    OCR_FALLBACK_PAGE_FRACTION    route when ocr_pages / page_count >= fraction

Routing semantics under sweep (identical to design.md D7.3):
    scanned / image-based        -> OCR-required unconditionally
    mixed                        -> OCR-required unconditionally
    text_based                   -> OCR only via a threshold trigger

For each (confidence, fraction) candidate the sweep reports:
    fp  text-based calibration PDFs the gate would route to OCR
    fn  OCR-required calibration PDFs the gate would leave on the fast path

Routing behaviour only. Retrieval quality belongs to the held-out
evaluation set in Stage 5. Output: output/calibration_matrix.json.
"""

from __future__ import annotations

import json
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
MANIFEST = PROJECT_ROOT / "tests/fixtures/pdf_baseline/manifest.json"

CONFIDENCE_GRID = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0)
FRACTION_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
UNCONDITIONAL_TYPES = {"scanned", "image_based", "mixed"}


def routes_to_ocr(obs: dict, min_confidence: float, page_fraction: float) -> bool:
    """One gate decision for one pinned pdf-inspector observation."""
    if obs["pdf_type"] in UNCONDITIONAL_TYPES:
        return True
    if obs["confidence"] < min_confidence:
        return True
    proportion = len(obs["pages_needing_ocr"]) / obs["page_count"]
    return proportion >= page_fraction


def main() -> None:
    """Sweep the grid over calibration fixtures and write the matrix."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    observed = manifest["observed_baseline"]["files"]
    calibration = sorted(name for name in observed if name.startswith("calibration/"))
    if not calibration:
        raise SystemExit("no calibration fixtures in manifest")

    matrix = []
    for min_confidence in CONFIDENCE_GRID:
        for page_fraction in FRACTION_GRID:
            routed, kept = [], []
            for name in calibration:
                obs = observed[name]
                (routed if routes_to_ocr(obs, min_confidence, page_fraction) else kept).append(name)
            fp = [n for n in routed if observed[n]["pdf_type"] == "text_based"]
            fn = [n for n in kept if observed[n]["pdf_type"] in UNCONDITIONAL_TYPES]
            matrix.append(
                {
                    "min_confidence": min_confidence,
                    "page_fraction": page_fraction,
                    "routed_to_ocr": routed,
                    "kept_on_fast_path": kept,
                    "text_based_routed_fp": fp,
                    "ocr_required_left_fp": fn,
                }
            )

    out = EXP_DIR / "output/calibration_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"calibration_files": calibration, "grid": matrix}, indent=2))
    tmp.replace(out)
    clean = [m for m in matrix if not m["text_based_routed_fp"] and not m["ocr_required_left_fp"]]
    print(f"calibration files: {len(calibration)}")
    print(f"grid cells: {len(matrix)}; zero-error cells: {len(clean)}")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
