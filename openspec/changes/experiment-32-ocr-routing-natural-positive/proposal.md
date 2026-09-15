# Experiment 32: OCR Routing Natural-Positive Study

## Why

Experiment 29 validated the current OCR routing gate mainly against born-digital held-out PDFs. Its held-out set contained no naturally OCR-required positives, so OCR recall on the held-out set was not directly measured.

OMRG needs a separate study containing genuine OCR-required PDFs and genuine non-OCR PDFs to measure whether the current packaged gate catches documents that need OCR without over-routing healthy documents.

## What Changes

- Add Experiment 32 under `experiments/32-ocr-routing-natural-positive-<date>/` when execution is approved.
- Freeze a stratified corpus containing born-digital, mixed, and scanned/image-based PDFs.
- Label OCR need independently from the classifier and routing output.
- Evaluate the current packaged routing policy without changing its thresholds.
- Make OCR-required false negatives the primary safety outcome.
- Measure routing precision, routing recall, false-positive rate, unnecessary OCR work, and downstream evidence recovery.
- Separate classification/routing evaluation from real OCR execution.
- Require the existing real-OCR authorisation and budget controls before any expensive OCR run.
- Do not change `0.5` or `0.10` defaults in this change.

## Capabilities

### New Capabilities

- `ocr-routing-evaluation`: defines a natural-positive evaluation contract for the packaged OCR routing gate.

### Modified Capabilities

- None.

## Impact

- Adds experiment artefacts only.
- Does not change OCR defaults, worker architecture, or ingestion behaviour.
- Any threshold or routing-policy change requires a separate proposal after the evidence is reviewed.
