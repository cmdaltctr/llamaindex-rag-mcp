# Design: Experiment 33 OCR Routing Natural-Positive Study

## Context

The packaged OCR gate currently routes unconditional scanned/image-based PDFs and threshold-gates other classifications using confidence and OCR-page fraction. Experiment 29 showed strong false-positive control on its held-out set, but that held-out set had no naturally OCR-required positives.

## Goals

- Measure recall for genuinely OCR-required documents and pages.
- Measure false positives on healthy born-digital documents.
- Measure the cost of unnecessary OCR routing.
- Measure whether correctly routed OCR restores evidence and retrieval quality when real OCR is authorised.

## Non-Goals

- Do not change the current routing thresholds.
- Do not replace PaddleOCR-VL.
- Do not compare OCR vendors.
- Do not infer OCR recovery quality from routing classification alone.

## Corpus Design

Use a frozen stratified corpus with four classes:

1. Born-digital PDFs that should stay on the fast path.
2. Mixed PDFs where only some pages genuinely need OCR.
3. Scanned or image-based PDFs that genuinely require OCR.
4. Reader-failure PDFs: a usable text layer exists, but `pdf-inspector` cannot read it (TDR-024; IA GlyphLessFont, WinAnsi without `/ToUnicode`).

Include naturally occurring cases near the current routing boundary when available. Do not manufacture the evaluation set only to match the existing thresholds.

Documents used to design prior routing candidates may be retained as development/regression cases but must not be presented as independent held-out validation. This includes the Experiment 29 development set, the Experiment 30 corpus, and the Experiment 31 corpus.

## Ground Truth

Ground-truth OCR need must come from direct assessment of page content and extractability, not from `pdf-inspector` classification alone.

Ambiguous cases must be labelled and reported explicitly.

The routing target is document-level. The shipped seam dispatches the whole PDF and does not stitch pages, so routing correctness is scored per document. Page-level labels measure unnecessary OCR pages and evidence at risk in mixed PDFs.

Reader-failure PDFs are scored apart from scanned or image-based positives. When the reader fallback chain recovers the text, the fast path is the correct route. Text lost by a reader tier (for example the LiteParse WinAnsi loss in Experiment 31) is reported as reader-quality loss, not as an OCR false negative.

## Measured Stages

### Stage A: routing only

Run classification and routing decisions without executing real OCR. This stage measures routing correctness and projected OCR work.

Stage A observes the decision on the shipped reader path. The gate inputs are read after the `pdf-inspector` reader fallback chain has run (ADR-066), because a successful rescue sets `pages_needing_ocr` to 0 (TDR-024). Run `OcrRoutedPdfInspector` with `ocr_client=None` and read the stamped `ocr_required`. A replay of raw classifier output is not the shipped policy (Experiment 29 routed Sloman wrongly for this reason).

### Stage B: real OCR recovery

After separate operator authorisation, run real OCR on the approved subset and measure evidence recovery plus downstream retrieval.

Stage B must not run from this proposal alone when authorisation, runtime budget, or worker provisioning is missing.

## Metrics

Primary safety measurements:

- OCR-routing recall on genuinely OCR-required documents;
- false-negative count and rate.

Secondary routing measurements:

- routing precision;
- false-positive count and rate;
- unnecessary OCR pages or projected pages;
- routing decisions by document class.

When Stage B is authorised:

- gold-evidence recoverability;
- Evidence Recall@1, @3, @5, and @10;
- MRR@10;
- OCR elapsed time and failure rate.

## Validity Controls

- Freeze corpus, labels, and scoring rules before held-out measurement.
- Evaluate the current packaged policy exactly as shipped: `OCR_FALLBACK_ENABLED=true`, `0.5` confidence, `0.10` page fraction, unconditional `scanned`/`image_based` (ADR-065), and the reader fallback chain (ADR-066).
- Record the routing-policy revision and effective settings in the manifest.
- Keep development and held-out documents disjoint.
- Preserve missing-worker, timeout, and failed-OCR outcomes instead of converting them into successful measurements.

## Decision Rule

Experiment 33 measures the current gate. It does not recalibrate it.

A material false-negative problem or excessive false-positive cost should trigger a separate calibration proposal. The current thresholds stay unchanged until that proposal is accepted.
