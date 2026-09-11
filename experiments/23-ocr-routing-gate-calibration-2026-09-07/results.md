# Experiment 23 — OCR routing gate calibration (task 1.7, design D7.2)

- **Status:** COMPLETE (routing behaviour only)
- **Date:** 2026-09-07
- **Operator:** Dr Muhammad Aizat Bin Md Hawari with AI agent

## Purpose

Choose the OCR routing gate from the task 1.8 configuration shape, using the
CALIBRATION fixture set only. The evaluation set (5 held-out PDFs) is untouched.

## Method

`calibrate.py` reads the pinned `pdf-inspector` observations recorded in
`tests/fixtures/pdf_baseline/manifest.json` (recorded 2026-09-06, pinned by
`tests/unit/test_pdf_baseline_fixtures.py`) and sweeps:

- `OCR_FALLBACK_MIN_CONFIDENCE` ∈ {0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0}
- `OCR_FALLBACK_PAGE_FRACTION` ∈ {0.0, 0.1, 0.25, 0.5, 0.75, 1.0}

Routing rule under sweep: scanned / image-based / mixed classify
OCR-required unconditionally; text-based PDFs route only via a threshold
trigger (confidence < min, or ocr-page proportion ≥ fraction).

Calibration fixtures: `cal_clean_text.pdf` (text_based, conf 1.0, 0/1 OCR
pages), `cal_table_text.pdf` (text_based, conf 1.0, 0/1), `cal_scanned.pdf`
(scanned, conf 0.9, 1/1).

## Result

48 grid cells, matrix in `output/calibration_matrix.json`.

- **40 cells are zero-error** (no text-based PDF routed, no OCR-required PDF
  left behind).
- The ONLY false-positive cells are `page_fraction = 0.0` (all 8 confidence
  levels): a proportion of 0/1 = 0.0 satisfies "≥ 0.0", so the degenerate
  value routes every PDF — including clean text — to OCR.
- **Zero cells** leave the scanned calibration PDF on the fast path;
  classification alone carries it at every grid point.

## Selected gate (for Stage 5 task 5.1)

```text
OCR_FALLBACK_ENABLED         true (opt-in for the ablation; packaged default stays false)
OCR_FALLBACK_MIN_CONFIDENCE  0.5
OCR_FALLBACK_PAGE_FRACTION   0.5
```

## Limitations (stated plainly)

1. The calibration set cannot discriminate among the 40 zero-error cells:
   both text fixtures sit at confidence 1.0 with zero OCR pages, so every
   threshold pair in the admissible region behaves identically. The 0.5/0.5
   pick is the middle of the admissible region — a conservative default, not
   a measured optimum.
2. Three files is thin. Image-based and mixed calibration fixtures do not
   exist (those types live only in the evaluation set); they are
   unconditional by rule, so calibration only needed to confirm the scanned
   case, which it did at every grid point.
3. The degenerate-value finding (fraction 0.0 routes everything) is a real
   configuration hazard: the composition-root validation or documentation
   must steer operators away from 0.0.

Retrieval impact of the gate is NOT assessed here; that is Stage 5's job on
the held-out evaluation set.
