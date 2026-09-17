## Why

`pdf_inspector.process_pdf` decides which pages need OCR from at most 8 evenly spread sample pages. A `text_based` PDF with image-only pages outside that sample reports `pages_needing_ocr = 0`, so the calibrated `0.10` page-fraction gate never fires and scanned evidence stays unread. The Experiment 33 boundary probe showed it: 3 scanned pages out of 20 (15%) stayed on the fast path, and a single scanned page in a 20-page PDF is seen only at pages 1, 3, 5, 7, 9, 11, 13 and 20.

## What Changes

- The pdf-inspector adapter completes the OCR evidence for `text_based` PDFs longer than the detection sample: it scans every page with `pdf_inspector.extract_pages_markdown` and uses that page count for `pages_needing_ocr`.
- `text_based` PDFs with 8 pages or fewer, and `scanned`, `image_based` and `mixed` PDFs, get no extra scan (already complete or already routed).
- A failure of the full scan keeps the sampled evidence, logs a warning, and never fails the read.
- The silent-empty rescue keeps its contract: the full-scan count becomes the pre-fallback diagnostic, and a successful rescue still sets `pages_needing_ocr` to zero.
- The `0.5` / `0.10` thresholds, `pdf_type` and `pdf_confidence` do not change. No new metadata key is added.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pdf-reader`: adds a requirement that pdf-inspector OCR evidence covers every page of `text_based` PDFs longer than the detection sample.

## Impact

- Code: `src/omrg/integrations/pdf/pdf_inspector.py` only.
- Tests: `tests/unit/test_pdf_inspector_reader.py`.
- Docs: new TDR-026; `docs/guides/ingestion.md`.
- Cost: one extra full parse for `text_based` PDFs over 8 pages (measured in TDR-026).
- Index identity is unchanged. PDFs already indexed are not re-routed until they are re-ingested.
- Experiment 33 measures the pre-fix and fixed code as two arms.
